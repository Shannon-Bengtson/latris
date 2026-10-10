"""Interpret operations — claim extraction, prose management, persistence.

Template-based claim extraction from findings/analysis results, plus
CRUD for interpretation sections (editable AI prose with version history).
"""

from __future__ import annotations

from pathlib import Path

from latris.operations.commit import auto_commit
from latris.operations.interpret_registry import (
    get_sections_for_model_types,
)
from latris.repo import git
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema.common import now_utc
from latris.schema.findings import Finding, FindingCategory
from latris.schema.ids import new_id
from latris.schema.interpretation import (
    InterpretationStore,
    InterpretSection,
    InterpretSectionId,
    InterpretTextVersion,
)
from latris.schema.project import ProjectFoundation

# ── Loading / saving ────────────────────────────────────────────────────


def load_interpretation(*, root: Path | None = None) -> InterpretationStore:
    """Load the interpretation store from YAML (empty if file absent)."""
    paths = require_project(root)
    if paths.interpretation_yaml.exists():
        return load_model(InterpretationStore, paths.interpretation_yaml)
    return InterpretationStore()


def save_interpretation(
    store: InterpretationStore,
    *,
    subject: str = "Update interpretation",
    root: Path | None = None,
) -> str:
    """Persist the interpretation store and commit."""
    paths = require_project(root)
    dump_model(store, paths.interpretation_yaml)
    sha = auto_commit(
        paths.root,
        subject=subject,
        paths=[paths.interpretation_yaml],
    )
    return sha


# ── Initialisation ──────────────────────────────────────────────────────


def initialise_sections(
    *, root: Path | None = None
) -> tuple[InterpretationStore, str, list[tuple[str, str]]]:
    """Create interpretation sections for selected model types that pass
    structural readiness.

    Returns ``(store, commit_sha, skipped)`` where ``skipped`` is a list
    of ``(model_type_id, reason)`` pairs for selected model types that
    failed structural readiness (e.g. cycle in DAG, no loops in CLD).

    Selected-but-structurally-failed model types are skipped here rather
    than rendered with stale claims later. Attribute-completeness gaps
    (e.g. some edges missing polarity) do *not* skip section creation —
    those are handled at claim/prose level.

    Idempotent — existing sections are preserved; only missing ones are
    added.
    """
    from latris.operations.readiness import assess_readiness

    paths = require_project(root)
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    selected = foundation.selected_model_types

    # Filter to structurally-viable model types. The readiness scoring
    # collapses any structural-validator failure to score=0 (see
    # readiness.py:224-232), so score>0 ↔ structural_ok. Planned types
    # also score 0 — they get skipped here too with their planned
    # status surfaced as the skip reason.
    viable: list[str] = []
    skipped: list[tuple[str, str]] = []
    for mid in selected:
        r = assess_readiness(mid, root=paths.root)
        if r.score > 0:
            viable.append(mid)
        else:
            # Prefer the first structural gap message; fall back to
            # the readiness summary if no gaps were named.
            structural_gap_types = {"cycle_detected", "no_loops"}
            structural_gaps = [g for g in r.gaps if g.gap_type in structural_gap_types]
            reason = (
                structural_gaps[0].message
                if structural_gaps
                else (r.summary or "structural readiness failed")
            )
            skipped.append((mid, reason))

    specs = get_sections_for_model_types(viable)

    store = load_interpretation(root=paths.root)
    existing = {(s.section_type, s.model_type) for s in store.sections}

    for spec in specs:
        for model_type in viable:
            if model_type not in spec.applicable_model_types:
                continue
            if (spec.section_type, model_type) in existing:
                continue
            section = InterpretSection(
                id=new_id("interpret-section"),
                section_type=spec.section_type,
                model_type=model_type,
            )
            store.sections.append(section)

    sha = save_interpretation(
        store,
        subject="Initialise interpretation sections",
        root=paths.root,
    )
    return store, sha, skipped


# ── Claim extraction ────────────────────────────────────────────────────


def extract_claims(
    section_type: InterpretSectionId,
    model_type: str,
    *,
    root: Path | None = None,
) -> list[str]:
    """Extract template-based claims for a section. Pure from project state."""
    paths = require_project(root)
    extractors = {
        "structural_summary": _extract_structural_summary,
        "key_findings": _extract_key_findings,
        "sensitivity": _extract_sensitivity,
        "assumptions_limitations": _extract_assumptions,
        "evidence_gaps": _extract_evidence_gaps,
        "evidence_coverage": _extract_evidence_coverage,
        "answer_to_question": _extract_answer,
        "implications": _extract_implications,
        "confidence_assessment": _extract_confidence,
        "open_questions": _extract_open_questions,
    }
    extractor = extractors.get(section_type)
    if extractor is None:
        return []
    return extractor(model_type, paths)


def refresh_claims(
    section_id: str,
    *,
    root: Path | None = None,
) -> tuple[InterpretSection, str]:
    """Re-extract claims for a section. Marks prose stale if claims changed."""
    paths = require_project(root)
    store = load_interpretation(root=paths.root)

    section = _find_section(store, section_id)
    new_claims = extract_claims(section.section_type, section.model_type, root=paths.root)

    section.claims = new_claims
    section.model_commit = git.head_sha(paths.root)
    section.updated_at = now_utc()

    if section.generation_state == "empty":
        section.generation_state = "claims_only"

    sha = save_interpretation(
        store,
        subject=f"Refresh claims: {section.section_type}",
        root=paths.root,
    )
    return section, sha


def refresh_all_claims(
    *,
    root: Path | None = None,
) -> tuple[InterpretationStore, str]:
    """Re-extract claims for all sections."""
    paths = require_project(root)
    store = load_interpretation(root=paths.root)

    for section in store.sections:
        new_claims = extract_claims(section.section_type, section.model_type, root=paths.root)
        section.claims = new_claims
        section.model_commit = git.head_sha(paths.root)
        section.updated_at = now_utc()
        if section.generation_state == "empty":
            section.generation_state = "claims_only"

    sha = save_interpretation(
        store,
        subject="Refresh all interpretation claims",
        root=paths.root,
    )
    return store, sha


# ── Prose management ────────────────────────────────────────────────────


def update_prose(
    section_id: str,
    prose: str,
    *,
    source: str = "human-edit",
    root: Path | None = None,
) -> tuple[InterpretSection, str]:
    """Update prose for a section. Appends to version history."""
    paths = require_project(root)
    store = load_interpretation(root=paths.root)

    section = _find_section(store, section_id)
    section.prose = prose
    section.updated_at = now_utc()

    # Snapshot current claims at generation time for staleness tracking
    if source == "ai":
        section.claims_at_generation = list(section.claims)
        section.generation_state = "generated"
    else:
        section.generation_state = "edited"

    # Append to version history
    version = InterpretTextVersion(
        version_id=new_id("version"),
        text=prose,
        source=source,  # type: ignore[arg-type]
        model_commit=git.head_sha(paths.root),
    )
    section.prose_versions.append(version)

    sha = save_interpretation(
        store,
        subject=f"{'Generate' if source == 'ai' else 'Edit'} interpretation: {section.section_type}",
        root=paths.root,
    )
    return section, sha


# ── Private claim extractors ────────────────────────────────────────────


def _load_findings(paths, model_type: str | None = None) -> list[Finding]:
    """Load findings, optionally filtered by model_type."""
    from latris.operations.findings import list_findings

    return list_findings(model_type=model_type, root=paths.root)


# ── AI interrogation Phase 2b: hedge-mode infrastructure ────────────────


# Below this fraction of element coverage AND with zero accepted findings,
# Interpret* prompts get a hedge instruction that forbids confident
# magnitude claims (centrality decimals, "self-amplifying" prose, etc.).
# Module-level constant — calibrate on real runs before exposing in
# ai_config.yaml.
HEDGE_COVERAGE_THRESHOLD: float = 0.5


def coverage_ratio(model_type: str, paths) -> tuple[int, int, float]:
    """Return ``(cited_count, total_count, ratio)`` for evidence coverage.

    ``ratio`` is ``cited / total`` and ``1.0`` when total is zero (an
    empty model has nothing to be uncited about, so it should not
    auto-trigger hedge mode on coverage grounds alone).
    """
    from latris.schema import EvidenceLinkSet, Substrate

    substrate = load_model(Substrate, paths.conceptual_yaml)
    evidence_path = paths.evidence_links_yaml
    evidence = (
        load_model(EvidenceLinkSet, evidence_path) if evidence_path.exists() else EvidenceLinkSet()
    )

    all_ids = {e.id for e in substrate.entities} | {e.id for e in substrate.edges}
    total = len(all_ids)
    if total == 0:
        return 0, 0, 1.0

    cited_targets = {e.target_id for e in evidence.entries if e.target_id is not None}
    cited = len(all_ids & cited_targets)
    return cited, total, cited / total


def accepted_findings_count(model_type: str, paths) -> int:
    """Count findings whose maturity is ``approved`` for a given model type."""
    return sum(1 for f in _load_findings(paths, model_type) if f.maturity == "approved")


def hedge_mode_active(model_type: str, paths) -> bool:
    """Whether `Interpret*` prompts should be passed a hedge instruction.

    Active iff evidence coverage is below the threshold AND no
    findings have been accepted yet — projects that have done real
    curation (accepted findings) are trusted to speak more
    confidently even if many supplementary nodes remain uncited.
    """
    _cited, _total, ratio = coverage_ratio(model_type, paths)
    return ratio < HEDGE_COVERAGE_THRESHOLD and accepted_findings_count(model_type, paths) == 0


def _extract_structural_summary(model_type: str, paths) -> list[str]:
    """Claims from model structure — loops, topology, connectivity."""
    from latris.operations.graph_analysis import (
        causal_edges,
        classify_loop,
        find_all_loops,
    )
    from latris.schema import Substrate

    substrate = load_model(Substrate, paths.conceptual_yaml)
    claims: list[str] = []

    n_entities = len(substrate.entities)
    n_edges = len(substrate.edges)
    claims.append(f"Model contains {n_entities} entities and {n_edges} relationships.")

    # Loop detection runs over causal edges only — non-causal kinds
    # (decision_rule, governance, flow, ...) inflate loop counts and
    # produce the "self-amplifying system" overclaim caught in the
    # 4DWW capability run.
    causal = causal_edges(substrate.edges)
    if model_type in ("cld", "fcm") and causal:
        # Load polarity for classification
        polarity_path = paths.view_attribute_path(model_type, "polarity")
        polarity_map: dict[str, str] = {}
        if polarity_path.exists():
            from latris.schema import PolaritySet

            pol_set = load_model(PolaritySet, polarity_path)
            polarity_map = {e.target_id: e.value for e in pol_set.entries if e.attribute == "polarity"}

        loops = find_all_loops(causal)
        if loops:
            classified = [classify_loop(loop, polarity_map) for loop in loops]
            r_count = sum(1 for loop in classified if loop.classification == "R")
            b_count = sum(1 for loop in classified if loop.classification == "B")
            u_count = sum(1 for loop in classified if loop.classification == "unknown")
            claims.append(
                f"{len(loops)} feedback loop(s) detected: "
                f"{r_count} reinforcing, {b_count} balancing" + (f", {u_count} unclassified" if u_count else "") + "."
            )
            # Name the longest loop. Always show the full cycle and close
            # back to the start node — truncating with "→ …" creates an
            # apparent node-count mismatch (claim says N nodes, display
            # shows fewer) that erodes reader trust.
            longest = max(classified, key=lambda loop: len(loop.node_ids))
            entity_labels = {e.id: e.label for e in substrate.entities}
            loop_names = [entity_labels.get(nid, nid[:8]) for nid in longest.node_ids]
            claims.append(
                f"Longest loop ({len(longest.node_ids)} nodes, {longest.classification}): "
                f"{' → '.join(loop_names)} → {loop_names[0]}."
            )
        else:
            claims.append("No feedback loops detected (acyclic structure).")

    # DAG-specific: confirm acyclicity, or report cycle-detected
    # readiness failure if the substrate isn't projectable to a DAG.
    if model_type == "dag":
        from latris.operations.readiness import assess_readiness

        dag_readiness = assess_readiness("dag", root=paths.root)
        cycle_gaps = [g for g in dag_readiness.gaps if g.gap_type == "cycle_detected"]
        if cycle_gaps:
            substrate_loops = find_all_loops(causal_edges(substrate.edges))
            claims.append(
                f"DAG readiness FAILS: substrate contains "
                f"{len(substrate_loops)} cycle(s). The substrate is not "
                "projectable to a valid DAG view without dropping or "
                "redirecting edges."
            )
        else:
            claims.append("DAG structure confirmed (acyclic by readiness gate).")

    # Add any recorded structural findings
    findings = _load_findings(paths, model_type)
    structural = [f for f in findings if f.category == "structure"]
    if structural:
        claims.extend([f.statement for f in structural[:5]])

    return claims


def _extract_key_findings(model_type: str, paths) -> list[str]:
    """Top findings + key structural properties."""
    from latris.operations.graph_analysis import (
        causal_edges,
        compute_centrality,
        find_all_loops,
    )
    from latris.schema import Substrate

    substrate = load_model(Substrate, paths.conceptual_yaml)
    claims: list[str] = []

    # Centrality and loop participation read causal edges only —
    # non-causal kinds inflate degrees and create phantom loops.
    causal = causal_edges(substrate.edges)
    if substrate.entities and causal:
        centrality = compute_centrality(substrate.entities, causal)
        # Top 3 by betweenness
        by_betweenness = sorted(centrality, key=lambda c: c.betweenness, reverse=True)
        entity_labels = {e.id: e.label for e in substrate.entities}
        if by_betweenness:
            top = by_betweenness[:3]
            top_names = [
                f"{entity_labels.get(c.entity_id, c.entity_id[:8])} (betweenness: {c.betweenness:.2f})" for c in top
            ]
            claims.append(f"Most central nodes: {', '.join(top_names)}.")

        # Highest degree
        by_degree = sorted(centrality, key=lambda c: c.degree_total, reverse=True)
        if by_degree:
            top_deg = by_degree[0]
            claims.append(
                f"Highest connectivity: {entity_labels.get(top_deg.entity_id, '')} "
                f"({top_deg.degree_total} connections)."
            )

    # Loop participation
    if model_type in ("cld", "fcm") and causal:
        loops = find_all_loops(causal)
        if loops:
            from latris.operations.graph_analysis import compute_loop_participation

            participation = compute_loop_participation(substrate.entities, loops)
            multi_loop = [p for p in participation if p.loop_count > 1]
            if multi_loop:
                entity_labels = {e.id: e.label for e in substrate.entities}
                top_part = sorted(multi_loop, key=lambda p: p.loop_count, reverse=True)[:3]
                names = [f"{entity_labels.get(p.entity_id, '')} ({p.loop_count} loops)" for p in top_part]
                claims.append(f"Nodes in multiple loops: {', '.join(names)}.")

    # Add recorded findings (ranked)
    findings = _load_findings(paths, model_type)
    if findings:
        priority_cats: list[FindingCategory] = ["inference", "sensitivity", "structure"]
        accepted = [f for f in findings if f.maturity == "approved"]
        drafts = [f for f in findings if f.maturity == "proposed"]
        ranked = accepted + drafts

        def sort_key(f: Finding) -> int:
            try:
                return priority_cats.index(f.category)
            except ValueError:
                return len(priority_cats)

        ranked.sort(key=sort_key)
        claims.extend([f.statement for f in ranked[:5]])

    if not claims:
        claims = ["Model structure is minimal — add more entities and relationships."]
    return claims


def _extract_sensitivity(model_type: str, paths) -> list[str]:
    """Structural sensitivity — centrality, leverage points, loop participation."""
    from latris.operations.graph_analysis import (
        causal_edges,
        compute_centrality,
        find_all_loops,
    )
    from latris.schema import Substrate

    substrate = load_model(Substrate, paths.conceptual_yaml)
    claims: list[str] = []

    causal = causal_edges(substrate.edges)
    if substrate.entities and causal:
        centrality = compute_centrality(substrate.entities, causal)
        entity_labels = {e.id: e.label for e in substrate.entities}

        # Frame the betweenness ranking differently depending on whether
        # the graph has loops. On an acyclic graph, betweenness ranks the
        # mediating layer between source(s) and sink(s) — that's topology,
        # not dynamic leverage. Capability-run reviewers correctly flagged
        # the "highest leverage" framing as overclaim on DAGs.
        has_loops = bool(find_all_loops(causal))

        by_betweenness = sorted(centrality, key=lambda c: c.betweenness, reverse=True)
        if by_betweenness and by_betweenness[0].betweenness > 0:
            top = by_betweenness[:3]
            if has_loops:
                claims.append("Highest leverage nodes (by betweenness centrality):")
            else:
                claims.append(
                    "Top structural mediators (by betweenness centrality; "
                    "graph is acyclic, so this primarily reflects topology):"
                )
            for c in top:
                claims.append(f"  - {entity_labels.get(c.entity_id, c.entity_id[:8])}: {c.betweenness:.3f}")

        # Degree distribution — are there bottlenecks?
        degrees = [c.degree_total for c in centrality]
        if degrees:
            avg_degree = sum(degrees) / len(degrees)
            max_degree = max(degrees)
            if max_degree > avg_degree * 2:
                hub = max(centrality, key=lambda c: c.degree_total)
                claims.append(
                    f"Structural bottleneck: {entity_labels.get(hub.entity_id, '')} "
                    f"has {hub.degree_total} connections (avg: {avg_degree:.1f})."
                )

    # Add recorded sensitivity findings
    findings = _load_findings(paths, model_type)
    sensitivity = [f for f in findings if f.category == "sensitivity"]
    if sensitivity:
        claims.extend([f.statement for f in sensitivity[:5]])

    if not claims:
        claims = ["Insufficient model structure for sensitivity analysis."]
    return claims


def _extract_assumptions(model_type: str, paths) -> list[str]:
    """Claims from the assumptions log."""
    from latris.schema import AssumptionLog

    assumptions_path = paths.assumptions_yaml
    if not assumptions_path.exists():
        return ["No assumptions recorded."]
    log = load_model(AssumptionLog, assumptions_path)
    if not log.entries:
        return ["No assumptions recorded."]
    claims = [a.statement for a in log.entries[:10]]
    # Also check for limitation-related findings
    findings = _load_findings(paths, model_type)
    diagnostics = [f for f in findings if f.category == "diagnostics"]
    if diagnostics:
        claims.extend([f"Diagnostic: {f.statement}" for f in diagnostics[:5]])
    return claims


def _extract_evidence_gaps(model_type: str, paths) -> list[str]:
    """Cross-reference evidence coverage against entities.

    Reports linked vs supported separately. A "linked" element has at least
    one EvidenceLink; a "supported" element has at least one link with
    ``support_verdict == "supports"``. Conflating these inflates apparent
    coverage when most links are unverified title-only inferences.
    """
    from latris.schema import EvidenceLinkSet, Substrate

    substrate = load_model(Substrate, paths.conceptual_yaml)
    evidence_path = paths.evidence_links_yaml
    evidence = load_model(EvidenceLinkSet, evidence_path) if evidence_path.exists() else EvidenceLinkSet()

    linked_ids = {e.target_id for e in evidence.entries}
    supported_ids = {e.target_id for e in evidence.entries if e.support_verdict == "supports"}
    all_entity_ids = {e.id for e in substrate.entities}
    all_edge_ids = {e.id for e in substrate.edges}
    all_ids = all_entity_ids | all_edge_ids

    total = len(all_ids)
    linked = len(all_ids & linked_ids)
    supported = len(all_ids & supported_ids)
    uncited = all_ids - linked_ids

    claims = [
        f"Evidence coverage: {linked}/{total} elements have at least one evidence link "
        f"({supported}/{total} verified as supporting)."
    ]
    if uncited:
        entity_labels = {e.id: e.label for e in substrate.entities}
        uncited_entities = [eid for eid in uncited if eid in all_entity_ids]
        if uncited_entities:
            names = [entity_labels.get(eid, eid[:12]) for eid in uncited_entities[:5]]
            claims.append(
                f"Entities without evidence: {', '.join(names)}"
                + (f" (+{len(uncited_entities) - 5} more)" if len(uncited_entities) > 5 else "")
            )
    return claims


def _extract_evidence_coverage(model_type: str, paths) -> list[str]:
    """Cross-reference audit: uncited elements AND unused references."""
    from latris.schema import EvidenceLinkSet, ReferenceLibrary, Substrate

    substrate = load_model(Substrate, paths.conceptual_yaml)
    evidence_path = paths.evidence_links_yaml
    evidence = load_model(EvidenceLinkSet, evidence_path) if evidence_path.exists() else EvidenceLinkSet()
    refs = load_model(ReferenceLibrary, paths.references_yaml) if paths.references_yaml.exists() else ReferenceLibrary()

    entity_labels = {e.id: e.label for e in substrate.entities}
    all_entity_ids = {e.id for e in substrate.entities}
    all_edge_ids = {e.id for e in substrate.edges}
    all_ids = all_entity_ids | all_edge_ids

    # Elements without evidence — split linked vs supported (verified). A
    # link with support_verdict != "supports" is a proposed citation, not
    # verified backing; report the two figures separately so the partner
    # reviewer knows what proportion of the model is actually grounded.
    evidence_target_ids = {e.target_id for e in evidence.entries}
    supported_target_ids = {e.target_id for e in evidence.entries if e.support_verdict == "supports"}
    uncited_ids = all_ids - evidence_target_ids
    cited_count = len(all_ids) - len(uncited_ids)
    supported_count = len(all_ids & supported_target_ids)

    claims = [
        f"Element coverage: {cited_count}/{len(all_ids)} model elements have evidence links "
        f"({supported_count} verified as supporting; {cited_count - supported_count} unverified)."
    ]

    if uncited_ids:
        uncited_entities = [eid for eid in uncited_ids if eid in all_entity_ids]
        if uncited_entities:
            names = [entity_labels.get(eid, eid[:12]) for eid in uncited_entities[:5]]
            claims.append(
                f"Uncited entities: {', '.join(names)}"
                + (f" (+{len(uncited_entities) - 5} more)" if len(uncited_entities) > 5 else "")
            )

    # References not linked to any element. EvidenceLink joins to References
    # via `bibkey`, not by Reference.id — comparing the two means joining on
    # bibkey on both sides.
    bibkeys_used = {e.bibkey for e in evidence.entries}
    all_bibkeys = {r.bibkey for r in refs.entries} if refs.entries else set()
    unused_bibkeys = all_bibkeys - bibkeys_used
    if refs.entries:
        claims.append(
            f"Reference usage: {len(all_bibkeys) - len(unused_bibkeys)}/{len(all_bibkeys)} "
            "references linked to model elements."
        )
    if unused_bibkeys:
        unused_titles = [r.title for r in refs.entries if r.bibkey in unused_bibkeys and r.title][:3]
        if unused_titles:
            claims.append(
                f"Unused references: {'; '.join(unused_titles)}"
                + (f" (+{len(unused_bibkeys) - 3} more)" if len(unused_bibkeys) > 3 else "")
            )

    return claims


def _extract_answer(model_type: str, paths) -> list[str]:
    """Claims grounding the answer: modelling question + structural insights + findings."""
    from latris.operations.graph_analysis import (
        causal_edges,
        classify_loop,
        compute_centrality,
        find_all_loops,
    )
    from latris.schema import Substrate

    foundation = load_model(ProjectFoundation, paths.project_yaml)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    claims = [f"Modelling question: {foundation.statement}"]

    entity_labels = {e.id: e.label for e in substrate.entities}
    # Structural analytics must use causal edges only — decision_rule /
    # governance edges represent policy structure, not feedback mechanism,
    # and including them inflates loop counts (capability-run inflation bug).
    causal = causal_edges(substrate.edges)

    # Key structural insights relevant to answering the question
    if model_type in ("cld", "fcm") and causal:
        polarity_path = paths.view_attribute_path(model_type, "polarity")
        polarity_map: dict[str, str] = {}
        if polarity_path.exists():
            from latris.schema import PolaritySet

            pol_set = load_model(PolaritySet, polarity_path)
            polarity_map = {e.target_id: e.value for e in pol_set.entries if e.attribute == "polarity"}

        loops = find_all_loops(causal)
        if loops:
            classified = [classify_loop(loop, polarity_map) for loop in loops]
            r_loops = [loop for loop in classified if loop.classification == "R"]
            b_loops = [loop for loop in classified if loop.classification == "B"]
            if r_loops:
                claims.append(f"{len(r_loops)} reinforcing loop(s) may drive escalation or growth.")
            if b_loops:
                claims.append(f"{len(b_loops)} balancing loop(s) provide natural stabilisation.")

    # Most central nodes as key factors
    if substrate.entities and causal:
        centrality = compute_centrality(substrate.entities, causal)
        top_3 = sorted(centrality, key=lambda c: c.betweenness, reverse=True)[:3]
        if top_3 and top_3[0].betweenness > 0:
            names = [entity_labels.get(c.entity_id, "") for c in top_3]
            claims.append(f"Key factors in the system: {', '.join(names)}.")

    # Recorded inference findings
    findings = _load_findings(paths, model_type)
    inference = [f for f in findings if f.category == "inference"]
    if inference:
        claims.extend([f.statement for f in inference[:5]])

    return claims


def _extract_implications(model_type: str, paths) -> list[str]:
    """Claims about intervention points — leverage nodes + recommendation findings."""
    from latris.operations.graph_analysis import causal_edges, compute_centrality
    from latris.schema import Substrate

    substrate = load_model(Substrate, paths.conceptual_yaml)
    claims: list[str] = []

    # Centrality is a structural metric — restrict to causal edges so
    # decision_rule / governance edges don't inflate betweenness.
    causal = causal_edges(substrate.edges)

    # High-betweenness nodes are intervention leverage points
    if substrate.entities and causal:
        centrality = compute_centrality(substrate.entities, causal)
        entity_labels = {e.id: e.label for e in substrate.entities}
        by_betweenness = sorted(centrality, key=lambda c: c.betweenness, reverse=True)
        if by_betweenness and by_betweenness[0].betweenness > 0:
            top = by_betweenness[:3]
            claims.append("Potential intervention leverage points (high betweenness):")
            for c in top:
                claims.append(f"  - {entity_labels.get(c.entity_id, c.entity_id[:8])}")

    # Recorded recommendation findings
    findings = _load_findings(paths, model_type)
    recs = [f for f in findings if f.category == "recommendations"]
    if recs:
        claims.extend([f.statement for f in recs[:5]])

    if not claims:
        claims = ["Model structure identified — interpret centrality and loops to identify intervention points."]
    return claims


def _extract_confidence(model_type: str, paths) -> list[str]:
    """Compute confidence indicators from evidence density and finding maturity."""
    from latris.schema import EvidenceLinkSet, Substrate

    substrate = load_model(Substrate, paths.conceptual_yaml)
    evidence_path = paths.evidence_links_yaml
    evidence = load_model(EvidenceLinkSet, evidence_path) if evidence_path.exists() else EvidenceLinkSet()

    total_elements = len(substrate.entities) + len(substrate.edges)
    # Links cover an element if at least one EvidenceLink targets it.
    # Supported coverage requires support_verdict == "supports" — i.e. the
    # source was actually read and the claim was backed. Reporting only the
    # linked-percentage rewards title-only citation stuffing.
    linked_elements = len({e.target_id for e in evidence.entries})
    supported_elements = len({e.target_id for e in evidence.entries if e.support_verdict == "supports"})
    linked_pct = int(100 * linked_elements / max(total_elements, 1))
    supported_pct = int(100 * supported_elements / max(total_elements, 1))

    findings = _load_findings(paths, model_type)
    accepted = len([f for f in findings if f.maturity == "approved"])
    total_findings = len(findings)
    maturity_pct = int(100 * accepted / max(total_findings, 1)) if total_findings else 0

    claims = [
        f"Evidence coverage: {linked_pct}% of model elements have evidence links "
        f"({supported_pct}% verified as supporting; "
        f"{linked_pct - supported_pct}% unverified or proposed).",
        f"Finding maturity: {accepted}/{total_findings} findings approved ({maturity_pct}%).",
    ]

    if supported_pct < 50:
        claims.append(
            "Low verified-support coverage — interpretation rests largely on "
            "unverified proposed links and should be treated as preliminary."
        )
    if maturity_pct < 50 and total_findings > 0:
        claims.append("Most findings are still in draft — peer review recommended before reporting.")

    return claims


def _extract_open_questions(model_type: str, paths) -> list[str]:
    """Claims from open questions and diagnostic findings."""
    from latris.schema import QuestionLog

    questions_path = paths.questions_yaml
    claims: list[str] = []

    if questions_path.exists():
        log = load_model(QuestionLog, questions_path)
        open_qs = [q for q in log.entries if q.disposition == "open"]
        if open_qs:
            claims.extend([f"Open question: {q.question}" for q in open_qs[:6]])

    findings = _load_findings(paths, model_type)
    diagnostics = [f for f in findings if f.category == "diagnostics"]
    if diagnostics:
        claims.extend([f"Diagnostic: {f.statement}" for f in diagnostics[:4]])

    if not claims:
        claims = ["No open questions or diagnostic issues recorded."]
    return claims


# ── Helpers ─────────────────────────────────────────────────────────────


def _find_section(store: InterpretationStore, section_id: str) -> InterpretSection:
    """Find a section by ID or raise ValueError."""
    for section in store.sections:
        if section.id == section_id:
            return section
    raise ValueError(f"Interpretation section not found: {section_id!r}")
