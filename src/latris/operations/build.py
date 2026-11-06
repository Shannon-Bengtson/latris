"""Build a model from a spec file in one commit (``latris build --spec``).

The spec is checked in full before anything is written — every link end,
citation and the outcome must name a factor or source that exists in the
project or in the spec — so a mistake leaves the project untouched. The
writes then run through the normal operations inside one ``batch()``, so
the result is identical to issuing the commands one by one, as one commit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from latris.operations.batch import batch
from latris.repo import git
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model, load_model_from_string
from latris.schema import ProjectFoundation, ReferenceLibrary, Substrate
from latris.schema.build_spec import BuildSpec, SpecCitation


@dataclass
class BuildResult:
    factors: int = 0
    links: list[dict[str, str]] = field(default_factory=list)
    sources: int = 0
    citations: int = 0
    assumptions: int = 0
    questions: int = 0
    outcome: str | None = None
    commit_sha: str = ""


def load_spec(text: str) -> BuildSpec:
    """Parse a YAML or JSON spec (JSON is valid YAML)."""
    return load_model_from_string(BuildSpec, text)


def _citations(items: list[str | SpecCitation]) -> list[SpecCitation]:
    return [SpecCitation(key=c) if isinstance(c, str) else c for c in items]


def _check(spec: BuildSpec, substrate: Substrate, ref_keys: set[str], model_type: str) -> None:
    """Raise ValueError listing every reference the spec can't resolve."""
    existing = {e.label.casefold() for e in substrate.entities} | {e.id for e in substrate.entities}
    spec_labels = [f.label for f in spec.factors]
    dupes = sorted({x for x in spec_labels if spec_labels.count(x) > 1})
    known = existing | {label.casefold() for label in spec_labels}
    keys = ref_keys | {s.key for s in spec.sources}
    problems: list[str] = []
    if dupes:
        problems.append(f"factor listed twice: {', '.join(dupes)}")
    clash = sorted(label for label in spec_labels if label.casefold() in existing)
    if clash:
        problems.append(f"factor already in the project: {', '.join(clash)}")

    def _known(name: str) -> bool:
        return name.casefold() in known or name in known

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
    if problems:
        raise ValueError("the spec has problems, nothing was changed:\n- " + "\n- ".join(problems))


def build_from_spec(spec: BuildSpec, *, verified_by: str = "human", root: Path | None = None) -> BuildResult:
    """Apply ``spec`` to the project as one commit."""
    from latris.operations.attributes import set_attribute
    from latris.operations.edges import add_edge
    from latris.operations.evidence import add_evidence
    from latris.operations.nodes import add_node
    from latris.operations.provenance import add_assumption, add_question
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

    with batch(paths.root, subject=subject):
        for s in spec.sources:
            add_reference(
                s.key, s.title, authors=s.authors or None, year=s.year, container=s.container,
                doi=s.doi, url=s.url, root=paths.root,
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
            if f.description:
                set_attribute(node.id, "description", f.description, root=paths.root)
            _cite(node.id, "description", f.sources)
            _cite(node.id, "description", f.contradicts, against=True)
            result.factors += 1

        for link in spec.links:
            edge, _ = add_edge(link.from_, link.to, kind=link.kind, root=paths.root)
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
        for text in spec.assumptions:
            add_assumption(text, root=paths.root)
            result.assumptions += 1
        for text in spec.questions:
            add_question(text, root=paths.root)
            result.questions += 1

    result.commit_sha = git.head_sha(paths.root)
    return result
