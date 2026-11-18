"""Markdown report exporter — a scannable draft a colleague can comment on.

Pulls from every YAML in the project and renders one long Markdown document
organised by concern: model (nodes/edges), evidence, provenance, challenges,
references. Hand-intended as the starting point for a written deliverable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any

from latris.exporters._format import BADGE_TEXT as _BADGE_TEXT
from latris.exporters._format import BADGE_URL as _BADGE_URL
from latris.exporters._format import actor_name as _actor_name
from latris.exporters._scope import view_member_ids
from latris.repo import git as git_repo
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import iter_jsonl, load_model, load_model_or_default
from latris.schema import (
    FINDING_CATEGORIES,
    AnalysisRun,
    AssumptionLog,
    ChallengeLog,
    ConfidenceSet,
    DataActionLog,
    DatasetLibrary,
    DecisionLog,
    DescriptionSet,
    ElicitationLog,
    ElicitationSession,
    EvidenceLinkSet,
    ExclusionLog,
    MilestoneLog,
    PolaritySet,
    PredictionLog,
    ProjectFoundation,
    QuestionLog,
    ReferenceLibrary,
    SessionLog,
    SignoffLog,
    Substrate,
)
from latris.schema.ids import id_timestamp


def _md_escape(text: str) -> str:
    """Escape pipes and angle brackets so table cells don't break layout."""
    return text.replace("|", "\\|").replace("\n", " ")


# Phrases that mark a "question" as being about the prompt/tooling rather
# than the project. Matching is case-insensitive substring. Keep this
# list narrow — false positives on real domain questions are worse than
# letting a stray meta-question through.
_META_QUESTION_MARKERS = (
    "tier-0",
    "tier 0",
    "source extract",
    "source content was empty",
    "as per instructions",
    "full_text_excerpt",
    "general knowledge of the paper titles",
    "ground your rationale",
    "tier-0 content",
)


def _is_meta_question(question: str) -> bool:
    """True if the question is about prompt/tooling internals, not the model."""
    lower = question.lower()
    return any(marker in lower for marker in _META_QUESTION_MARKERS)


# Edge-kind grouping for the rendered Edges section. Mirrors the comment
# at schema/substrate.py:27-34 — causal/temporal/decomposition/conditional
# carry mechanism; decision_rule/governance/definitional are policy or
# identity links and are excluded from loop / centrality analysis.
_READER_PACKS = frozenset({"client", "publication"})
# Interpretation sections a reader pack opens with.
# Where a reader pack's interpretation splits: the answer above, the rest
# (after the diagram) below. Never reaches the output.
_INTERPRETATION_REST = "<!-- interpretation continues -->"
# Findings before what to do about them (a board reads what was found, then the implications).
_ANSWER_FIRST = ("answer_to_question", "key_findings", "implications", "confidence_assessment", "open_questions")

_CAUSAL_EDGE_KINDS = frozenset({"causal", "temporal", "decomposition", "conditional"})
_POLICY_EDGE_KINDS = frozenset({"decision_rule", "governance", "definitional"})


# Evidence audit axes in words a reader understands (the raw values stay
# in the data and the JSON outputs).
_AUDIT_TEXT = {
    ("by", "human"): "attached by a person",
    ("by", "ai"): "attached by an AI",
    ("source", "title_only"): "from the source's title",
    ("source", "abstract"): "from the abstract",
    ("source", "full_text_chunk"): "from an extract of the text",
    ("source", "full_text"): "from the full text",
    ("verdict", "unverified"): "not yet checked against the source",
    ("verdict", "supports"): "checked: the source supports it",
    ("verdict", "contradicts"): "checked: the source contradicts it",
    ("verdict", "confirmed_against"): "checked: the source does argue against it",
    ("quote", "found"): "quote found in the stored text",
    ("quote", "not_found"): "quote not found in the stored text",
    ("verdict", "orthogonal"): "checked: on topic but doesn't address it",
    ("verdict", "insufficient_extract"): "checked: the extract was too short to tell",
}


def _audit_text(key: str, value: str) -> str:
    return _AUDIT_TEXT.get((key, value), f"{key}={value}")


# Columns a table can do without: dropped when every cell is blank, and
# (for "Kind") when every row says the same thing — a column of "causal"
# under "Causal substrate" tells the reader nothing.
_OPTIONAL_COLUMNS = {"Kind", "Polarity", "Why", "Confidence", "Description"}


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    keep = [
        i
        for i, h in enumerate(headers)
        if h not in _OPTIONAL_COLUMNS
        or (any(r[i] for r in rows) and not (h == "Kind" and len({r[i] for r in rows}) == 1))
    ]
    lines = ["| " + " | ".join(headers[i] for i in keep) + " |", "|" + "|".join("---" for _ in keep) + "|"]
    lines.extend("| " + " | ".join(r[i] for i in keep) + " |" for r in rows)
    return lines


def _short_citation(ref) -> str:
    """'Smith & Lee (2021), *Title*' — for headings that would otherwise be a bare key."""
    surnames = [a.split(",")[0].strip() for a in (ref.authors or []) if a.strip()]
    who = (
        surnames[0] if len(surnames) == 1
        else f"{surnames[0]} & {surnames[1]}" if len(surnames) == 2
        else f"{surnames[0]} et al." if surnames
        else ""
    )
    year = f" ({ref.year})" if ref.year else ""
    lead = f"{who}{year}, " if who else (f"{ref.year}, " if ref.year else "")
    return f"{lead}*{_md_escape(ref.title)}*"


def _load_attr_lookup(paths: ProjectPaths):
    descriptions = {(e.target_id, e.attribute): e for e in load_model(DescriptionSet, paths.descriptions_yaml).entries}
    confidence = {(e.target_id, e.attribute): e for e in load_model(ConfidenceSet, paths.confidence_yaml).entries}
    pol_path = paths.view_attribute_path("cld", "polarity")
    pol_set = load_model_or_default(PolaritySet, pol_path)
    polarity = {(e.target_id, e.attribute): e for e in pol_set.entries}
    return descriptions, confidence, polarity


@dataclass
class _Report:
    """What every report section reads: the loaded project, the options, and the lines so far."""

    out: list[str]
    include: Callable[[str], bool]
    begin: Callable[[str], None]
    all_findings: list[Any]
    analysis_runs: list[Any]
    app_link: bool
    assumptions: list[Any]
    challenges: list[Any]
    chart_markers: bool
    confidence: Any
    datasets: list[Any]
    decisions: list[Any]
    descriptions: dict[Any, Any]
    elicit_sessions: list[Any]
    evidence: EvidenceLinkSet
    exclusions: list[Any]
    foundation: ProjectFoundation
    labels: dict[str, str]
    milestones: list[Any]
    model_type: str | None
    narrative: Any
    pack: str | None
    paths: ProjectPaths
    polarity: Any
    predictions: list[Any]
    questions: list[Any]
    references: list[Any]
    report_url: str | None
    sessions: list[Any]
    show_ids: bool
    signoffs: list[Any]
    substrate: Substrate


def render(
    paths: ProjectPaths,
    *,
    pack: str | None = None,
    sections: list[str] | None = None,
    model_type: str | None = None,
    report_url: str | None = None,
    ai: bool = True,
    app_link: bool = False,
    chart_markers: bool = False,
) -> str:
    """Render the project as Markdown, optionally filtered by pack or sections.

    When ``model_type`` is given the report is scoped to that formalism: the
    substrate is filtered to the view's members and findings/interpretation are
    filtered to that model type. ``model_type=None`` renders the whole project
    (legacy aggregate behaviour). ``report_url`` adds a link to the hosted
    copy of this report in the footer. ``ai=False`` writes the narrative
    preamble without attempting an AI call. ``chart_markers=True`` puts a
    fenced ``latris-chart`` block before each result for the app to draw.
    """
    from latris.exporters.packs import get_pack

    included = None
    if sections:
        included = set(sections)
    elif pack:
        included = set(get_pack(pack).sections)
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    members = view_member_ids(paths, model_type)
    if members is not None:
        substrate.entities = [e for e in substrate.entities if e.id in members]
        substrate.edges = [e for e in substrate.edges if e.id in members]
    descriptions, confidence, polarity = _load_attr_lookup(paths)
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    references = load_model(ReferenceLibrary, paths.references_yaml).entries
    assumptions = load_model(AssumptionLog, paths.assumptions_yaml).entries
    decisions = load_model(DecisionLog, paths.decisions_yaml).entries
    signoffs = load_model(SignoffLog, paths.signoffs_yaml).entries
    sessions = load_model(SessionLog, paths.sessions_yaml).entries
    questions = load_model(QuestionLog, paths.questions_yaml).entries
    exclusions = load_model(ExclusionLog, paths.exclusions_yaml).entries
    predictions = load_model(PredictionLog, paths.predictions_yaml).entries
    challenges = load_model(ChallengeLog, paths.challenges_yaml).entries
    datasets = load_model(DatasetLibrary, paths.data_datasets_yaml).entries
    elicit_index = load_model(ElicitationLog, paths.elicitations_yaml)
    elicit_sessions: list[ElicitationSession] = []
    for entry in elicit_index.entries:
        session_path = paths.elicitations_dir / entry.file_path
        if session_path.exists():
            elicit_sessions.append(load_model(ElicitationSession, session_path))
    from latris.schema.findings import Finding

    analysis_runs = list(iter_jsonl(AnalysisRun, paths.analysis_runs_jsonl))
    all_findings = list(iter_jsonl(Finding, paths.findings_jsonl))
    if model_type is not None:
        all_findings = [f for f in all_findings if f.model_type == model_type]
    milestones = (
        load_model_or_default(MilestoneLog, paths.milestones_yaml)
    ).entries

    labels = {n.id: n.label for n in substrate.entities}
    # Edges read as "A → B" wherever they're named (evidence, challenges).
    for e in substrate.edges:
        labels.setdefault(e.id, f"{labels.get(e.from_id, e.from_id)} → {labels.get(e.to_id, e.to_id)}")

    out: list[str] = []
    # Packs written for people outside the modelling work hide internal IDs;
    # the rest keep them so a reader can act on a row with the CLI.
    show_ids = pack not in _READER_PACKS

    def _include(section: str) -> bool:
        return included is None or section in included

    # Each section's lines start at a marker; the report is reassembled in
    # the pack's own section order at the end (reader packs lead with the
    # answer, not the change log).
    starts: list[tuple[str, int]] = []

    def _begin(section: str) -> None:
        starts.append((section, len(out)))

    narrative = None
    if _include("foundation") or _include("structure") or _include("history"):
        from latris.exporters.narrative import build_narrative

        narrative = build_narrative(paths, model_type=model_type, ai=ai)

    rep = _Report(
        out=out, include=_include, begin=_begin,
        all_findings=all_findings,
        analysis_runs=analysis_runs,
        app_link=app_link,
        assumptions=assumptions,
        challenges=challenges,
        chart_markers=chart_markers,
        confidence=confidence,
        datasets=datasets,
        decisions=decisions,
        descriptions=descriptions,
        elicit_sessions=elicit_sessions,
        evidence=evidence,
        exclusions=exclusions,
        foundation=foundation,
        labels=labels,
        milestones=milestones,
        model_type=model_type,
        narrative=narrative,
        pack=pack,
        paths=paths,
        polarity=polarity,
        predictions=predictions,
        questions=questions,
        references=references,
        report_url=report_url,
        sessions=sessions,
        show_ids=show_ids,
        signoffs=signoffs,
        substrate=substrate,
    )
    for name, section in _SECTIONS:
        _begin(name)
        section(rep)

    out = _in_pack_order(out, starts, pack=pack, sections=sections)

    # ---------- Footer badge ----------
    out.append("---")
    out.append("")
    if report_url:
        out.append(f"View this report online: {report_url}")
        out.append("")
    out.append(f"*{_BADGE_TEXT} — {_BADGE_URL}*")
    out.append("")

    return "\n".join(out)


def _section_foundation(rep: _Report) -> None:
    # ---------- Header + Narrative Preamble ----------
    if rep.include("foundation"):
        rep.out.append(f"# {rep.narrative.title}")
        rep.out.append("")
        rep.out.append(rep.narrative.purpose)
        # The context the model was built in: who it's for, the situation
        # behind the question, and what's in scope.
        if rep.foundation.audience.strip():
            rep.out.append("")
            rep.out.append(f"**Prepared for:** {rep.foundation.audience.strip()}")
        if rep.foundation.background.strip():
            rep.out.append("")
            rep.out.append(f"**Background.** {rep.foundation.background.strip()}")
        if rep.narrative.boundary:
            rep.out.append("")
            rep.out.append(rep.narrative.boundary)
        rep.out.append("")
        # Pre-modelling intuition (foundation.predictions) — surfaced near
        # the top so readers can compare the person's own expectation with
        # the model's answer.
        if rep.foundation.predictions.strip():
            rep.out.append("## Pre-modelling intuition")
            rep.out.append("")
            rep.out.append(
                "_What the person who asked for this model expected the answer to be, in their own "
                "words. Compare it with the answer in this report._"
            )
            rep.out.append("")
            rep.out.append(rep.foundation.predictions.strip())
            rep.out.append("")
        try:
            head_ts = git_repo.commit_timestamp(
                git_repo.run_git(["rev-parse", "HEAD"], cwd=rep.paths.root).stdout.strip(),
                rep.paths.root,
            )
            utc = head_ts.astimezone(UTC)
            rep.out.append(f"_Last updated {utc.day} {utc:%b %Y, %H:%M} UTC_")
        except git_repo.GitError:
            pass
        rep.out.append("")


def _section_structure(rep: _Report) -> None:
    # Model structure (AI prose or mechanical fallback)
    if rep.include("structure") and rep.narrative.structure_description:
        rep.out.append("## Model Structure\n")
        rep.out.append(rep.narrative.structure_description)
        rep.out.append("")


def _section_history(rep: _Report) -> None:
    # Model history — the change log (AI prose or mechanical fallback)
    if rep.include("history") and rep.narrative.history_summary:
        rep.out.append("## Model History\n")
        rep.out.append(rep.narrative.history_summary)
        rep.out.append("")


def _section_diagram(rep: _Report) -> None:
    # ---------- Diagram (Mermaid sketch) ----------
    if rep.include("diagram"):
        from latris.exporters import mermaid

        def _emit_diagram(source: str, legend: list[str]) -> None:
            rep.out.append("```mermaid")
            rep.out.append(source.rstrip("\n"))
            rep.out.append("```")
            rep.out.append("")
            if legend:
                rep.out.append("Feedback loops:")
                rep.out.append("")
                rep.out.extend(f"- {line}" for line in legend)
                rep.out.append("")

        drew = False
        if rep.model_type is None:
            # The aggregate report: one sketch per formalism in use, each drawn by
            # the formalism's own hook (docs/engineering/REPORT-SURFACE.md). The
            # whole-substrate sketch follows only when factors sit outside every
            # formalism in use; when no formalism is in use at all, it is the diagram.
            parts = _formalism_diagrams(rep.paths)
            if parts:
                rep.out.append("## Diagram")
                rep.out.append("")
                for title, source, legend in parts:
                    rep.out.append(f"### {title}")
                    rep.out.append("")
                    _emit_diagram(source, legend)
                drew = True
                if _has_unmapped_edges(rep.paths):
                    whole = mermaid.render(rep.paths)
                    if whole:
                        rep.out.append("### Whole model")
                        rep.out.append("")
                        _emit_diagram(whole, mermaid.loop_legend(rep.paths))
        if not drew:
            diagram = mermaid.render(rep.paths, model_type=rep.model_type)
            if diagram:
                rep.out.append("## Diagram")
                rep.out.append("")
                _emit_diagram(diagram, mermaid.loop_legend(rep.paths, model_type=rep.model_type))
                drew = True
        if drew:
            link = _app_link(rep.paths, rep.model_type) if rep.app_link and not rep.report_url else None
            if link:
                rep.out.append(
                    f"**[Open the interactive report]({link})** — the full figure, result charts and "
                    "interpretation in the Latris app. This link is the shareable report; the model travels "
                    "inside it."
                )
                rep.out.append("")


def _section_results(rep: _Report) -> None:
    # ---------- Results (recorded simulations, uncertainty runs, queries) ----------
    if rep.include("results"):
        from latris.exporters.results import render_results

        rep.out.extend(
            render_results(
                rep.paths,
                model_types=[rep.model_type] if rep.model_type else None,
                chart_markers=rep.chart_markers,
                show_ids=rep.show_ids,
            )
        )


def _section_modelling_approach(rep: _Report) -> None:
    if rep.include("modelling_approach"):
        rep.out.extend(_render_modelling_approach(rep.paths))


def _section_methods(rep: _Report) -> None:
    # Methods and foundations — generated from the foundations registry so the
    # methods cited here match what the scoped Results section actually shows.
    if rep.include("methods"):
        from latris.operations.foundations import render_methods_section

        rep.out.extend(render_methods_section(rep.paths, model_type=rep.model_type))


def _section_nodes(rep: _Report) -> None:
    # ---------- Nodes ----------
    if rep.include("nodes"):
        rep.out.append("## Nodes")
        rep.out.append("")
        if not rep.substrate.entities:
            rep.out.append("_No nodes yet._")
        else:
            rows = []
            for n in rep.substrate.entities:
                desc = rep.descriptions.get((n.id, "description"))
                rows.append(
                    ([f"`{n.id}`"] if rep.show_ids else [])
                    + [n.kind, _md_escape(n.label), _md_escape(desc.value) if desc else ""]
                )
            rep.out.extend(_table((["ID"] if rep.show_ids else []) + ["Kind", "Label", "Description"], rows))
        rep.out.append("")


def _section_edges(rep: _Report) -> None:
    # ---------- Edges ----------
    if rep.include("edges"):
        rep.out.append("## Edges")
        rep.out.append("")
        if not rep.substrate.edges:
            rep.out.append("_No edges yet._")
        else:
            # Split by edge kind so policy / governance / definitional edges
            # don't visually inflate the causal substrate. See
            # schema/substrate.py:27-34 — these kinds look like causal
            # arrows in prose but represent policy or identity links and
            # are excluded from loop / centrality analysis.
            causal_edges = [e for e in rep.substrate.edges if e.kind in _CAUSAL_EDGE_KINDS]
            policy_edges = [e for e in rep.substrate.edges if e.kind in _POLICY_EDGE_KINDS]
            other_edges = [
                e for e in rep.substrate.edges
                if e.kind not in _CAUSAL_EDGE_KINDS and e.kind not in _POLICY_EDGE_KINDS
            ]

            def _emit_edge_table(edges_list) -> None:
                rows = []
                for e in edges_list:
                    src = rep.labels.get(e.from_id, e.from_id)
                    dst = rep.labels.get(e.to_id, e.to_id)
                    pol = rep.polarity.get((e.id, "polarity"))
                    why = getattr(pol, "rationale", None) if pol else None
                    conf = rep.confidence.get((e.id, "confidence"))
                    desc = rep.descriptions.get((e.id, "description"))
                    # Agents often set both to the same causal story; say it once.
                    desc_txt = desc.value if desc and desc.value.strip() != (why or "").strip() else ""
                    rows.append(
                        ([f"`{e.id}`"] if rep.show_ids else [])
                        + [
                            e.kind,
                            f"{_md_escape(src)} → {_md_escape(dst)}",
                            pol.value if pol else "",
                            _md_escape(why) if why else "",
                            conf.value if conf else "",
                            _md_escape(desc_txt),
                        ]
                    )
                headers = ["Kind", "From → To", "Polarity", "Why", "Confidence", "Description"]
                rep.out.extend(_table((["ID"] if rep.show_ids else []) + headers, rows))

            if causal_edges:
                rep.out.append("### Causal substrate")
                rep.out.append("")
                _emit_edge_table(causal_edges)
                rep.out.append("")
            if policy_edges:
                rep.out.append("### Policy regime")
                rep.out.append("")
                rep.out.append(
                    "_Decision-rule, governance, and definitional edges. "
                    "These describe how the firm responds to outcomes or "
                    "how variables are identity-related; they are "
                    "**excluded from loop and centrality analysis** "
                    "because they are not feedback-bearing mechanisms._"
                )
                rep.out.append("")
                _emit_edge_table(policy_edges)
                rep.out.append("")
            if other_edges:
                rep.out.append("### Other")
                rep.out.append("")
                _emit_edge_table(other_edges)
                rep.out.append("")


def _section_contested(rep: _Report) -> None:
    # ---------- Evidence ----------
    if rep.include("contested"):
        rep.out.extend(_render_contested(rep.evidence, rep.challenges, rep.labels, rep.references))


def _section_evidence(rep: _Report) -> None:
    if rep.include("evidence"):
        rep.out.append("## Evidence")
        rep.out.append("")
        if not rep.evidence.entries:
            rep.out.append("_No evidence attached yet._")
        else:
            by_key: dict[str, list] = {}
            for link in rep.evidence.entries:
                by_key.setdefault(link.bibkey, []).append(link)
            ref_by_key = {r.bibkey: r for r in rep.references}

            def _tags(link) -> list[tuple[str, str]]:
                # A source against a claim is marked "against" (below); its
                # check, like any other, says what the source was read as.
                tags = [("by", link.verified_by), ("source", link.source_access)]
                verdict = link.support_verdict
                if link.stance == "against" and verdict == "contradicts":
                    verdict = "confirmed_against"
                tags.append(("verdict", verdict))
                if link.quote:
                    # Legacy checks (before 0.7.7) never looked the quote up.
                    tags.append(("quote", "found" if link.quote_verified else "not_found"))
                return tags

            # The same audit tag on every line is noise: a tag every citation
            # shares is stated once, and lines keep only the ones that differ.
            values: dict[str, set[str]] = {}
            for link in rep.evidence.entries:
                for k, v in _tags(link):
                    values.setdefault(k, set()).add(v)
            shared = {k: next(iter(v)) for k, v in values.items() if len(v) == 1}
            if shared:
                common = " · ".join(_audit_text(k, v) for k, v in shared.items())
                rep.out.append(f"_Every citation below: {common}._")
                rep.out.append("")
            for bibkey, links in sorted(by_key.items()):
                ref = ref_by_key.get(bibkey)
                cite = _short_citation(ref) if ref else ""
                # Reader packs name the source, not its internal key.
                if cite and not rep.show_ids:
                    rep.out.append(f"### {cite}")
                else:
                    rep.out.append(f"### `{bibkey}` — {cite}" if cite else f"### `{bibkey}`")
                rep.out.append("")
                for link in links:
                    target_label = rep.labels.get(link.target_id, link.target_id)
                    # Phase 1 audit axes — replaces the old binary
                    # "human-verified / ai-verified" badge that conflated
                    # who proposed the link with whether the source
                    # supports the claim.
                    own = " · ".join(_audit_text(k, v) for k, v in _tags(link) if k not in shared)
                    audit = f" ({own})" if own else ""
                    if link.is_against:
                        audit = f" — **against**{audit}"
                    note = f" — _{link.notes}_" if link.notes else ""
                    # "existence" is a sentinel attribute meaning the
                    # reference supports the existence/presence of the
                    # entity or edge itself, not one of its sub-fields.
                    # Render without the "/ attribute" suffix in that case.
                    if link.attribute == "existence":
                        rep.out.append(f"- {target_label}{audit}{note}")
                    else:
                        rep.out.append(f"- {target_label} / **{link.attribute}**{audit}{note}")
                    if link.quote:
                        rep.out.append(f"  > {link.quote}")
                rep.out.append("")


def _section_assumptions(rep: _Report) -> None:
    if rep.include("assumptions"):
        rep.out.append("## Assumptions")
        rep.out.append("")
        if not rep.assumptions:
            rep.out.append("_None._")
        else:
            for a in rep.assumptions:
                rationale = f" — _{a.rationale}_" if a.rationale else ""
                rep.out.append(
                    f"- **{_md_escape(a.statement)}**{rationale}  "
                    f"_by {_actor_name(a.authored_by)}, "
                    f"{id_timestamp(a.id).date().isoformat()}_"
                )
        rep.out.append("")


def _section_decisions(rep: _Report) -> None:
    if rep.include("decisions"):
        rep.out.append("## Decisions")
        rep.out.append("")
        if not rep.decisions:
            rep.out.append("_None._")
        else:
            for d in rep.decisions:
                rep.out.append(
                    f"- **{_md_escape(d.statement)}** — _{d.rationale}_  "
                    f"_by {_actor_name(d.authored_by)}, "
                    f"{id_timestamp(d.id).date().isoformat()}_"
                )
        rep.out.append("")


def _section_signoffs(rep: _Report) -> None:
    if rep.include("signoffs"):
        rep.out.append("## Sign-offs")
        rep.out.append("")
        if not rep.signoffs:
            rep.out.append("_None._")
        else:
            for s in rep.signoffs:
                notes = f" — _{s.notes}_" if s.notes else ""
                rep.out.append(
                    f"- **{s.role}** on _{_md_escape(s.scope)}_ — "
                    f"{_actor_name(s.reviewer)}, {s.signed_at.date().isoformat()}"
                    f"{notes}"
                )
        rep.out.append("")


def _section_sessions(rep: _Report) -> None:
    if rep.include("sessions"):
        rep.out.append("## Sessions")
        rep.out.append("")
        if not rep.sessions:
            rep.out.append("_None._")
        else:
            for s in rep.sessions:
                attendees = ", ".join(_actor_name(a) for a in s.attendees)
                notes = f" — {s.notes}" if s.notes else ""
                rep.out.append(f"- **{s.held_at.isoformat()}** with {attendees}{notes}")
        rep.out.append("")


def _section_questions(rep: _Report) -> None:
    if rep.include("questions"):
        rep.out.append("## Open questions")
        rep.out.append("")
        open_qs = [q for q in rep.questions if q.disposition == "open"]
        # Defensive filter: drop prompt-engineering meta-questions that
        # leaked from RaiseQuestions / SuggestCitations (a 4DWW capability
        # bug). These are tooling concerns, not project concerns, and
        # should never reach a partner-facing report.
        open_qs = [q for q in open_qs if not _is_meta_question(q.question)]
        if not open_qs:
            rep.out.append("_None._")
        else:
            for q in open_qs:
                rep.out.append(
                    f"- {_md_escape(q.question)} _(raised by "
                    f"{_actor_name(q.raised_by)}, "
                    f"{id_timestamp(q.id).date().isoformat()})_"
                )
        rep.out.append("")


def _section_exclusions(rep: _Report) -> None:
    if rep.include("exclusions"):
        rep.out.append("## Exclusions")
        rep.out.append("")
        if not rep.exclusions:
            rep.out.append("_None._")
        else:
            for e in rep.exclusions:
                rep.out.append(
                    f"- **{_md_escape(e.statement)}** — _{e.rationale}_  "
                    f"_by {_actor_name(e.authored_by)}, "
                    f"{id_timestamp(e.id).date().isoformat()}_"
                )
        rep.out.append("")


def _section_predictions(rep: _Report) -> None:
    if rep.include("predictions"):
        rep.out.append("## Predictions")
        rep.out.append("")
        if not rep.predictions:
            rep.out.append("_None._")
        else:
            for p in rep.predictions:
                rep.out.append(
                    f"- **{_md_escape(p.statement)}** _(horizon: {p.horizon}; "
                    f"status: {p.resolution})_  "
                    f"_by {_actor_name(p.authored_by)}, "
                    f"{id_timestamp(p.id).date().isoformat()}_"
                )
        rep.out.append("")


def _section_challenges(rep: _Report) -> None:
    if rep.include("challenges"):
        rep.out.append("## Challenges")
        rep.out.append("")
        if not rep.challenges:
            rep.out.append("_None raised._")
        else:
            open_cs = [c for c in rep.challenges if c.state == "open"]
            closed_cs = [c for c in rep.challenges if c.state != "open"]
            rep.out.append("### Open")
            rep.out.append("")
            if not open_cs:
                rep.out.append("_None._")
            else:
                for c in open_cs:
                    target_label = rep.labels.get(c.target_id, c.target_id)
                    attr = f"/{c.target_attribute}" if c.target_attribute else ""
                    rep.out.append(
                        f"- **{target_label}{attr}**: {_md_escape(c.argument)}  "
                        f"_(opened by {_actor_name(c.opened_by)}, "
                        f"{id_timestamp(c.id).date().isoformat()})_"
                    )
            rep.out.append("")
            rep.out.append("### Resolved")
            rep.out.append("")
            if not closed_cs:
                rep.out.append("_None._")
            else:
                for c in closed_cs:
                    target_label = rep.labels.get(c.target_id, c.target_id)
                    attr = f"/{c.target_attribute}" if c.target_attribute else ""
                    rationale = f" — _{c.resolution_rationale}_" if c.resolution_rationale else ""
                    rep.out.append(
                        f"- **{target_label}{attr}** → `{c.state}`"
                        f"{rationale}  _({_md_escape(c.argument)}, "
                        f"{_actor_name(c.opened_by)}, "
                        f"{id_timestamp(c.id).date().isoformat()})_"
                    )
            rep.out.append("")


def _section_references(rep: _Report) -> None:
    if rep.include("references"):
        rep.out.append("## References")
        rep.out.append("")
        if not rep.references:
            rep.out.append("_None._")
        else:
            # Reader packs list sources by author and year, without keys.
            order = (lambda r: r.bibkey) if rep.show_ids else (
                lambda r: ((r.authors or [r.title])[0].lower(), r.year or 0)
            )
            for r in sorted(rep.references, key=order):
                # "Surname, Given" names already hold commas; separate them
                # with semicolons so the list stays readable.
                sep = "; " if any("," in a for a in r.authors or []) else ", "
                authors = sep.join(r.authors) if r.authors else ""
                year = f"({r.year})" if r.year else ""
                # Names ending in an initial ("L.") already close with a stop.
                bits = [x.rstrip(".") for x in [authors, year, f"*{r.title}*"] if x]
                line = f"- **`{r.bibkey}`** — {'. '.join(bits)}." if rep.show_ids else f"- {'. '.join(bits)}."
                if r.doi:
                    line += f" DOI: {r.doi}"
                if r.url:
                    line += f" · <{r.url}>"
                via = next((v for v in rep.references if v.bibkey == r.cited_via), None) if r.cited_via else None
                if via is not None:
                    line += f" _Read as cited in {_short_citation(via)}, not first-hand._"
                rep.out.append(line)
        rep.out.append("")


def _section_elicitations(rep: _Report) -> None:
    if rep.include("elicitations"):
        rep.out.append("## Elicitation Sessions")
        rep.out.append("")
        if not rep.elicit_sessions:
            rep.out.append("_None._")
        else:
            for s in rep.elicit_sessions:
                experts = ", ".join(e.name for e in s.experts) if s.experts else "none listed"
                targets = (
                    ", ".join(f"{rep.labels.get(t.target_id, t.target_id)}/{t.attribute}" for t in s.target_attributes)
                    if s.target_attributes
                    else "none"
                )
                notes = f" — _{s.notes}_" if s.notes else ""
                rep.out.append(
                    f"- **{s.held_at.isoformat()}** — {s.protocol.name} "
                    f"(facilitated by {s.facilitator.name}; "
                    f"experts: {experts}; targets: {targets}; "
                    f"phase: {s.phase}){notes}"
                )
        rep.out.append("")


def _section_datasets(rep: _Report) -> None:
    if rep.include("datasets"):
        rep.out.append("## Datasets")
        rep.out.append("")
        if not rep.datasets:
            rep.out.append("_None registered._")
        else:
            rep.out.append("| Name | Source | Rows | Columns | Description |")
            rep.out.append("|------|--------|------|---------|-------------|")
            for d in rep.datasets:
                cols = len(d.columns) if d.columns else "?"
                rows = d.rows if d.rows is not None else "?"
                rep.out.append(
                    f"| {_md_escape(d.name)} | {d.source_type} | {rows} | {cols} | {_md_escape(d.description)} |"
                )
        rep.out.append("")


def _section_data_actions(rep: _Report) -> None:
    if rep.include("data_actions"):
        rep.out.append("## Data Actions")
        rep.out.append("")
        # Collect actions from per-dataset log files.
        all_actions = []
        for d in rep.datasets:
            log_path = rep.paths.data_action_log(d.id)
            if log_path.exists():
                log = load_model(DataActionLog, log_path)
                for a in log.entries:
                    all_actions.append((d.name, a))
        if not all_actions:
            rep.out.append("_No data actions recorded._")
        else:
            rep.out.append("| Dataset | Action | Summary | Date |")
            rep.out.append("|---------|--------|---------|------|")
            for dname, a in all_actions:
                rep.out.append(
                    f"| {_md_escape(dname)} | {a.kind} | "
                    f"{_md_escape(a.summary)} | "
                    f"{id_timestamp(a.id).date().isoformat()} |"
                )
        rep.out.append("")


def _section_analyses(rep: _Report) -> None:
    if rep.include("analyses"):
        rep.out.append("## Analysis Runs")
        rep.out.append("")
        if not rep.analysis_runs:
            rep.out.append("_None._")
        else:
            rep.out.append("| Purpose | Algorithm | Run by | Date | Summary |")
            rep.out.append("|---------|-----------|--------|------|---------|")
            for r in rep.analysis_runs:
                rep.out.append(
                    f"| {r.purpose} | {_md_escape(r.algorithm)} | "
                    f"{_actor_name(r.run_by)} | "
                    f"{id_timestamp(r.id).date().isoformat()} | "
                    f"{_md_escape(r.output_summary)} |"
                )
        rep.out.append("")


def _section_findings(rep: _Report) -> None:
    if rep.include("findings"):
        # Client/publication packs only show approved findings.
        visible_maturities = {"proposed", "reviewed", "approved"}
        if rep.pack == "client" or rep.pack == "publication":
            visible_maturities = {"approved"}

        visible = [f for f in rep.all_findings if f.maturity in visible_maturities]

        rep.out.append("## Findings")
        rep.out.append("")
        waiting = sum(1 for f in rep.all_findings if f.maturity in {"proposed", "reviewed"} and f not in visible)
        if not visible and waiting:
            rep.out.append(
                f"_{waiting} draft finding{'s are' if waiting != 1 else ' is'} not shown here "
                f"until a person approves {'them' if waiting != 1 else 'it'}._"
            )
        elif not visible:
            rep.out.append("_No findings recorded._")
        else:
            for cat in FINDING_CATEGORIES:
                cat_findings = [f for f in visible if f.category == cat]
                if not cat_findings:
                    continue
                rep.out.append(f"### {cat.title()}")
                rep.out.append("")
                for f in cat_findings:
                    draft_marker = " _(proposed)_" if f.maturity == "proposed" else ""
                    date_str = id_timestamp(f.id).date().isoformat()
                    rep.out.append(
                        f"- **{_md_escape(f.statement)}**{draft_marker}  _({f.model_type}, {f.maturity}, {date_str})_"
                    )
                    if f.detail:
                        for line in f.detail.splitlines():
                            rep.out.append(f"  {_md_escape(line)}")
                rep.out.append("")
        rep.out.append("")


def _section_interpretation(rep: _Report) -> None:
    if rep.include("interpretation"):
        reader = rep.pack in _READER_PACKS
        lines = _render_interpretation(rep.paths, model_type=rep.model_type, answer_first=reader)
        if reader and _INTERPRETATION_REST in lines:
            # Reader packs: the answer stands alone as its own section, and
            # the rest of the interpretation follows the diagram.
            cut = lines.index(_INTERPRETATION_REST)
            rep.out.extend(lines[:cut])
            rep.begin("interpretation_rest")
            rep.out.extend(lines[cut + 1 :])
        else:
            rep.out.extend(line for line in lines if line != _INTERPRETATION_REST)


def _section_milestones(rep: _Report) -> None:
    if rep.include("milestones"):
        rep.out.append("## Milestones")
        rep.out.append("")
        if not rep.milestones:
            rep.out.append("_None._")
        else:
            milestone_dates = git_repo.commit_timestamp_many(
                [m.commit_sha for m in rep.milestones], rep.paths.root
            )
            for m in rep.milestones:
                notes = f" — _{m.notes}_" if m.notes else ""
                date = milestone_dates.get(m.commit_sha)
                date_str = date.date().isoformat() if date else "—"
                rep.out.append(
                    f"- **{_md_escape(m.name)}** ({m.maturity}) — "
                    f"by {_actor_name(m.created_by)}, "
                    f"{date_str}{notes}"
                )
        rep.out.append("")



_SECTIONS: tuple[tuple[str, Callable[[_Report], None]], ...] = (
    ("foundation", _section_foundation),
    ("structure", _section_structure),
    ("history", _section_history),
    ("diagram", _section_diagram),
    ("results", _section_results),
    ("modelling_approach", _section_modelling_approach),
    ("methods", _section_methods),
    ("nodes", _section_nodes),
    ("edges", _section_edges),
    ("contested", _section_contested),
    ("evidence", _section_evidence),
    ("assumptions", _section_assumptions),
    ("decisions", _section_decisions),
    ("signoffs", _section_signoffs),
    ("sessions", _section_sessions),
    ("questions", _section_questions),
    ("exclusions", _section_exclusions),
    ("predictions", _section_predictions),
    ("challenges", _section_challenges),
    ("references", _section_references),
    ("elicitations", _section_elicitations),
    ("datasets", _section_datasets),
    ("data_actions", _section_data_actions),
    ("analyses", _section_analyses),
    ("findings", _section_findings),
    ("interpretation", _section_interpretation),
    ("milestones", _section_milestones),
)


def _render_contested(evidence, challenges, labels: dict[str, str], references) -> list[str]:
    """Links and factors where sources disagree or a challenge is open.

    Nothing (not even a heading) when the model has no disagreement, so
    reader packs don't carry an empty section.
    """
    against: dict[str, list[str]] = {}
    for e in evidence.entries:
        if e.target_id and e.is_against:
            against.setdefault(e.target_id, []).append(e.bibkey)
    open_challenges: dict[str, list[str]] = {}
    for c in challenges:
        if c.state == "open" and c.target_id:
            open_challenges.setdefault(c.target_id, []).append(c.argument)
    targets = sorted(set(against) | set(open_challenges), key=lambda t: labels.get(t, t))
    if not targets:
        return []
    ref_by_key = {r.bibkey: r for r in references}

    def _cite(key: str) -> str:
        ref = ref_by_key.get(key)
        return _short_citation(ref) if ref else f"`{key}`"

    out = ["## Contested links", ""]
    out.append("_Where sources disagree, or someone has challenged the link and it isn't resolved._")
    out.append("")
    for t in targets:
        out.append(f"- **{_md_escape(labels.get(t, t))}**")
        for_keys = sorted(
            {e.bibkey for e in evidence.entries if e.target_id == t and not e.is_against}
        )
        if for_keys:
            out.append(f"  - For: {'; '.join(_cite(k) for k in for_keys)}")
        if t in against:
            out.append(f"  - Against: {'; '.join(_cite(k) for k in sorted(set(against[t])))}")
        for arg in open_challenges.get(t, []):
            out.append(f"  - Open challenge: {_md_escape(arg)}")
    out.append("")
    return out


def _app_link(paths: ProjectPaths, model_type: str | None) -> str | None:
    """A ``latris link`` for this model as it is now, so the report never points at a stale copy."""
    from latris.operations.share_link import make_link

    try:
        return make_link(model_type=model_type, root=paths.root).url
    except (ValueError, OSError):  # e.g. too large to carry in a link
        return None


def _in_pack_order(
    out: list[str], starts: list[tuple[str, int]], *, pack: str | None, sections: list[str] | None
) -> list[str]:
    """Reorder rendered sections to follow the pack's (or caller's) list."""
    from latris.exporters.packs import get_pack

    order = sections or (get_pack(pack).sections if pack else None)
    if not order:
        return out
    if "interpretation" in order:
        # The rest of a split interpretation goes after the diagram when the
        # diagram follows the answer, else straight after the answer.
        after = "diagram" if "diagram" in order[order.index("interpretation") :] else "interpretation"
        if after == "diagram" and "results" in order and order.index("results") == order.index("diagram") + 1:
            after = "results"  # answer → diagram → the numbers behind it → the rest of the interpretation
        order = list(order)
        order.insert(order.index(after) + 1, "interpretation_rest")
    bounds = [*(i for _, i in starts[1:]), len(out)]
    chunks = {key: out[start:end] for (key, start), end in zip(starts, bounds, strict=True)}
    head = out[: starts[0][1]] if starts else []
    ranked = [k for k in order if k in chunks] + [k for k, _ in starts if k not in order]
    return head + [line for k in ranked for line in chunks[k]]


def _used_model_types(paths: ProjectPaths) -> list[str]:
    """Formalisms this project genuinely uses, in model-type-registry order.

    Same test as the methods section (`foundations._uses_formalism`): selected in
    project.yaml, present in the mapping registry, or holding stored
    view-attribute content.
    """
    from latris.operations.foundations import _uses_formalism
    from latris.schema.model_types import list_model_types

    return [s.id for s in list_model_types() if _uses_formalism(paths, s.id)]


def _formalism_diagrams(paths: ProjectPaths) -> list[tuple[str, str, list[str]]]:
    """(display name, mermaid source, loop legend) per used formalism with a drawable diagram."""
    from latris.exporters import mermaid
    from latris.schema.model_types import get_model_type

    parts = []
    seen: set[str] = set()
    for mt in _used_model_types(paths):
        source = mermaid.render(paths, model_type=mt)
        # Two legacy types with no view mappings both draw the whole substrate —
        # show it once (the "Whole model" part covers it via _has_unmapped_entities).
        if source and source not in seen:
            seen.add(source)
            parts.append((get_model_type(mt).display_name, source, mermaid.loop_legend(paths, model_type=mt)))
    return parts


def _draws_whole_substrate(paths: ProjectPaths, model_type: str) -> bool:
    """True if an unscoped formalism's diagram is the generic sketch of the whole model.

    A plugin with its own Mermaid hook (MCDA, ACH, ...) draws only its own elements even with
    no mappings, so it doesn't stand in for the whole model.
    """
    from latris.exporters import mermaid
    from latris.operations import formalisms

    plugin = formalisms.get(model_type)
    if not (plugin and plugin.mermaid):
        return True
    entities, edges, _ = mermaid._scoped(paths, model_type)
    return not plugin.mermaid(paths, entities, edges)


def _has_unmapped_edges(paths: ProjectPaths) -> bool:
    """True if any substrate edge sits outside the views of every formalism in use.

    Edges, not entities: an unmapped node alone draws as an unconnected box, which
    tells the reader nothing (a pure MCDA project has no edges at all).
    """
    substrate = load_model(Substrate, paths.conceptual_yaml)
    mapped: set[str] = set()
    for mt in _used_model_types(paths):
        members = view_member_ids(paths, mt)
        if members is None:
            if _draws_whole_substrate(paths, mt):
                return False  # this formalism's diagram already draws every factor and link
            continue
        mapped |= members
    return any(e.id not in mapped for e in substrate.edges)


def _render_modelling_approach(paths: ProjectPaths) -> list[str]:
    """Render the 'Modelling Approach' section from the ModelChoiceLog — why
    each selected formalism was chosen. Empty list if no choices recorded."""
    from latris.operations.project import current_model_choices
    from latris.schema.model_types import get_model_type

    choices = current_model_choices(root=paths.root)
    if not choices:
        return []

    out: list[str] = ["## Modelling Approach", ""]
    if len(choices) > 1:
        out.append(
            "This question was modelled with more than one formalism to triangulate "
            "the answer; each choice is justified below."
        )
        out.append("")
    for mt_id, choice in choices.items():
        try:
            name = get_model_type(mt_id).display_name
        except ValueError:
            name = mt_id.upper()
        out.append(f"### {_md_escape(name)}")
        out.append("")
        if choice.rationale.strip():
            out.append(_md_escape(choice.rationale.strip()))
        else:
            out.append("_No rationale recorded for this choice._")
        out.append("")
    return out


def _prose_is_stale(section, paths: ProjectPaths) -> bool:
    """The section's prose rests on claims the model no longer gives (see ``InterpretSection.is_stale``)."""
    if not section.prose.strip() or not section.claims_at_generation:
        return False
    from latris.operations.interpret import extract_claims

    try:
        current = extract_claims(section.section_type, section.model_type, root=paths.root)
    except Exception:  # noqa: BLE001 — a report never fails over a staleness check
        current = None
    return section.is_stale(current)


def _render_interpretation(
    paths: ProjectPaths, *, model_type: str | None = None, answer_first: bool = False
) -> list[str]:
    """Render the Interpret-phase sections (Answer, Confidence, Limitations,
    etc) into Markdown lines. Empty list if interpretation.yaml is missing
    or has no sections — keeps the report quiet for projects that haven't
    reached the Interpret phase yet. When ``model_type`` is given, only that
    formalism's sections are rendered (and the model suffix is dropped)."""
    interp_path = paths.interpretation_yaml
    if not interp_path.exists():
        return []
    from latris.operations.interpret_registry import (
        INTERPRET_SECTION_REGISTRY,
        get_section_spec,
    )
    from latris.schema.interpretation import InterpretationStore

    store = load_model(InterpretationStore, interp_path)
    from latris.operations.interpret_registry import MODEL_WIDE

    scoped_sections = [
        s for s in store.sections if model_type is None or s.model_type in (model_type, MODEL_WIDE)
    ]
    if not scoped_sections:
        return []

    out: list[str] = []
    answer_alone = answer_first and any(s.section_type == "answer_to_question" for s in scoped_sections)
    if not answer_alone:
        out += ["## Interpretation", ""]

    # Render in registry order so the report flows logically
    # (Structural Summary → Key Findings → ... → Open Questions). Reader
    # packs lead with the answer, what to do about it and how sure we are.
    section_order = list(INTERPRET_SECTION_REGISTRY.keys())
    if answer_first:
        lead = [t for t in _ANSWER_FIRST if t in section_order]
        section_order = lead + [t for t in section_order if t not in lead]
    by_type: dict[str, list] = {}
    for s in scoped_sections:
        by_type.setdefault(s.section_type, []).append(s)

    for section_type in section_order:
        for s in by_type.get(section_type, []):
            try:
                spec = get_section_spec(s.section_type)
                title = spec.display_name
            except ValueError:
                title = s.section_type.replace("_", " ").title()

            # Disambiguate by model only in the aggregate (unscoped) report.
            multi = len(by_type.get(section_type, [])) > 1 or len(scoped_sections) > 10
            heading_suffix = (
                f" ({s.model_type.upper()})" if model_type is None and multi and s.model_type != MODEL_WIDE else ""
            )
            if answer_alone and section_type == "answer_to_question":
                out.append(f"## {title}{heading_suffix}")
            else:
                if answer_alone and _INTERPRETATION_REST not in out:
                    out += [_INTERPRETATION_REST, "## Interpretation", ""]
                out.append(f"### {title}{heading_suffix}")
            out.append("")

            stale = _prose_is_stale(s, paths)
            if s.prose:
                # Prose is already Markdown — render verbatim, indented
                # paragraphs preserved.
                out.append(s.prose.rstrip())
                out.append("")
                if stale:
                    out.append(
                        "_Out of date: the model has changed since this was written, and what it rests on "
                        "has changed with it._"
                    )
                    out.append("")
            elif s.claims:
                out.append("_AI prose not generated yet — claims only:_")
                out.append("")
            else:
                out.append("_Not yet populated._")
                out.append("")

            # Reader packs: the prose already says it; the claims list is
            # only shown where no prose has been written yet.
            if s.claims and not (answer_first and s.prose):
                out.append("**Claims (from analysis):**")
                out.append("")
                for c in s.claims:
                    # "  - item" claims list the items of the claim before
                    # them; nest them under it, not under an empty bullet.
                    if c.startswith("  - "):
                        out.append(f"  - {_md_escape(c[4:])}")
                    else:
                        out.append(f"- {_md_escape(c)}")
                out.append("")

            state_marker = {
                "empty": "empty",
                "claims_only": "claims only",
                "generated": "AI-generated",
                "edited": "human-edited",
            }.get(s.generation_state, s.generation_state)
            if stale:
                state_marker += ", out of date"
            out.append(f"_State: {state_marker} · last updated {s.updated_at.date().isoformat()}_")
            out.append("")

    return out


def write(
    paths: ProjectPaths,
    target: Path,
    *,
    pack: str | None = None,
    model_type: str | None = None,
    report_url: str | None = None,
    ai: bool = True,
    app_link: bool = False,
) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    text = render(paths, pack=pack, model_type=model_type, report_url=report_url, ai=ai, app_link=app_link)
    target.write_text(text, encoding="utf-8", newline="")
    return target
