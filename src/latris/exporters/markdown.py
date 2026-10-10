"""Markdown report exporter — a scannable draft a colleague can comment on.

Pulls from every YAML in the project and renders one long Markdown document
organised by concern: model (nodes/edges), evidence, provenance, challenges,
references. Hand-intended as the starting point for a written deliverable.
"""

from __future__ import annotations

from pathlib import Path

from latris.exporters._format import actor_name as _actor_name
from latris.exporters._scope import view_member_ids
from latris.repo import git as git_repo
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import iter_jsonl, load_model
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
_CAUSAL_EDGE_KINDS = frozenset({"causal", "temporal", "decomposition", "conditional"})
_POLICY_EDGE_KINDS = frozenset({"decision_rule", "governance", "definitional"})


def _load_attr_lookup(paths: ProjectPaths):
    descriptions = {(e.target_id, e.attribute): e for e in load_model(DescriptionSet, paths.descriptions_yaml).entries}
    confidence = {(e.target_id, e.attribute): e for e in load_model(ConfidenceSet, paths.confidence_yaml).entries}
    pol_path = paths.view_attribute_path("cld", "polarity")
    pol_set = load_model(PolaritySet, pol_path) if pol_path.exists() else PolaritySet()
    polarity = {(e.target_id, e.attribute): e for e in pol_set.entries}
    return descriptions, confidence, polarity


def render(
    paths: ProjectPaths,
    *,
    pack: str | None = None,
    sections: list[str] | None = None,
    model_type: str | None = None,
) -> str:
    """Render the project as Markdown, optionally filtered by pack or sections.

    When ``model_type`` is given the report is scoped to that formalism: the
    substrate is filtered to the view's members and findings/interpretation are
    filtered to that model type. ``model_type=None`` renders the whole project
    (legacy aggregate behaviour).
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
        load_model(MilestoneLog, paths.milestones_yaml) if paths.milestones_yaml.exists() else MilestoneLog()
    ).entries

    out: list[str] = []

    def _include(section: str) -> bool:
        return included is None or section in included

    # ---------- Header + Narrative Preamble ----------
    if _include("foundation"):
        from latris.exporters.narrative import build_narrative

        narrative = build_narrative(paths, model_type=model_type)
        out.append(f"# {narrative.title}")
        out.append("")
        out.append(narrative.purpose)
        if narrative.boundary:
            out.append("")
            out.append(narrative.boundary)
        out.append("")
        # Pre-modelling intuition (foundation.predictions) — surfaced near
        # the top so reviewers can compare AI-generated findings against
        # the human prior recorded at project initialisation.
        if foundation.predictions.strip():
            out.append("## Pre-modelling intuition")
            out.append("")
            out.append(
                "_Recorded at project initialisation, before any AI analysis. "
                "Use this as a check against the AI-generated answer below._"
            )
            out.append("")
            out.append(foundation.predictions.strip())
            out.append("")
        try:
            head_ts = git_repo.commit_timestamp(
                git_repo.run_git(["rev-parse", "HEAD"], cwd=paths.root).stdout.strip(),
                paths.root,
            )
            out.append(f"_Last updated {head_ts.isoformat()}_")
        except git_repo.GitError:
            pass
        out.append("")

        # Model structure (AI prose or mechanical fallback)
        if narrative.structure_description:
            out.append("## Model Structure\n")
            out.append(narrative.structure_description)
            out.append("")

        # Model history (AI prose or mechanical fallback)
        if narrative.history_summary:
            out.append("## Model History\n")
            out.append(narrative.history_summary)
            out.append("")

    if _include("modelling_approach"):
        out.extend(_render_modelling_approach(paths))

    labels = {n.id: n.label for n in substrate.entities}

    # ---------- Nodes ----------
    if _include("nodes"):
        out.append("## Nodes")
        out.append("")
        if not substrate.entities:
            out.append("_No nodes yet._")
        else:
            out.append("| ID | Kind | Label | Description |")
            out.append("|----|------|-------|-------------|")
            for n in substrate.entities:
                desc = descriptions.get((n.id, "description"))
                desc_txt = _md_escape(desc.value) if desc else ""
                out.append(f"| `{n.id}` | {n.kind} | {_md_escape(n.label)} | {desc_txt} |")
        out.append("")

    # ---------- Edges ----------
    if _include("edges"):
        out.append("## Edges")
        out.append("")
        if not substrate.edges:
            out.append("_No edges yet._")
        else:
            # Split by edge kind so policy / governance / definitional edges
            # don't visually inflate the causal substrate. See
            # schema/substrate.py:27-34 — these kinds look like causal
            # arrows in prose but represent policy or identity links and
            # are excluded from loop / centrality analysis.
            causal_edges = [e for e in substrate.edges if e.kind in _CAUSAL_EDGE_KINDS]
            policy_edges = [e for e in substrate.edges if e.kind in _POLICY_EDGE_KINDS]
            other_edges = [
                e for e in substrate.edges
                if e.kind not in _CAUSAL_EDGE_KINDS and e.kind not in _POLICY_EDGE_KINDS
            ]

            def _emit_edge_table(edges_list) -> None:
                out.append("| ID | Kind | From → To | Polarity | Confidence | Description |")
                out.append("|----|------|-----------|----------|------------|-------------|")
                for e in edges_list:
                    src = labels.get(e.from_id, e.from_id)
                    dst = labels.get(e.to_id, e.to_id)
                    pol = polarity.get((e.id, "polarity"))
                    conf = confidence.get((e.id, "confidence"))
                    desc = descriptions.get((e.id, "description"))
                    out.append(
                        f"| `{e.id}` | {e.kind} | "
                        f"{_md_escape(src)} → {_md_escape(dst)} | "
                        f"{pol.value if pol else ''} | "
                        f"{conf.value if conf else ''} | "
                        f"{_md_escape(desc.value) if desc else ''} |"
                    )

            if causal_edges:
                out.append("### Causal substrate")
                out.append("")
                _emit_edge_table(causal_edges)
                out.append("")
            if policy_edges:
                out.append("### Policy regime")
                out.append("")
                out.append(
                    "_Decision-rule, governance, and definitional edges. "
                    "These describe how the firm responds to outcomes or "
                    "how variables are identity-related; they are "
                    "**excluded from loop and centrality analysis** "
                    "because they are not feedback-bearing mechanisms._"
                )
                out.append("")
                _emit_edge_table(policy_edges)
                out.append("")
            if other_edges:
                out.append("### Other")
                out.append("")
                _emit_edge_table(other_edges)
                out.append("")

    # ---------- Evidence ----------
    if _include("evidence"):
        out.append("## Evidence")
        out.append("")
        if not evidence.entries:
            out.append("_No evidence attached yet._")
        else:
            by_key: dict[str, list] = {}
            for link in evidence.entries:
                by_key.setdefault(link.bibkey, []).append(link)
            for bibkey, links in sorted(by_key.items()):
                out.append(f"### `{bibkey}`")
                out.append("")
                for link in links:
                    target_label = labels.get(link.target_id, link.target_id)
                    # Phase 1 audit axes — replaces the old binary
                    # "human-verified / ai-verified" badge that conflated
                    # who proposed the link with whether the source
                    # supports the claim.
                    audit = (
                        f"by={link.verified_by} · "
                        f"source={link.source_access} · "
                        f"verdict={link.support_verdict}"
                    )
                    note = f" — _{link.notes}_" if link.notes else ""
                    # "existence" is a sentinel attribute meaning the
                    # reference supports the existence/presence of the
                    # entity or edge itself, not one of its sub-fields.
                    # Render without the "/ attribute" suffix in that case.
                    if link.attribute == "existence":
                        out.append(f"- {target_label} ({audit}){note}")
                    else:
                        out.append(f"- {target_label} / **{link.attribute}** ({audit}){note}")
                    if link.quote:
                        out.append(f"  > {link.quote}")
                out.append("")

    if _include("assumptions"):
        out.append("## Assumptions")
        out.append("")
        if not assumptions:
            out.append("_None._")
        else:
            for a in assumptions:
                rationale = f" — _{a.rationale}_" if a.rationale else ""
                out.append(
                    f"- **{_md_escape(a.statement)}**{rationale}  "
                    f"_by {_actor_name(a.authored_by)}, "
                    f"{id_timestamp(a.id).date().isoformat()}_"
                )
        out.append("")

    if _include("decisions"):
        out.append("## Decisions")
        out.append("")
        if not decisions:
            out.append("_None._")
        else:
            for d in decisions:
                out.append(
                    f"- **{_md_escape(d.statement)}** — _{d.rationale}_  "
                    f"_by {_actor_name(d.authored_by)}, "
                    f"{id_timestamp(d.id).date().isoformat()}_"
                )
        out.append("")

    if _include("signoffs"):
        out.append("## Sign-offs")
        out.append("")
        if not signoffs:
            out.append("_None._")
        else:
            for s in signoffs:
                notes = f" — _{s.notes}_" if s.notes else ""
                out.append(
                    f"- **{s.role}** on _{_md_escape(s.scope)}_ — "
                    f"{_actor_name(s.reviewer)}, {s.signed_at.date().isoformat()}"
                    f"{notes}"
                )
        out.append("")

    if _include("sessions"):
        out.append("## Sessions")
        out.append("")
        if not sessions:
            out.append("_None._")
        else:
            for s in sessions:
                attendees = ", ".join(_actor_name(a) for a in s.attendees)
                notes = f" — {s.notes}" if s.notes else ""
                out.append(f"- **{s.held_at.isoformat()}** with {attendees}{notes}")
        out.append("")

    if _include("questions"):
        out.append("## Open questions")
        out.append("")
        open_qs = [q for q in questions if q.disposition == "open"]
        # Defensive filter: drop prompt-engineering meta-questions that
        # leaked from RaiseQuestions / SuggestCitations (a 4DWW capability
        # bug). These are tooling concerns, not project concerns, and
        # should never reach a partner-facing report.
        open_qs = [q for q in open_qs if not _is_meta_question(q.question)]
        if not open_qs:
            out.append("_None._")
        else:
            for q in open_qs:
                out.append(
                    f"- {_md_escape(q.question)} _(raised by "
                    f"{_actor_name(q.raised_by)}, "
                    f"{id_timestamp(q.id).date().isoformat()})_"
                )
        out.append("")

    if _include("exclusions"):
        out.append("## Exclusions")
        out.append("")
        if not exclusions:
            out.append("_None._")
        else:
            for e in exclusions:
                out.append(
                    f"- **{_md_escape(e.statement)}** — _{e.rationale}_  "
                    f"_by {_actor_name(e.authored_by)}, "
                    f"{id_timestamp(e.id).date().isoformat()}_"
                )
        out.append("")

    if _include("predictions"):
        out.append("## Predictions")
        out.append("")
        if not predictions:
            out.append("_None._")
        else:
            for p in predictions:
                out.append(
                    f"- **{_md_escape(p.statement)}** _(horizon: {p.horizon}; "
                    f"status: {p.resolution})_  "
                    f"_by {_actor_name(p.authored_by)}, "
                    f"{id_timestamp(p.id).date().isoformat()}_"
                )
        out.append("")

    if _include("challenges"):
        out.append("## Challenges")
        out.append("")
        if not challenges:
            out.append("_None raised._")
        else:
            open_cs = [c for c in challenges if c.state == "open"]
            closed_cs = [c for c in challenges if c.state != "open"]
            out.append("### Open")
            out.append("")
            if not open_cs:
                out.append("_None._")
            else:
                for c in open_cs:
                    target_label = labels.get(c.target_id, c.target_id)
                    attr = f"/{c.target_attribute}" if c.target_attribute else ""
                    out.append(
                        f"- **{target_label}{attr}**: {_md_escape(c.argument)}  "
                        f"_(opened by {_actor_name(c.opened_by)}, "
                        f"{id_timestamp(c.id).date().isoformat()})_"
                    )
            out.append("")
            out.append("### Resolved")
            out.append("")
            if not closed_cs:
                out.append("_None._")
            else:
                for c in closed_cs:
                    target_label = labels.get(c.target_id, c.target_id)
                    attr = f"/{c.target_attribute}" if c.target_attribute else ""
                    rationale = f" — _{c.resolution_rationale}_" if c.resolution_rationale else ""
                    out.append(
                        f"- **{target_label}{attr}** → `{c.state}`"
                        f"{rationale}  _({_md_escape(c.argument)}, "
                        f"{_actor_name(c.opened_by)}, "
                        f"{id_timestamp(c.id).date().isoformat()})_"
                    )
            out.append("")

    if _include("references"):
        out.append("## References")
        out.append("")
        if not references:
            out.append("_None._")
        else:
            for r in sorted(references, key=lambda r: r.bibkey):
                authors = ", ".join(r.authors) if r.authors else ""
                year = f"({r.year})" if r.year else ""
                bits = [x for x in [authors, year, f"*{r.title}*"] if x]
                line = f"- **`{r.bibkey}`** — {'. '.join(bits)}."
                if r.doi:
                    line += f" DOI: {r.doi}"
                if r.url:
                    line += f" · <{r.url}>"
                out.append(line)
        out.append("")

    if _include("elicitations"):
        out.append("## Elicitation Sessions")
        out.append("")
        if not elicit_sessions:
            out.append("_None._")
        else:
            for s in elicit_sessions:
                experts = ", ".join(e.name for e in s.experts) if s.experts else "none listed"
                targets = (
                    ", ".join(f"{labels.get(t.target_id, t.target_id)}/{t.attribute}" for t in s.target_attributes)
                    if s.target_attributes
                    else "none"
                )
                notes = f" — _{s.notes}_" if s.notes else ""
                out.append(
                    f"- **{s.held_at.isoformat()}** — {s.protocol.name} "
                    f"(facilitated by {s.facilitator.name}; "
                    f"experts: {experts}; targets: {targets}; "
                    f"phase: {s.phase}){notes}"
                )
        out.append("")

    if _include("datasets"):
        out.append("## Datasets")
        out.append("")
        if not datasets:
            out.append("_None registered._")
        else:
            out.append("| Name | Source | Rows | Columns | Description |")
            out.append("|------|--------|------|---------|-------------|")
            for d in datasets:
                cols = len(d.columns) if d.columns else "?"
                rows = d.rows if d.rows is not None else "?"
                out.append(
                    f"| {_md_escape(d.name)} | {d.source_type} | {rows} | {cols} | {_md_escape(d.description)} |"
                )
        out.append("")

    if _include("data_actions"):
        out.append("## Data Actions")
        out.append("")
        # Collect actions from per-dataset log files.
        all_actions = []
        for d in datasets:
            log_path = paths.data_action_log(d.id)
            if log_path.exists():
                log = load_model(DataActionLog, log_path)
                for a in log.entries:
                    all_actions.append((d.name, a))
        if not all_actions:
            out.append("_No data actions recorded._")
        else:
            out.append("| Dataset | Action | Summary | Date |")
            out.append("|---------|--------|---------|------|")
            for dname, a in all_actions:
                out.append(
                    f"| {_md_escape(dname)} | {a.kind} | "
                    f"{_md_escape(a.summary)} | "
                    f"{id_timestamp(a.id).date().isoformat()} |"
                )
        out.append("")

    if _include("analyses"):
        out.append("## Analysis Runs")
        out.append("")
        if not analysis_runs:
            out.append("_None._")
        else:
            out.append("| Purpose | Algorithm | Run by | Date | Summary |")
            out.append("|---------|-----------|--------|------|---------|")
            for r in analysis_runs:
                out.append(
                    f"| {r.purpose} | {_md_escape(r.algorithm)} | "
                    f"{_actor_name(r.run_by)} | "
                    f"{id_timestamp(r.id).date().isoformat()} | "
                    f"{_md_escape(r.output_summary)} |"
                )
        out.append("")

    if _include("findings"):
        # Client/publication packs only show approved findings.
        visible_maturities = {"proposed", "reviewed", "approved"}
        if pack == "client" or pack == "publication":
            visible_maturities = {"approved"}

        visible = [f for f in all_findings if f.maturity in visible_maturities]

        out.append("## Findings")
        out.append("")
        if not visible:
            out.append("_No findings recorded._")
        else:
            for cat in FINDING_CATEGORIES:
                cat_findings = [f for f in visible if f.category == cat]
                if not cat_findings:
                    continue
                out.append(f"### {cat.title()}")
                out.append("")
                for f in cat_findings:
                    draft_marker = " _(proposed)_" if f.maturity == "proposed" else ""
                    date_str = id_timestamp(f.id).date().isoformat()
                    out.append(
                        f"- **{_md_escape(f.statement)}**{draft_marker}  _({f.model_type}, {f.maturity}, {date_str})_"
                    )
                    if f.detail:
                        for line in f.detail.splitlines():
                            out.append(f"  {_md_escape(line)}")
                out.append("")
        out.append("")

    if _include("interpretation"):
        out.extend(_render_interpretation(paths, model_type=model_type))

    if _include("milestones"):
        out.append("## Milestones")
        out.append("")
        if not milestones:
            out.append("_None._")
        else:
            milestone_dates = git_repo.commit_timestamp_many(
                [m.commit_sha for m in milestones], paths.root
            )
            for m in milestones:
                notes = f" — _{m.notes}_" if m.notes else ""
                date = milestone_dates.get(m.commit_sha)
                date_str = date.date().isoformat() if date else "—"
                out.append(
                    f"- **{_md_escape(m.name)}** ({m.maturity}) — "
                    f"by {_actor_name(m.created_by)}, "
                    f"{date_str}{notes}"
                )
        out.append("")

    return "\n".join(out)


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


def _render_interpretation(paths: ProjectPaths, *, model_type: str | None = None) -> list[str]:
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
    scoped_sections = [
        s for s in store.sections if model_type is None or s.model_type == model_type
    ]
    if not scoped_sections:
        return []

    out: list[str] = ["## Interpretation", ""]

    # Render in registry order so the report flows logically
    # (Structural Summary → Key Findings → ... → Open Questions)
    section_order = list(INTERPRET_SECTION_REGISTRY.keys())
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
            heading_suffix = f" ({s.model_type.upper()})" if model_type is None and multi else ""
            out.append(f"### {title}{heading_suffix}")
            out.append("")

            if s.prose:
                # Prose is already Markdown — render verbatim, indented
                # paragraphs preserved.
                out.append(s.prose.rstrip())
                out.append("")
            elif s.claims:
                out.append("_AI prose not generated yet — claims only:_")
                out.append("")
            else:
                out.append("_Not yet populated._")
                out.append("")

            if s.claims:
                out.append("**Claims (from analysis):**")
                out.append("")
                for c in s.claims:
                    out.append(f"- {_md_escape(c)}")
                out.append("")

            state_marker = {
                "empty": "empty",
                "claims_only": "claims only",
                "generated": "AI-generated",
                "edited": "human-edited",
            }.get(s.generation_state, s.generation_state)
            out.append(f"_State: {state_marker} · last updated {s.updated_at.date().isoformat()}_")
            out.append("")

    return out


def write(
    paths: ProjectPaths,
    target: Path,
    *,
    pack: str | None = None,
    model_type: str | None = None,
) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(paths, pack=pack, model_type=model_type), encoding="utf-8", newline="")
    return target
