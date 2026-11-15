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
            # New sections start with their claims, so prose can be checked
            # against them straight away (no separate refresh-claims step).
            section.claims = extract_claims(spec.section_type, model_type, root=paths.root)
            section.model_commit = git.head_sha(paths.root)
            section.generation_state = "claims_only"
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
    claims = extractor(model_type, paths)
    # What recorded runs show (simulations, scenarios, uncertainty, loops, queries).
    from latris.operations.result_claims import claims_by_section

    extra = claims_by_section(model_type, paths).get(section_type, [])
    if extra:
        placeholders = ("Insufficient model structure", "No open questions, challenges")
        claims = [c for c in claims if not c.startswith(placeholders)] + extra
    return claims


def refresh_claims(
    section_id: str,
    *,
    root: Path | None = None,
) -> tuple[InterpretSection, str]:
    """Re-extract claims for a section. Prose then shows as stale if they changed (``is_stale``)."""
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


def _prose_verb(source: str, written_by_agent: bool) -> str:
    if source != "ai":
        return "Edit"
    return "Write (AI agent)" if written_by_agent else "Generate"


def update_prose(
    section_id: str,
    prose: str,
    *,
    source: str = "human-edit",
    written_by_agent: bool = False,
    root: Path | None = None,
) -> tuple[InterpretSection, str]:
    """Update prose for a section. Appends to version history.

    ``written_by_agent`` marks AI prose an agent wrote and set directly
    (``interpret set-prose --by ai``) rather than prose Latris generated, so
    the commit says "Write", not "Generate".
    """
    paths = require_project(root)
    store = load_interpretation(root=paths.root)

    section = _find_section(store, section_id)
    section.prose = prose
    section.updated_at = now_utc()

    # Prose is written against the model as it is now: refresh the claims
    # and keep them, so a later change to the model shows the prose is out
    # of date (``InterpretSection.is_stale``), whoever wrote it.
    section.claims = extract_claims(section.section_type, section.model_type, root=paths.root)
    section.claims_at_generation = list(section.claims)
    section.generation_state = "generated" if source == "ai" else "edited"

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
        subject=f"{_prose_verb(source, written_by_agent)} interpretation: {section.section_type}",
        root=paths.root,
    )
    return section, sha


# ── Private claim extractors ────────────────────────────────────────────


def _load_findings(paths, model_type: str | None = None) -> list[Finding]:
    """Load findings, optionally filtered by model_type."""
    from latris.operations.findings import list_findings

    return list_findings(model_type=model_type, root=paths.root)


def _coverage_ids(substrate, paths=None) -> tuple[set[str], str]:
    """The elements evidence coverage is measured over, and their name.

    Links are the model's claims, so coverage is "how many links have a
    source". Factors are named things, not claims; counting them too made a
    well-sourced model look thin (11 of 16 links became 11 of 28). Before
    any link exists, factors are all there is to cover. Links marked
    ``by-definition`` (e.g. departures reduce the number of volunteers)
    need no source, so they aren't counted.
    """
    edge_ids = {e.id for e in substrate.edges}
    if edge_ids:
        return edge_ids - (_by_definition_ids(paths) if paths is not None else set()), "links"
    return {e.id for e in substrate.entities}, "factors"


def _by_definition_ids(paths) -> set[str]:
    from latris.schema import ConfidenceSet

    if not paths.confidence_yaml.exists():
        return set()
    return {e.target_id for e in load_model(ConfidenceSet, paths.confidence_yaml).entries if e.value == "by-definition"}


def _element_names(substrate, ids: list[str]) -> list[str]:
    """Readable names for factors and links (``A → B``)."""
    labels = {e.id: e.label for e in substrate.entities}
    edges = {e.id: e for e in substrate.edges}
    out = []
    for eid in ids:
        if eid in edges:
            e = edges[eid]
            out.append(f"{labels.get(e.from_id, e.from_id[:12])} → {labels.get(e.to_id, e.to_id[:12])}")
        else:
            out.append(labels.get(eid, eid[:12]))
    return out


def _for_ids(evidence) -> set[str]:
    """Targets with at least one source *for* them (contradicting sources don't cover a claim)."""
    return {e.target_id for e in evidence.entries if e.target_id is not None and not e.is_against}


def _supported_ids(evidence) -> set[str | None]:
    """Targets with a source checked and found to support them."""
    return {e.target_id for e in evidence.entries if e.support_verdict == "supports" and not e.is_against}


def _contested(substrate, evidence) -> list[str]:
    """``"A → B: 2 sources for, 1 against (tuohy2015)"`` for each claim with sources against it."""
    against: dict[str, list[str]] = {}
    for e in evidence.entries:
        if e.target_id and e.is_against:
            against.setdefault(e.target_id, []).append(e.bibkey)
    out = []
    for target_id, keys in against.items():
        n_for = sum(1 for e in evidence.entries if e.target_id == target_id and not e.is_against)
        name = _element_names(substrate, [target_id])[0]
        out.append(
            f"{name}: {n_for} source{'s' if n_for != 1 else ''} for, {len(keys)} against ({', '.join(sorted(keys))})"
        )
    return sorted(out)


def _feedback(substrate, paths) -> list:
    """Causal links plus stock-and-flow feedback (loops through stocks count; see operations/feedback.py)."""
    from latris.operations.feedback import feedback_edges

    return feedback_edges(substrate.edges, paths)


def _sd_polarity(substrate, paths) -> dict[str, str]:
    from latris.operations.feedback import link_polarity

    return link_polarity(substrate.edges, paths)


def _outcome_ids(paths, model_type: str) -> set[str]:
    """Factors given the ``outcome`` role in this view (``latris view role``)."""
    if model_type == "sd":
        from latris.operations import sd as sd_ops

        outcome = sd_ops.get_settings(root=paths.root).outcome
        return {outcome} if outcome else set()
    if model_type == "theory_of_change":
        from latris.operations import toc

        return {eid for eid, lvl in toc.get_levels(root=paths.root).items() if lvl == "impact"}
    if model_type == "fault_tree":
        from latris.operations import fault_tree

        return {eid for eid, t in fault_tree.get_events(root=paths.root).items() if t == "top_event"}
    if model_type == "bow_tie":
        from latris.operations import bow_tie

        return {eid for eid, t in bow_tie.get_elements(root=paths.root).items() if t == "top_event"}
    if model_type == "event_tree":
        from latris.operations import event_tree

        return {eid for eid, t in event_tree.get_elements(root=paths.root).items() if t == "end_state"}
    path = paths.role_path(model_type)
    if not path.exists():
        return set()
    from latris.schema.roles import RoleSet

    return {e.target_id for e in load_model(RoleSet, path).entries if e.value == "outcome"}


def _leverage_candidates(centrality, causal, outcome_ids: set[str]) -> list:
    """Rank factors many causal paths run through, leaving out outcomes.

    The outcome is what the model explains, not a place to intervene, and a
    factor with no outgoing link can't change anything downstream — both
    are dropped even when betweenness ranks them high.
    """
    has_effect = {e.from_id for e in causal}
    ranked = sorted(centrality, key=lambda c: c.betweenness, reverse=True)
    return [
        c for c in ranked if c.betweenness > 0 and c.entity_id not in outcome_ids and c.entity_id in has_effect
    ]


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

    all_ids, _ = _coverage_ids(substrate, paths)
    total = len(all_ids)
    if total == 0:
        return 0, 0, 1.0

    cited_targets = _for_ids(evidence)
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


# Risk formalisms whose links are logic or barrier lines, not mechanisms: graph centrality over them
# ("factors many causal paths run through") means nothing, so their claims come from their own analyses.
_NO_CENTRALITY = frozenset({"fault_tree", "bow_tie", "event_tree"})


def _toc_claims(paths, section: str) -> list[str]:
    """Theory-of-change claims for one section, from the live pathway analysis."""
    from latris.operations import toc

    payload, _ = toc.check(record=False, root=paths.root)
    pws, on = payload["pathways"], [lk for lk in payload["links"] if lk["on_pathway"]]
    by_status = {s: sum(1 for p in pws if p["status"] == s) for s in ("checked", "cited", "untested", "contested")}
    claims: list[str] = []
    if section == "structure":
        counts = ", ".join(f"{n} {toc.LEVEL_NAMES[lvl].lower()}" for lvl, n in payload["counts"].items() if n)
        if counts:
            claims.append(f"Results chain by level: {counts}.")
        claims.append(toc.describe(payload) + ".")
        leaps = [lk["label"] for lk in on if lk["leap"]]
        if leaps:
            claims.append(f"Links that skip levels, leaving the steps between unstated: {', '.join(leaps[:5])}.")
        if payload["problems"]:
            claims.append(
                f"The results chain is incomplete: {len(payload['problems'])} structure problem(s) "
                f"(e.g. {payload['problems'][0]['label']}: {payload['problems'][0]['message']})"
            )
    elif section == "answer":
        if not pws:
            claims.append("No pathway yet runs from an activity to an impact, so the theory doesn't say how the "
                          "intervention would reach its goal.")
        else:
            claims.append(
                f"Of {len(pws)} pathway(s) from activity to impact, {by_status['checked']} rest entirely on links "
                f"checked against a source; {by_status['cited']} have a link whose sources aren't checked yet, "
                f"{by_status['untested']} a link with no source and {by_status['contested']} a contested link."
            )
            best = [p for p in pws if p["status"] == "checked"]
            if best:
                claims.append(f"Best-supported pathway: {' → '.join(best[0]['path'])}.")
    elif section == "gaps":
        untested = [lk["label"] for lk in on if lk["status"] == "untested"]
        contested = [lk["label"] for lk in on if lk["status"] == "contested"]
        no_assumption = [lk["label"] for lk in on if not lk["assumptions"]]
        if untested:
            claims.append(f"Links on a pathway with no source: {', '.join(untested[:5])}"
                          + (f" (+{len(untested) - 5} more)." if len(untested) > 5 else "."))
        if contested:
            claims.append(f"Links on a pathway with a source against them: {', '.join(contested[:5])}.")
        if no_assumption:
            claims.append(f"{len(no_assumption)} of {len(on)} link(s) on a pathway have no stated assumption "
                          "about why the step should happen.")
    elif section == "implications":
        weak = {}
        for p in pws:
            for name in p["weak_links"]:
                weak[name] = weak.get(name, 0) + 1
        status = {lk["label"]: lk["status"] for lk in on}
        if weak:
            rank = {"contested": 0, "untested": 1, "cited": 2}
            top = sorted(weak.items(), key=lambda kv: (-kv[1], rank.get(status.get(kv[0], ""), 3), kv[0]))[:3]
            claims.append("Links to test first — not yet checked, and on the most pathways:")
            claims += [f"  - {name} ({status.get(name, '?')}; on {n} pathway(s))" for name, n in top]
        elif pws:
            claims.append("Every link on a pathway has been checked against a source.")
    return claims


def _ft_claims(paths, section: str) -> list[str]:
    """Fault-tree claims for one section, from the live analysis."""
    from latris.operations import fault_tree

    p = fault_tree.analyse(root=paths.root)
    claims: list[str] = []
    if p["problems"]:
        if section == "structure":
            claims.append(f"The fault tree is incomplete: {len(p['problems'])} structure problem(s) "
                          f"(e.g. {p['problems'][0]['label']}: {p['problems'][0]['message']})")
        return claims
    if p["error"]:
        return [p["error"]] if section == "structure" else []
    imp = p["importance"]
    if section == "structure":
        c = p["counts"]
        claims.append(f"Fault tree for {p['top']}: {c['intermediate_event']} intermediate event(s), "
                      f"{c['basic_event']} basic and {c['undeveloped_event']} undeveloped event(s).")
        claims.append(fault_tree.describe(p) + ".")
        if p["outside_inputs"]:
            claims.append(f"Left out of the tree (no fault-tree type): {', '.join(p['outside_inputs'][:5])}.")
    elif section == "answer":
        if p["quantified"]:
            claims.append(f"Probability of {p['top']}: {p['probability']['exact']:.3g} (exact, assuming the basic "
                          "events are independent).")
            top = p["cut_sets"][:3]
            if top:
                claims.append("Most likely ways it happens: " + "; ".join(
                    f"{' AND '.join(c['events'])} ({c['probability']:.3g})" for c in top) + ".")
        else:
            claims.append(f"{p['top']} can happen in {p['cut_sets_total']} minimal way(s); it isn't quantified "
                          f"until every basic event has a probability.")
        if p["single_points"]:
            claims.append(f"Single points of failure — one event alone causes {p['top']}: "
                          f"{', '.join(p['single_points'])}.")
    elif section == "sensitivity" and imp:
        claims.append("Basic events by importance (Fussell–Vesely: the share of the top-event probability that "
                      "needs the event):")
        claims += [f"  - {i['event']}: {i['fussell_vesely']:.2f}" + (" (value not verified)" if i["weak"] else "")
                   for i in imp[:5]]
        weak = [i["event"] for i in imp[:3] if i["weak"]]
        if weak:
            claims.append(f"The most important values nobody has verified yet: {', '.join(weak)} — check these first.")
    elif section == "implications":
        if p["single_points"]:
            claims.append(f"Redundancy or a barrier at a single point of failure removes a whole way {p['top']} "
                          f"happens: {', '.join(p['single_points'])}.")
        if imp:
            claims.append("Largest reductions in the top-event probability if these events could not happen "
                          "(Fussell–Vesely):")
            claims += [f"  - {i['event']} ({i['fussell_vesely']:.0%} of the probability)" for i in imp[:3]]
    elif section == "gaps":
        if p["missing_probabilities"]:
            claims.append(f"Basic events without a probability: {', '.join(p['missing_probabilities'][:5])}"
                          + (f" (+{len(p['missing_probabilities']) - 5} more)." if len(p["missing_probabilities"]) > 5
                             else "."))
        unsourced = [i["event"] for i in imp if not i["source"]]
        if unsourced:
            claims.append(f"Probabilities with no stated source: {', '.join(unsourced[:5])}.")
    return claims


def _bt_claims(paths, section: str) -> list[str]:
    """Bow-tie claims for one section, from the live analysis."""
    from latris.operations import bow_tie

    p = bow_tie.analyse(root=paths.root)
    if p["problems"]:
        if section == "structure":
            return [f"The bow-tie is incomplete: {len(p['problems'])} structure problem(s) "
                    f"(e.g. {p['problems'][0]['label']}: {p['problems'][0]['message']})"]
        return []
    f = bow_tie.flags(p)
    claims: list[str] = []
    if section == "structure":
        claims.append(bow_tie.describe(p) + ".")
        if p["hazard"]:
            claims.append(f"Hazard: {p['hazard']}; top event: {p['top']}.")
        if p["outside_inputs"]:
            claims.append(f"Left out of the bow-tie (no bow-tie role): {', '.join(p['outside_inputs'][:5])}.")
    elif section == "answer":
        if f["unprotected"]:
            claims.append(f"Lines with no effective barrier: {', '.join(f['unprotected'])}.")
        if f["single_barrier"]:
            claims.append(f"Lines resting on a single effective barrier: {', '.join(f['single_barrier'])}.")
        if not f["unprotected"] and not f["single_barrier"]:
            claims.append("Every line has at least two effective barriers.")
        if p["quantified"]:
            fr = p["frequency"]
            claims.append(f"Estimated frequency of {p['top']}: {fr['top']:.3g} per year (layer of protection; "
                          "barriers assumed independent).")
            claims.append("Consequences per year: " + "; ".join(f"{c} {v:.3g}" for c, v in fr["consequences"].items())
                          + ".")
    elif section == "sensitivity" and p["quantified"]:
        ranked = [b for b in p["barriers"] if b["raw"] is not None][:5]
        claims.append("Barriers by how much they buy (RAW: how many times more often their side's outcome would "
                      "happen if the barrier always failed):")
        claims += [f"  - {b['barrier']} ({b['side']}): {b['raw']:.3g}" + (" (value not verified)" if b["weak"] else "")
                   for b in ranked]
        weak = [b["barrier"] for b in ranked[:3] if b["weak"]]
        if weak:
            claims.append(f"The barriers that matter most whose failure probability nobody has verified: "
                          f"{', '.join(weak)}.")
    elif section == "implications":
        if f["unprotected"] or f["single_barrier"]:
            claims.append("Where another independent barrier would help most: "
                          + ", ".join(f["unprotected"] + f["single_barrier"]) + ".")
        if f["shared"]:
            claims.append(f"Barriers on more than one line — one failure defeats every line they guard: "
                          f"{', '.join(f['shared'])}.")
        if f["uncontrolled_escalation"]:
            claims.append(f"Escalation factors with no control: {', '.join(f['uncontrolled_escalation'])}.")
        if f["not_in_place"]:
            claims.append(f"Barriers degraded or not in place: {', '.join(f['not_in_place'])}.")
        if f["no_owner"]:
            claims.append(f"Barriers nobody owns: {', '.join(f['no_owner'])}.")
    elif section == "gaps":
        if p["missing"]:
            claims.append(f"Not quantified — missing: {', '.join(p['missing'][:6])}"
                          + (f" (+{len(p['missing']) - 6} more)." if len(p["missing"]) > 6 else "."))
        unsourced = [b["barrier"] for b in p["barriers"] if b["pfd"] is not None and not b["source"]]
        if unsourced:
            claims.append(f"Failure probabilities with no stated source: {', '.join(unsourced[:5])}.")
    return claims


def _et_claims(paths, section: str) -> list[str]:
    """Event-tree claims for one section, from the live analysis."""
    from latris.operations import event_tree

    p = event_tree.analyse(root=paths.root)
    if p["problems"]:
        if section == "structure":
            return [f"The event tree is incomplete: {len(p['problems'])} structure problem(s) "
                    f"(e.g. {p['problems'][0]['label']}: {p['problems'][0]['message']})"]
        return []
    fr = p["frequency"]
    claims: list[str] = []
    if section == "structure":
        claims.append(event_tree.describe(p) + ".")
        claims.append("Headings, in order: " + " → ".join(p["headings"]) + ".")
    elif section == "answer" and p["quantified"]:
        for d in p["end_states"]:
            amount = f"{d['frequency']:.3g} per year" if fr else f"probability {d['probability']:.3g}"
            claims.append(f"{d['end_state']}: {amount}, mostly through {d['dominant']['text']} "
                          f"({d['dominant']['share']:.0%}).")
        if not fr:
            claims.append(f"These are probabilities given that {p['initiator']} happens; give it a frequency for "
                          "rates per year.")
    elif section == "sensitivity" and p["quantified"]:
        weak = sorted({v["heading"] for v in p["values"] if v["weak"]})
        on_top = sorted({h for d in p["end_states"] for r in p["sequences"] if r["n"] == d["dominant"]["n"]
                         for h in r["unverified"]})
        if on_top:
            claims.append(f"Branch probabilities on the dominant sequences that nobody has verified: "
                          f"{', '.join(on_top)} — these move the answer most directly.")
        elif weak:
            claims.append(f"Branch probabilities nobody has verified: {', '.join(weak)}.")
        if fr and fr["weak"]:
            claims.append(f"The frequency of {p['initiator']} scales every result and hasn't been verified.")
    elif section == "implications" and p["quantified"]:
        for d in p["end_states"]:
            claims.append(f"To make {d['end_state']} rarer, look first at sequence #{d['dominant']['n']}: "
                          f"{d['dominant']['text']}.")
    elif section == "gaps":
        if p["missing"]:
            claims.append("Not quantified — missing: " + "; ".join(p["missing"][:5])
                          + (f" (+{len(p['missing']) - 5} more)." if len(p["missing"]) > 5 else "."))
        if not fr:
            claims.append(f"No frequency for {p['initiator']}, so results are conditional probabilities.")
        unsourced = sorted({v["heading"] for v in p["values"] if not v["source"]})
        if unsourced:
            claims.append(f"Branch probabilities with no stated source: {', '.join(unsourced)}.")
    return claims


def _extract_structural_summary(model_type: str, paths) -> list[str]:
    """Claims from model structure — loops, topology, connectivity."""
    from latris.operations.graph_analysis import (
        causal_edges,
        classify_loop,
        find_all_loops,
        group_loop_mechanisms,
        loop_mechanism_summary,
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
        polarity_map = {**_sd_polarity(substrate, paths), **polarity_map}

        loops = find_all_loops(_feedback(substrate, paths))
        if loops:
            classified = [classify_loop(loop, polarity_map) for loop in loops]
            n_mech = len(group_loop_mechanisms(classified))
            counted = f"{n_mech} feedback mechanism(s)" + (
                f" ({len(loops)} loops; loops that share most of their factors count as one mechanism)"
                if n_mech != len(loops)
                else ""
            )
            claims.append(f"{counted}: {loop_mechanism_summary(classified)}.")
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

    if model_type == "theory_of_change":
        claims.extend(_toc_claims(paths, "structure"))
    if model_type == "fault_tree":
        claims.extend(_ft_claims(paths, "structure"))
    if model_type == "bow_tie":
        claims.extend(_bt_claims(paths, "structure"))
    if model_type == "event_tree":
        claims.extend(_et_claims(paths, "structure"))

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
    if substrate.entities and causal and model_type not in _NO_CENTRALITY:
        centrality = compute_centrality(substrate.entities, causal)
        # Top 3 by betweenness, outcomes excluded — same ranking as
        # Sensitivity and Implications, so the sections don't disagree.
        entity_labels = {e.id: e.label for e in substrate.entities}
        top = _leverage_candidates(centrality, causal, _outcome_ids(paths, model_type))[:3]
        if top:
            top_names = [
                f"{entity_labels.get(c.entity_id, c.entity_id[:8])} (betweenness: {c.betweenness:.2f})" for c in top
            ]
            claims.append(f"Factors the most causal paths run through (outcomes excluded): {', '.join(top_names)}.")

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
        loops = find_all_loops(_feedback(substrate, paths))
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

    if model_type == "fault_tree":
        # Importance measures, not graph centrality: what matters is each event's share of the top event.
        claims = _ft_claims(paths, "sensitivity")
        claims.extend(f.statement for f in _load_findings(paths, model_type) if f.category == "sensitivity")
        return claims or ["Give every basic event a probability to rank the events by importance."]
    if model_type == "bow_tie":
        claims = _bt_claims(paths, "sensitivity")
        claims.extend(f.statement for f in _load_findings(paths, model_type) if f.category == "sensitivity")
        return claims or ["Give every threat a frequency and every barrier a failure probability to rank the "
                          "barriers by how much they buy."]
    if model_type == "event_tree":
        claims = _et_claims(paths, "sensitivity")
        claims.extend(f.statement for f in _load_findings(paths, model_type) if f.category == "sensitivity")
        return claims or ["Give every heading its probability to see which values move the result."]

    causal = causal_edges(substrate.edges)
    if substrate.entities and causal:
        centrality = compute_centrality(substrate.entities, causal)
        entity_labels = {e.id: e.label for e in substrate.entities}

        # Frame the betweenness ranking differently depending on whether
        # the graph has loops. On an acyclic graph, betweenness ranks the
        # mediating layer between source(s) and sink(s) — that's topology,
        # not dynamic leverage. Capability-run reviewers correctly flagged
        # the "highest leverage" framing as overclaim on DAGs.
        # SD feedback runs through stocks (flow edges), so it never shows as a causal-edge cycle.
        has_loops = bool(find_all_loops(_feedback(substrate, paths))) or model_type == "sd"

        top = _leverage_candidates(centrality, causal, _outcome_ids(paths, model_type))[:3]
        if top:
            if has_loops:
                claims.append(
                    "Factors the most causal paths run through (betweenness centrality; "
                    "structural, not a measured effect size; outcomes excluded):"
                )
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

    linked_ids = _for_ids(evidence)
    supported_ids = _supported_ids(evidence)
    all_ids, noun = _coverage_ids(substrate, paths)

    total = len(all_ids)
    linked = len(all_ids & linked_ids)
    supported = len(all_ids & supported_ids)
    uncited = all_ids - linked_ids

    claims = [
        f"Evidence coverage: {linked}/{total} {noun} have at least one source "
        f"({supported}/{total} verified as supporting)."
    ]
    if uncited:
        names = _element_names(substrate, sorted(uncited))
        claims.append(
            f"{noun.capitalize()} without a source: {', '.join(names[:5])}"
            + (f" (+{len(names) - 5} more)" if len(names) > 5 else "")
        )
    if model_type == "theory_of_change":
        claims.extend(_toc_claims(paths, "gaps"))
    if model_type == "fault_tree":
        claims.extend(_ft_claims(paths, "gaps"))
    if model_type == "bow_tie":
        claims.extend(_bt_claims(paths, "gaps"))
    if model_type == "event_tree":
        claims.extend(_et_claims(paths, "gaps"))
    return claims


def _extract_evidence_coverage(model_type: str, paths) -> list[str]:
    """Cross-reference audit: uncited elements AND unused references."""
    from latris.schema import EvidenceLinkSet, ReferenceLibrary, Substrate

    substrate = load_model(Substrate, paths.conceptual_yaml)
    evidence_path = paths.evidence_links_yaml
    evidence = load_model(EvidenceLinkSet, evidence_path) if evidence_path.exists() else EvidenceLinkSet()
    refs = load_model(ReferenceLibrary, paths.references_yaml) if paths.references_yaml.exists() else ReferenceLibrary()

    all_ids, noun = _coverage_ids(substrate, paths)

    # Elements without evidence — split linked vs supported (verified). A
    # link with support_verdict != "supports" is a proposed citation, not
    # verified backing; report the two figures separately so the partner
    # reviewer knows what proportion of the model is actually grounded.
    evidence_target_ids = _for_ids(evidence)
    supported_target_ids = _supported_ids(evidence)
    uncited_ids = all_ids - evidence_target_ids
    cited_count = len(all_ids) - len(uncited_ids)
    supported_count = len(all_ids & supported_target_ids)

    claims = [
        f"Coverage: {cited_count}/{len(all_ids)} {noun} have a source "
        f"({supported_count} verified as supporting; {cited_count - supported_count} unverified)."
    ]

    if uncited_ids:
        names = _element_names(substrate, sorted(uncited_ids))
        claims.append(
            f"Uncited {noun}: {', '.join(names[:5])}"
            + (f" (+{len(names) - 5} more)" if len(names) > 5 else "")
        )

    contested = _contested(substrate, evidence)
    if contested:
        claims.append(f"Contested ({len(contested)}): " + "; ".join(contested[:5]))

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
        group_loop_mechanisms,
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
        polarity_map = {**_sd_polarity(substrate, paths), **polarity_map}

        loops = find_all_loops(_feedback(substrate, paths))
        if loops:
            classified = [classify_loop(loop, polarity_map) for loop in loops]
            groups = group_loop_mechanisms(classified)
            r_groups = sum(1 for g in groups if g[0].classification == "R")
            b_groups = sum(1 for g in groups if g[0].classification == "B")
            if r_groups:
                claims.append(f"{r_groups} reinforcing feedback mechanism(s) may drive escalation or growth.")
            if b_groups:
                claims.append(f"{b_groups} balancing feedback mechanism(s) provide natural stabilisation.")

    # Most central nodes as key factors
    if substrate.entities and causal and model_type not in _NO_CENTRALITY:
        centrality = compute_centrality(substrate.entities, causal)
        top_3 = _leverage_candidates(centrality, causal, _outcome_ids(paths, model_type))[:3]
        if top_3:
            names = [entity_labels.get(c.entity_id, "") for c in top_3]
            claims.append(f"Key factors in the system: {', '.join(names)}.")

    if model_type == "theory_of_change":
        claims.extend(_toc_claims(paths, "answer"))
    if model_type == "fault_tree":
        claims.extend(_ft_claims(paths, "answer"))
    if model_type == "bow_tie":
        claims.extend(_bt_claims(paths, "answer"))
    if model_type == "event_tree":
        claims.extend(_et_claims(paths, "answer"))

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

    # In a theory of change the intervention is its activities; what matters is which steps to test.
    if model_type == "theory_of_change":
        claims.extend(_toc_claims(paths, "implications"))
    elif model_type == "fault_tree":
        claims.extend(_ft_claims(paths, "implications"))
    elif model_type == "bow_tie":
        claims.extend(_bt_claims(paths, "implications"))
    elif model_type == "event_tree":
        claims.extend(_et_claims(paths, "implications"))
    # High-betweenness nodes are intervention leverage points
    elif substrate.entities and causal:
        centrality = compute_centrality(substrate.entities, causal)
        entity_labels = {e.id: e.label for e in substrate.entities}
        top = _leverage_candidates(centrality, causal, _outcome_ids(paths, model_type))[:3]
        if top:
            claims.append(
                "Candidate intervention points — factors many causal paths run through "
                "(betweenness; outcomes excluded):"
            )
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

    all_ids, noun = _coverage_ids(substrate, paths)
    total_elements = len(all_ids)
    # Links cover an element if at least one EvidenceLink targets it.
    # Supported coverage requires support_verdict == "supports" — i.e. the
    # source was actually read and the claim was backed. Reporting only the
    # linked-percentage rewards title-only citation stuffing.
    linked_elements = len(all_ids & _for_ids(evidence))
    supported_elements = len(all_ids & _supported_ids(evidence))
    linked_pct = int(100 * linked_elements / max(total_elements, 1))
    supported_pct = int(100 * supported_elements / max(total_elements, 1))

    findings = _load_findings(paths, model_type)
    accepted = len([f for f in findings if f.maturity == "approved"])
    total_findings = len(findings)
    maturity_pct = int(100 * accepted / max(total_findings, 1)) if total_findings else 0

    claims = [
        f"Evidence coverage: {linked_pct}% of {noun} have a source "
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
    contested = _contested(substrate, evidence)
    if contested:
        claims.append(f"Contested — sources disagree on {len(contested)} {noun if len(contested) != 1 else noun[:-1]}:")
        claims.extend(f"  - {c}" for c in contested[:5])

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

    from latris.schema import ChallengeLog, EvidenceLinkSet, Substrate

    substrate = load_model(Substrate, paths.conceptual_yaml)
    if paths.challenges_yaml.exists():
        open_challenges = [c for c in load_model(ChallengeLog, paths.challenges_yaml).entries if c.state == "open"]
        for c in open_challenges[:4]:
            on = f" ({_element_names(substrate, [c.target_id])[0]})" if c.target_id else ""
            claims.append(f"Open challenge{on}: {c.argument}")
    if paths.evidence_links_yaml.exists():
        for c in _contested(substrate, load_model(EvidenceLinkSet, paths.evidence_links_yaml))[:4]:
            claims.append(f"Sources disagree — {c}")

    findings = _load_findings(paths, model_type)
    diagnostics = [f for f in findings if f.category == "diagnostics"]
    if diagnostics:
        claims.extend([f"Diagnostic: {f.statement}" for f in diagnostics[:4]])

    if not claims:
        claims = ["No open questions, challenges or diagnostic issues recorded."]
    return claims


# ── Helpers ─────────────────────────────────────────────────────────────


def _find_section(store: InterpretationStore, section_id: str) -> InterpretSection:
    """Find a section by ID or raise ValueError."""
    for section in store.sections:
        if section.id == section_id:
            return section
    raise ValueError(f"Interpretation section not found: {section_id!r}")


def resolve_section(
    query: str, *, model_type: str | None = None, root: Path | None = None
) -> InterpretSection:
    """Find a section by ID, ID prefix, or section type (e.g. ``answer_to_question``).

    A section type is ambiguous when several model types have one; pass
    ``model_type`` to pick.
    """
    store = load_interpretation(root=root)
    if not store.sections:
        raise ValueError("no interpretation sections — run `latris interpret initialise` first")
    candidates = [s for s in store.sections if model_type is None or s.model_type == model_type]
    for s in candidates:
        if s.id == query:
            return s
    by_type = [s for s in candidates if s.section_type == query]
    by_prefix = [s for s in candidates if len(query) >= 8 and s.id.startswith(query)]
    matches = by_type or by_prefix
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        kinds = ", ".join(sorted({s.model_type for s in matches}))
        raise ValueError(f"{query!r} matches sections for several model types ({kinds}) — pass --model-type")
    known = ", ".join(sorted({s.section_type for s in candidates}))
    raise ValueError(f"no interpretation section {query!r}. Sections: {known}")
