"""Build a model from a spec file in one commit (``latris build --spec``).

The spec is checked in full before anything is written — every link end,
citation, target and the outcome must name a factor, link or source that
exists in the project or in the spec — so a mistake leaves the project
untouched. The writes then run through the normal operations inside one
``batch()``, so the result is identical to issuing the commands one by one,
as one commit.

Links are named by their ends, ``"From -> To"``, wherever a spec entry
targets one (assumptions, findings, challenges).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from latris.operations.batch import batch
from latris.repo import git
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model, load_model_from_string
from latris.schema import ProjectFoundation, ReferenceLibrary, Substrate
from latris.schema.build_spec import LINK_ARROWS, BuildSpec, SpecAssumption, SpecCitation


@dataclass
class BuildResult:
    factors: int = 0
    links: list[dict[str, str]] = field(default_factory=list)
    sources: int = 0
    citations: int = 0
    assumptions: int = 0
    questions: int = 0
    findings: int = 0
    challenges: int = 0
    decisions: int = 0
    interpretation: int = 0
    parameters: int = 0  # SD/BN roles, values, equations, tables, uncertainty ranges, scenarios
    analyses: list[str] = field(default_factory=list)  # run ids of the analyses replayed after building
    outcome: str | None = None
    notes: list[str] = field(default_factory=list)  # parts that couldn't be applied, and why
    commit_sha: str = ""


def load_spec(text: str) -> BuildSpec:
    """Parse a YAML or JSON spec (JSON is valid YAML)."""
    return load_model_from_string(BuildSpec, text)


def _citations(items: list[str | SpecCitation]) -> list[SpecCitation]:
    return [SpecCitation(key=c) if isinstance(c, str) else c for c in items]


def _assumptions(items: list[str | SpecAssumption]) -> list[SpecAssumption]:
    return [SpecAssumption(text=a) if isinstance(a, str) else a for a in items]


def split_link(name: str) -> tuple[str, str] | None:
    """``"A -> B"`` → ``("A", "B")``; None when ``name`` isn't a link."""
    for arrow in LINK_ARROWS:
        if arrow in name:
            a, b = name.split(arrow, 1)
            return a.strip(), b.strip()
    return None


def _check(spec: BuildSpec, substrate: Substrate, ref_keys: set[str], model_type: str) -> None:
    """Raise ValueError listing every reference the spec can't resolve."""
    from latris.operations.interpret_registry import INTERPRET_SECTION_REGISTRY

    existing = {e.label.casefold() for e in substrate.entities} | {e.id for e in substrate.entities}
    spec_labels = [f.label for f in spec.factors]
    dupes = sorted({x for x in spec_labels if spec_labels.count(x) > 1})
    known = existing | {label.casefold() for label in spec_labels}
    keys = ref_keys | {s.key for s in spec.sources}
    labels = {e.id: e.label.casefold() for e in substrate.entities}
    link_pairs = {(labels.get(e.from_id), labels.get(e.to_id)) for e in substrate.edges} | {
        (link.from_.casefold(), link.to.casefold()) for link in spec.links
    }
    problems: list[str] = []
    from latris.operations.references import _clean_doi

    for s in spec.sources:
        if s.extract and not (s.extract_url or s.url or s.doi):
            problems.append(f"source {s.key!r}: an extract needs extract_url (or the source's url or doi)")
        if s.cited_via and (s.cited_via == s.key or s.cited_via not in keys):
            problems.append(f"source {s.key!r}: cited_via {s.cited_via!r} isn't another source")
        try:
            _clean_doi(s.doi)
        except ValueError as exc:
            problems.append(f"source {s.key!r}: {exc}")
    if dupes:
        problems.append(f"factor listed twice: {', '.join(dupes)}")
    clash = sorted(label for label in spec_labels if label.casefold() in existing)
    if clash:
        problems.append(f"factor already in the project: {', '.join(clash)}")

    def _known(name: str) -> bool:
        return name.casefold() in known or name in known

    def _target(where: str, name: str | None) -> None:
        if name is None:
            return
        ends = split_link(name)
        if ends is None:
            if not _known(name):
                problems.append(f"{where}: no factor named {name!r}")
        elif (ends[0].casefold(), ends[1].casefold()) not in link_pairs:
            problems.append(f"{where}: no link {name!r}")

    for i, link in enumerate(spec.links, 1):
        for end in (link.from_, link.to):
            if not _known(end):
                problems.append(f"link {i}: no factor named {end!r}")
        if link.from_.casefold() == link.to.casefold():
            problems.append(f"link {i}: a factor can't link to itself")
    for where, items in [(f"factor {f.label!r}", f.sources + f.contradicts) for f in spec.factors] + [
        (f"link {i}", link.sources + link.contradicts) for i, link in enumerate(spec.links, 1)
    ]:
        for c in _citations(items):
            if c.key not in keys:
                problems.append(f"{where}: no source with key {c.key!r} (add it under sources)")
    if spec.outcome and not _known(spec.outcome):
        problems.append(f"outcome: no factor named {spec.outcome!r}")
    if spec.outcome:
        from latris.schema.model_types import get_model_type

        allowed = get_model_type(model_type).allowed_roles
        if allowed and "outcome" not in allowed:
            problems.append(f"outcome: {model_type} has no outcome role (cld, dag and fcm do)")
    for i, a in enumerate(_assumptions(spec.assumptions), 1):
        _target(f"assumption {i}", a.target)
    for i, f in enumerate(spec.findings, 1):
        for t in f.targets:
            _target(f"finding {i}", t)
    for i, c in enumerate(spec.challenges, 1):
        _target(f"challenge {i}", c.target)
    for i, d in enumerate(spec.decisions, 1):
        _target(f"decision {i}", d.target)
    for item in spec.interpretation:
        if item.section not in INTERPRET_SECTION_REGISTRY:
            problems.append(
                f"interpretation: no section {item.section!r} "
                f"(one of: {', '.join(sorted(INTERPRET_SECTION_REGISTRY))})"
            )
    if problems:
        raise ValueError("the spec has problems, nothing was changed:\n- " + "\n- ".join(problems))


def build_from_spec(spec: BuildSpec, *, verified_by: str = "human", root: Path | None = None) -> BuildResult:
    """Apply ``spec`` to the project as one commit."""
    from latris.operations.attributes import set_attribute
    from latris.operations.challenges import open_challenge
    from latris.operations.edges import add_edge
    from latris.operations.evidence import add_evidence
    from latris.operations.findings import record_new_finding
    from latris.operations.nodes import add_node
    from latris.operations.provenance import add_assumption, add_question, log_decision
    from latris.operations.references import add_reference
    from latris.operations.view_attributes import set_view_attribute
    from latris.operations.view_roles import set_role

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    library = (
        load_model(ReferenceLibrary, paths.references_yaml) if paths.references_yaml.exists() else ReferenceLibrary()
    )
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    model_type = spec.model_type or next(iter(foundation.selected_model_types), "cld")
    _check(spec, substrate, {r.bibkey for r in library.entries}, model_type)
    result = BuildResult()
    subject = f"Built model from spec: {len(spec.factors)} factors, {len(spec.links)} links"

    node_ids = {e.label.casefold(): e.id for e in substrate.entities}
    edge_ids = {
        (next(n.label for n in substrate.entities if n.id == e.from_id).casefold(),
         next(n.label for n in substrate.entities if n.id == e.to_id).casefold()): e.id
        for e in substrate.edges
    }

    def _target_id(name: str | None) -> str | None:
        if name is None:
            return None
        ends = split_link(name)
        if ends is None:
            return node_ids.get(name.casefold(), name)
        return edge_ids[(ends[0].casefold(), ends[1].casefold())]

    with batch(paths.root, subject=subject):
        if spec.context:
            from latris.operations.project import set_foundation_field

            for field, value in (("background", spec.context.background), ("audience", spec.context.audience),
                                 ("boundary", spec.context.boundary), ("predictions", spec.context.intuition)):
                if value and value.strip():
                    set_foundation_field(field, value.strip(), root=paths.root)
        # A source read in another goes in after it.
        for s in sorted(spec.sources, key=lambda s: s.cited_via is not None):
            add_reference(
                s.key, s.title, authors=s.authors or None, year=s.year, container=s.container,
                doi=s.doi, url=s.url, notes=s.notes, cited_via=s.cited_via, root=paths.root,
            )
            if s.extract and s.extract.strip():
                from latris.operations.references import set_source_snapshot

                set_source_snapshot(
                    s.key, retrieval_url=s.extract_url or s.url or (f"https://doi.org/{s.doi}" if s.doi else ""),
                    extract=s.extract.strip(), kind=s.extract_kind, root=paths.root,
                )
            result.sources += 1

        def _cite(target: str, attribute: str, items: list[str | SpecCitation], *, against: bool = False) -> None:
            for c in _citations(items):
                add_evidence(
                    target, attribute, c.key, verified_by=verified_by, notes=c.notes,  # type: ignore[arg-type]
                    contradicts=against, root=paths.root,
                )
                result.citations += 1

        for f in spec.factors:
            node, _ = add_node(f.label, kind=f.kind, root=paths.root)
            node_ids[f.label.casefold()] = node.id
            if f.description:
                set_attribute(node.id, "description", f.description, root=paths.root)
            _cite(node.id, "description", f.sources)
            _cite(node.id, "description", f.contradicts, against=True)
            result.factors += 1

        for link in spec.links:
            edge, _ = add_edge(link.from_, link.to, kind=link.kind, root=paths.root)
            edge_ids[(link.from_.casefold(), link.to.casefold())] = edge.id
            if link.polarity:
                set_view_attribute(edge.id, "cld", "polarity", link.polarity, rationale=link.reason, root=paths.root)
            if link.weight is not None:
                set_view_attribute(edge.id, "fcm", "weight", str(link.weight), root=paths.root)
            if link.description:
                set_attribute(edge.id, "description", link.description, root=paths.root)
            if link.confidence:
                set_attribute(edge.id, "confidence", link.confidence, root=paths.root)
            claim = "polarity" if link.polarity else "description"
            _cite(edge.id, claim, link.sources)
            _cite(edge.id, claim, link.contradicts, against=True)
            result.links.append({"id": edge.id, "from": link.from_, "to": link.to})

        if spec.outcome:
            set_role(spec.outcome, model_type, "outcome", root=paths.root)
            result.outcome = spec.outcome
        for a in _assumptions(spec.assumptions):
            add_assumption(a.text, a.rationale, target_id=_target_id(a.target), root=paths.root)
            result.assumptions += 1
        for text in spec.questions:
            add_question(text, root=paths.root)
            result.questions += 1
        for f in spec.findings:
            record_new_finding(
                f.statement, f.category, model_type, detail=f.detail,
                target_ids=[t for t in (_target_id(x) for x in f.targets) if t], root=paths.root,
            )
            result.findings += 1
        for c in spec.challenges:
            open_challenge(_target_id(c.target), c.argument, root=paths.root)
            result.challenges += 1
        for d in spec.decisions:
            log_decision(d.statement, d.rationale, target_id=_target_id(d.target), root=paths.root)
            result.decisions += 1
        default_origin = "ai-proposed" if verified_by == "ai" else "human-direct"
        if spec.sd:
            result.parameters += _apply_sd(spec.sd, default_origin, paths.root)
        if spec.bn:
            result.parameters += _apply_bn(spec.bn, default_origin, paths.root)
        if spec.interpretation:
            _apply_interpretation(spec, model_type, paths.root, result)

    result.commit_sha = git.head_sha(paths.root)
    # Analyses run after the model is built; each is recorded (its own commit) for the report.
    from latris.operations.analysis_replay import run_analysis

    for a in spec.analyses:
        try:
            result.analyses.append(run_analysis(a, root=paths.root))
        except (ValueError, RuntimeError) as exc:
            result.notes.append(f"analysis {a.kind!r} not run: {exc}")
    if result.analyses:
        result.commit_sha = git.head_sha(paths.root)
    return result


def _apply_sd(sd, default_origin: str, root: Path) -> int:
    """Roles first (equations need them), then values, equations, tables, uncertainty, scenarios."""
    from latris.operations import sd as sd_ops
    from latris.operations import sd_scenarios, uncertainty

    n = 0
    for r in sd.roles:
        sd_ops.set_role(r.node, r.role, root=root)
        n += 1
    for s in sd.stocks:
        sd_ops.set_initial_value(s.node, s.value, s.units, non_negative=s.non_negative,
                                 origin=s.origin or default_origin, source_id=s.source, root=root)
        n += 1
    for c in sd.constants:
        sd_ops.set_constant(c.node, c.value, c.units, origin=c.origin or default_origin, source_id=c.source,
                            root=root)
        n += 1
    for e in sd.equations:
        sd_ops.set_equation(e.node, e.expression, e.units, origin=e.origin or default_origin, source_id=e.source,
                            root=root)
        n += 1
    for t in sd.tables:
        sd_ops.set_table(t.node, [tuple(p) for p in t.points], t.x_units, t.y_units, extrapolate=t.extrapolate,
                         origin=t.origin or default_origin, source_id=t.source, root=root)
        n += 1
    for u in sd.uncertainty:
        uncertainty.set_uncertainty(u.node, u.distribution, u.params, reason=u.reason, source_id=u.source,
                                    origin=u.origin or default_origin, root=root)  # type: ignore[arg-type]
        n += 1
    for sc in sd.scenarios:
        sd_scenarios.set_scenario(sc.name, sc.set, description=sc.description, reason=sc.reason,
                                  origin=sc.origin or default_origin, source_id=sc.source,  # type: ignore[arg-type]
                                  root=root)
        n += 1
    return n


def _apply_bn(bn, default_origin: str, root: Path) -> int:
    from latris.operations import bn as bn_ops

    n = 0
    for s in bn.states:
        bn_ops.set_state_space(s.node, s.states, ordered=s.ordered, root=root)
        n += 1
    for t in bn.tables:
        bn_ops.set_cpt(t.node, t.parents, t.probabilities, origin=t.origin or default_origin,  # type: ignore[arg-type]
                       source_id=t.source, root=root)
        n += 1
    for no in bn.noisy_or:
        bn_ops.set_noisy_or(no.node, no.leak, [(c.parent, c.active_state, c.probability) for c in no.causes],
                            origin=no.origin or default_origin, source_id=no.source, root=root)  # type: ignore[arg-type]
        n += 1
    return n


def _apply_interpretation(spec: BuildSpec, model_type: str, root: Path, result: BuildResult) -> None:
    """Create the sections (and their claims) if needed, then set each section's prose."""
    from latris.operations.interpret import initialise_sections, load_interpretation, refresh_all_claims, update_prose

    _, _, skipped = initialise_sections(root=root)
    refresh_all_claims(root=root)
    store = load_interpretation(root=root)
    for item in spec.interpretation:
        section = next(
            (s for s in store.sections if s.section_type == item.section and s.model_type == model_type), None
        )
        if section is None:
            why = next((reason for mid, reason in skipped if mid == model_type), "no such section for this model")
            result.notes.append(f"interpretation {item.section!r} not applied: {why}")
            continue
        by_ai = item.by == "ai"
        update_prose(section.id, item.prose, source="ai" if by_ai else "human-edit", written_by_agent=by_ai, root=root)
        result.interpretation += 1
