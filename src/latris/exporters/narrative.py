"""Narrative preamble builder — client-facing summary for export reports.

Assembles a structured narrative from project data: what the model is for,
what it contains, and how it evolved. Uses AI to generate prose summaries
of the model structure and history. Falls back to mechanical descriptions
if the AI is unavailable (no API key, network error, mock mode).

Client tone: professional, third-person, no jargon about the tool itself.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from latris.diff.semantic import read_log
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import (
    AssumptionLog,
    ChallengeLog,
    DescriptionSet,
    EvidenceLinkSet,
    PolaritySet,
    ProjectFoundation,
    ReferenceLibrary,
    Substrate,
)

log = logging.getLogger(__name__)


@dataclass
class Narrative:
    title: str
    purpose: str
    structure_description: str  # AI prose describing the model structure
    boundary: str
    history_summary: str  # AI prose summarising the model evolution


class _NarrativeResponse(BaseModel):
    """Response schema for the AI narrative call."""

    structure_description: str = Field(
        ...,
        description=(
            "A prose description (~1 page) of the model's structure for a "
            "client audience. Describe the key entities, how they relate to "
            "each other, the causal chains, and what the overall structure "
            "tells us. Do not list connections mechanically — interpret them."
        ),
    )
    history_summary: str = Field(
        ...,
        description=(
            "A prose summary of how the model evolved over time, written for "
            "a client audience. Highlight key milestones: when the model was "
            "created, major structural changes, evidence additions, challenges "
            "raised, and reviews conducted. Keep it narrative, not a bullet list."
        ),
    )


def build_narrative(paths: ProjectPaths, *, model_type: str | None = None) -> Narrative:
    """Build a client-facing narrative preamble from the project data.

    When ``model_type`` is given, the structure description is scoped to that
    formalism's view (so a per-formalism report's prose describes only that
    formalism's entities and relationships)."""
    from latris.exporters._scope import view_member_ids

    foundation = load_model(ProjectFoundation, paths.project_yaml)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    members = view_member_ids(paths, model_type)
    if members is not None:
        substrate.entities = [e for e in substrate.entities if e.id in members]
        substrate.edges = [e for e in substrate.edges if e.id in members]
    assumptions = load_model(AssumptionLog, paths.assumptions_yaml).entries
    challenges = load_model(ChallengeLog, paths.challenges_yaml).entries
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml).entries
    references = load_model(ReferenceLibrary, paths.references_yaml).entries

    title = foundation.name or foundation.statement

    purpose = f'This model addresses the modelling question: "{foundation.statement}"'

    boundary = ""
    if getattr(foundation, "boundary", None):
        boundary = f"Model boundary: {foundation.boundary}"

    # Try AI-generated prose; fall back to mechanical descriptions
    history_entries = _build_history_entries(paths.root)
    ai_result = _try_ai_narrative(
        paths, foundation, substrate, assumptions, challenges, evidence, references, history_entries
    )

    if ai_result is not None:
        structure_description = ai_result.structure_description
        history_summary = ai_result.history_summary
    else:
        structure_description = _mechanical_scope(
            substrate,
            assumptions,
            challenges,
            evidence,
            references,
        )
        history_summary = _mechanical_history(history_entries)

    return Narrative(
        title=title,
        purpose=purpose,
        structure_description=structure_description,
        boundary=boundary,
        history_summary=history_summary,
    )


def _try_ai_narrative(
    paths: ProjectPaths,
    foundation: ProjectFoundation,
    substrate: Substrate,
    assumptions,
    challenges,
    evidence,
    references,
    history_entries: list[tuple[str, str]],
) -> _NarrativeResponse | None:
    """Attempt to generate AI prose for structure and history. Returns None on failure."""
    try:
        from latris.ai import config as ai_config
        from latris.ai import credentials as creds
        from latris.ai.adapters import get_adapter

        cfg = ai_config.load(paths)
        model = ai_config.resolve_model(paths)
        provider = model.split("/", 1)[0].lower() if "/" in model else "gemini"
        adapter = get_adapter()

        # Build context for the AI
        labels = {e.id: e.label for e in substrate.entities}
        descriptions = {
            (e.target_id, e.attribute): e for e in load_model(DescriptionSet, paths.descriptions_yaml).entries
        }
        pol_path = paths.view_attribute_path("cld", "polarity")
        pol_set = load_model(PolaritySet, pol_path) if pol_path.exists() else PolaritySet()
        polarity = {(e.target_id, e.attribute): e for e in pol_set.entries}

        entity_lines = []
        for e in substrate.entities:
            desc = descriptions.get((e.id, "description"))
            desc_text = f" — {desc.value}" if desc else ""
            entity_lines.append(f"  {e.label} ({e.kind}){desc_text}")

        edge_lines = []
        for e in substrate.edges:
            src = labels.get(e.from_id, e.from_id[:12])
            dst = labels.get(e.to_id, e.to_id[:12])
            desc = descriptions.get((e.id, "description"))
            pol = polarity.get((e.id, "polarity"))
            desc_text = f" — {desc.value}" if desc else ""
            pol_text = f" [{pol.value}]" if pol else ""
            edge_lines.append(f"  {src} → {dst} ({e.kind}){pol_text}{desc_text}")

        assumption_lines = [f"  {a.statement}" for a in assumptions]
        challenge_lines = [
            f"  [{c.state}] {labels.get(c.target_id, c.target_id[:12])}: {c.argument[:80]}" for c in challenges
        ]
        history_lines = [f"  {date}: {summary}" for date, summary in history_entries]

        user_message = (
            f"# Model overview\n"
            f'This model addresses the modelling question: "{foundation.statement}"\n'
            + (f"Boundary: {foundation.boundary}\n" if getattr(foundation, "boundary", None) else "")
            + f"\n# Entities ({len(substrate.entities)})\n"
            + "\n".join(entity_lines)
            + f"\n\n# Relationships ({len(substrate.edges)})\n"
            + "\n".join(edge_lines)
            + f"\n\n# Assumptions ({len(assumptions)})\n"
            + ("\n".join(assumption_lines) if assumption_lines else "  (none)")
            + f"\n\n# Challenges ({len(challenges)})\n"
            + ("\n".join(challenge_lines) if challenge_lines else "  (none)")
            + "\n\n# Evidence\n"
            + f"  {len(evidence)} evidence links across {len(references)} references"
            + "\n\n# Model history (chronological)\n"
            + ("\n".join(history_lines) if history_lines else "  (no history)")
            + "\n\n# Task\n"
            "Write for a client audience. Professional tone, third person. "
            "Do not mention the tool, IDs, YAML files, or git. "
            "The structure_description should be ~1 page of prose describing "
            "the model's entities, their relationships, key causal pathways, "
            "and what the structure reveals. Interpret, don't just list. "
            "The history_summary should narrate how the model evolved: "
            "creation, structural additions, evidence, challenges, reviews."
        )

        system = (
            "You are writing the executive summary section of a modelling "
            "report for a client. Return structured output matching the schema. "
            "Write clear, professional prose. No bullet lists."
        )

        with creds.key_in_env([provider]):
            result = adapter.chat(
                model=model,
                system=system,
                user=user_message,
                response_model=_NarrativeResponse,
                temperature=ai_config.resolve_temperature(model, 0.3),
                max_tokens=cfg.max_tokens,
            )
        return result.parsed

    except Exception as exc:
        log.info("AI narrative generation failed, using fallback: %s", exc)
        return None


# ---------- Mechanical fallbacks ----------


def _mechanical_scope(substrate, assumptions, challenges, evidence, references) -> str:
    """Fallback: mechanical scope description when AI is unavailable."""
    n_nodes = len(substrate.entities)
    n_edges = len(substrate.edges)
    n_evidence = len(evidence)
    n_refs = len(references)
    n_assumptions = len(assumptions)
    n_challenges_open = sum(1 for c in challenges if c.state == "open")
    n_challenges_resolved = sum(1 for c in challenges if c.state != "open")

    entity_kinds = Counter(e.kind for e in substrate.entities)
    kind_parts = [f"{count} {kind}{'s' if count != 1 else ''}" for kind, count in sorted(entity_kinds.items())]

    parts = [
        f"The model comprises {n_nodes} {'entity' if n_nodes == 1 else 'entities'} "
        f"and {n_edges} {'relationship' if n_edges == 1 else 'relationships'}",
    ]
    if kind_parts:
        parts[0] += f" ({', '.join(kind_parts)})"
    parts[0] += "."

    if n_evidence or n_refs:
        bits = []
        if n_evidence:
            bits.append(f"{n_evidence} evidence {'link' if n_evidence == 1 else 'links'}")
        if n_refs:
            bits.append(f"{n_refs} {'reference' if n_refs == 1 else 'references'}")
        parts.append(f"It is supported by {' and '.join(bits)}.")

    if n_assumptions:
        assumption_label = "assumption" if n_assumptions == 1 else "assumptions"
        parts.append(f"The model rests on {n_assumptions} stated {assumption_label}.")

    if n_challenges_open or n_challenges_resolved:
        bits = []
        if n_challenges_open:
            bits.append(f"{n_challenges_open} open")
        if n_challenges_resolved:
            bits.append(f"{n_challenges_resolved} resolved")
        parts.append(f"Challenges raised: {', '.join(bits)}.")

    return " ".join(parts)


def _mechanical_history(entries: list[tuple[str, str]]) -> str:
    """Fallback: bullet-style history when AI is unavailable."""
    if not entries:
        return ""
    lines = [f"- **{date}** — {summary}" for date, summary in entries]
    return "\n".join(lines)


def _build_history_entries(root: Path) -> list[tuple[str, str]]:
    """Extract (date, summary) pairs from git commits."""
    commits = read_log(root, limit=50)
    if not commits:
        return []
    entries = []
    for commit in reversed(commits):
        subject = commit.get("subject", "")
        if _is_meta_commit(subject):
            continue
        date = commit.get("date", "")[:10]
        entries.append((date, subject))
    return entries


def _is_meta_commit(subject: str) -> bool:
    """Filter out commits that don't represent meaningful model events."""
    lowered = subject.lower()
    skip_prefixes = (
        "logged interaction",
        "set approval",
        "approved interaction",
    )
    return any(lowered.startswith(p) for p in skip_prefixes)
