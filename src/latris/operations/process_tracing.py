"""Process tracing on a theory of change — how far the evidence supports each causal link.

Bayesian process tracing (Bennett 2015; Befani & Mayne 2014; Fairfield &
Charman 2017) treats each link of a results chain as a hypothesis H and each
piece of evidence as a test. A test is characterised by two judgements:

- **certainty** P(E | H): how likely you'd be to find the evidence if the link
  holds;
- P(E | not H), whose complement is its **uniqueness**: how unlikely the
  evidence would be if it didn't.

Finding the evidence multiplies the odds on H by P(E|H) / P(E|not H); looking
and not finding it, by (1 − P(E|H)) / (1 − P(E|not H)). Starting from a prior,
the tests give each link a posterior. Van Evera's (1997) four tests are the
corners of that space — this module's convention: *certain* when
P(E|H) ≥ 0.8, *unique* when P(E|not H) ≤ 0.2:

- **hoop** (certain, not unique): failing it sinks the link; passing it helps little;
- **smoking gun** (unique, not certain): passing it strongly supports the link; failing it hurts little;
- **doubly decisive** (both): decisive either way;
- **straw in the wind** (neither): nudges only.

A pathway is as believable as all its links together (the product of their
posteriors, treating links as independent). For tests not yet carried out, the
analysis says what each would do to its link if passed or failed — which
test to run next.

Priors and tests are stored with provenance (``schema/process_tracing.py``);
links are the theory of change's own (``operations/toc.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations._resolve import resolve_target
from latris.operations._view_store import ViewStore, replace_entry
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema import Substrate
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.schema.process_tracing import PTPriorEntry, PTPriorSet, PTTestEntry, PTTestSet

MODEL_TYPE = "theory_of_change"
DEFAULT_PRIOR = 0.5
CERTAIN, UNIQUE = 0.8, 0.2  # thresholds for the Van Evera classification
_UNSET = object()


_store = ViewStore(MODEL_TYPE)


def get_priors(*, root: Path | None = None) -> PTPriorSet:
    return _store.load(root, "pt_prior", PTPriorSet)


def get_tests(*, root: Path | None = None) -> PTTestSet:
    return _store.load(root, "pt_test", PTTestSet)


def _link(paths, link: str) -> tuple[str, str]:
    """Resolve a theory-of-change link: an edge between two factors that both have a level."""
    from latris.operations import toc

    sub = load_model(Substrate, paths.conceptual_yaml)
    eid = resolve_target(link, sub)
    e = next((x for x in sub.edges if x.id == eid), None)
    if e is None:
        raise ValueError(f"{link!r} is a factor; process tracing tests a link, written 'From -> To'")
    levels = toc.get_levels(root=paths.root)
    if e.from_id not in levels or e.to_id not in levels:
        raise ValueError("process tracing tests links of the theory of change: give both ends a level first "
                         "(`latris toc level`)")
    labels = {x.id: x.label for x in sub.entities}
    return eid, f"{labels[e.from_id]} → {labels[e.to_id]}"


def set_prior(
    link: str,
    prior: float,
    *,
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    verification: ProvenanceVerification = "unverified",
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[PTPriorEntry, str]:
    """Set how confident you are in a link before the tests (default 0.5)."""
    paths = require_project(root)
    eid, name = _link(paths, link)
    entry = PTPriorEntry(target_id=eid, prior=prior, origin=origin, source_id=source_id, verification=verification,
                         notes=notes)
    store = get_priors(root=paths.root)
    replace_entry(store, entry)
    sha = _store.save(paths, "pt_prior", store, subject=f"Process tracing: prior on {name} = {prior:g}",
        body=f"edge: {eid}\nprior: {prior}\norigin: {origin}\nsource_id: {source_id}")
    return entry, sha


def set_test(
    link: str,
    name: str,
    *,
    p_if_true: float | object = _UNSET,
    p_if_false: float | object = _UNSET,
    found: bool | None | object = _UNSET,
    description: str | None | object = _UNSET,
    notes: str | None | object = _UNSET,
    origin: ProvenanceOrigin | object = _UNSET,
    source_id: str | None | object = _UNSET,
    verification: ProvenanceVerification | object = _UNSET,
    root: Path | None = None,
) -> tuple[PTTestEntry, str]:
    """Add or update a test on a link. A new test needs both probabilities; afterwards only what's given changes."""
    paths = require_project(root)
    eid, lname = _link(paths, link)
    name = name.strip()
    if not name:
        raise ValueError("give the test a name")
    store = get_tests(root=paths.root)
    current = next((t for t in store.entries if (t.target_id, t.name) == (eid, name)), None)
    given = {"p_if_true": p_if_true, "p_if_false": p_if_false, "found": found, "description": description,
             "notes": notes, "origin": origin, "source_id": source_id, "verification": verification}
    changed = {k: v for k, v in given.items() if v is not _UNSET}
    if current is None and ("p_if_true" not in changed or "p_if_false" not in changed):
        raise ValueError("a new test needs both probabilities: how likely the evidence is if the link holds "
                         "(--if-true) and if it doesn't (--if-false)")
    if current is not None and not changed:
        raise ValueError("nothing to set for this test")
    base = current.model_dump() if current else {"target_id": eid, "name": name}
    entry = PTTestEntry.model_validate({**base, **changed})
    replace_entry(store, entry, "target_id", "name")
    sha = _store.save(paths, "pt_test", store, subject=f"Process tracing: test '{name}' on {lname}",
        body=f"edge: {eid}\n" + "\n".join(f"{k}: {v}" for k, v in changed.items()))
    return entry, sha


def remove_test(link: str, name: str, *, root: Path | None = None) -> str:
    paths = require_project(root)
    eid, lname = _link(paths, link)
    store = get_tests(root=paths.root)
    kept = [t for t in store.entries if (t.target_id, t.name) != (eid, name.strip())]
    if len(kept) == len(store.entries):
        raise ValueError(f"no test named {name!r} on {lname}")
    store.entries = kept
    return _store.save(paths, "pt_test", store, subject=f"Process tracing: removed test '{name}' on {lname}")


# ── the kernel ───────────────────────────────────────────────────────


def classify(p_if_true: float, p_if_false: float) -> str:
    certain, unique = p_if_true >= CERTAIN, p_if_false <= UNIQUE
    if certain and unique:
        return "doubly decisive"
    if certain:
        return "hoop"
    if unique:
        return "smoking gun"
    return "straw in the wind"


def likelihood_ratio(p_if_true: float, p_if_false: float, found: bool) -> float:
    return p_if_true / p_if_false if found else (1 - p_if_true) / (1 - p_if_false)


def posterior(prior: float, ratios: list[float]) -> float:
    odds = prior / (1 - prior)
    for r in ratios:
        odds *= r
    return odds / (1 + odds)


def verdict(p: float) -> str:
    if p >= 0.95:
        return "very likely"
    if p >= 0.75:
        return "likely"
    if p > 0.25:
        return "uncertain"
    if p > 0.05:
        return "unlikely"
    return "very unlikely"




def _test_row(t: PTTestEntry) -> dict[str, Any]:
    return {"test": t.name, "type": classify(t.p_if_true, t.p_if_false), "p_if_true": t.p_if_true,
            "p_if_false": t.p_if_false, "found": t.found, "description": t.description,
            "ratio": likelihood_ratio(t.p_if_true, t.p_if_false, t.found) if t.found is not None else None,
            "source": t.source_id, "weak": t.is_weak}


def _link_row(name: str, on_pathway: bool, prior: PTPriorEntry | None, tests: list[PTTestEntry]) -> dict[str, Any]:
    """A link's prior, its tests, the posterior from the done ones and what each pending one would do."""
    pr = prior.prior if prior else DEFAULT_PRIOR
    ratios = [likelihood_ratio(t.p_if_true, t.p_if_false, t.found) for t in tests if t.found is not None]
    p = posterior(pr, ratios)
    pending = [{"test": t.name, "type": classify(t.p_if_true, t.p_if_false),
                "if_found": posterior(p, [likelihood_ratio(t.p_if_true, t.p_if_false, True)]),
                "if_not_found": posterior(p, [likelihood_ratio(t.p_if_true, t.p_if_false, False)])}
               for t in tests if t.found is None]
    return {
        "link": name, "on_pathway": on_pathway, "prior": pr,
        "prior_source": prior.source_id if prior else None,
        "tests": [_test_row(t) for t in sorted(tests, key=lambda t: t.name)],
        "posterior": p, "verdict": verdict(p), "pending": pending,
    }


def _pathway_rows(pathways: list[Any], post: dict[str, float], labels: dict[str, str], names: dict[str, str]
                  ) -> list[dict[str, Any]]:
    """Each pathway's confidence (the product of its links' posteriors) and its weakest link, most credible
    first."""
    rows: list[dict[str, Any]] = []
    for pw in pathways:
        conf = 1.0
        for e in pw.edge_ids:
            conf *= post.get(e, DEFAULT_PRIOR)
        weakest = min(pw.edge_ids, key=lambda e: post.get(e, DEFAULT_PRIOR))
        rows.append({"path": [labels[n] for n in pw.node_ids], "confidence": conf,
                     "weakest": names[weakest], "weakest_posterior": post.get(weakest, DEFAULT_PRIOR)})
    rows.sort(key=lambda x: -x["confidence"])
    return rows


def analyse(*, root: Path | None = None) -> dict[str, Any]:
    from latris.operations import toc

    paths = require_project(root)
    result, substrate = toc.load_analysis(root=paths.root)
    labels = {e.id: e.label for e in substrate.entities}
    names = {lk.edge_id: f"{labels[lk.from_id]} → {labels[lk.to_id]}" for lk in result.links}
    priors = {p.target_id: p for p in get_priors(root=paths.root).entries if p.target_id in names}
    tests: dict[str, list[PTTestEntry]] = {}
    for t in get_tests(root=paths.root).entries:
        if t.target_id in names:
            tests.setdefault(t.target_id, []).append(t)
    on_path = {lk.edge_id for lk in result.links if lk.on_pathway}
    traced = sorted(set(priors) | set(tests) | on_path, key=lambda e: names[e])
    links = [_link_row(names[e], e in on_path, priors.get(e), tests.get(e, [])) for e in traced]
    post = {e: lk["posterior"] for e, lk in zip(traced, links, strict=True)}
    candidates = [(lk["link"], t) for lk in links if lk["on_pathway"] for t in lk["pending"]]
    nxt = max(candidates, key=lambda c: abs(c[1]["if_found"] - c[1]["if_not_found"]), default=None)
    rested = sorted({f"'{t['test']}' on {lk['link']}" for lk in links for t in lk["tests"]
                     if t["found"] is not None and t["weak"]})
    return {
        "links": links, "pathways": _pathway_rows(result.pathways, post, labels, names),
        "untested": [lk["link"] for lk in links if lk["on_pathway"] and not any(t["found"] is not None
                                                                              for t in lk["tests"])],
        "next_test": {"link": nxt[0], **nxt[1]} if nxt else None,
        "rests_on_unverified": rested,
        "toc_complete": not result.problems,
    }


def describe(p: dict[str, Any]) -> str:
    tested = [lk for lk in p["links"] if any(t["found"] is not None for t in lk["tests"])]
    parts = [f"{len(tested)} of {len(p['links'])} link(s) tested"]
    if p["pathways"]:
        best = p["pathways"][0]
        parts.append(f"most credible pathway {best['confidence']:.0%} ({' → '.join(best['path'])}), weakest link "
                     f"{best['weakest']} ({best['weakest_posterior']:.0%})")
    if p["next_test"]:
        n = p["next_test"]
        parts.append(f"most informative next test: '{n['test']}' on {n['link']} "
                     f"({n['if_not_found']:.0%} if not found, {n['if_found']:.0%} if found)")
    return "; ".join(parts)


def _record(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.analysis_results import record_result

    sha, run = record_result(
        kind="toc-process-trace",
        key="toc-process-trace",
        payload=payload,
        purpose="inference",
        algorithm="Bayesian process tracing: odds-form updating per link from P(E|H), P(E|not H) and whether each "
                  "test was passed; pathway confidence as the product of link posteriors",
        library_version="latris",
        summary=describe(payload),
        model_type=MODEL_TYPE,
        metrics={"links": len(payload["links"]), "pathways": len(payload["pathways"]),
                 "best_pathway": payload["pathways"][0]["confidence"] if payload["pathways"] else None},
        commit_subject="Analysis: process tracing",
        root=root,
    )
    return sha, run.id


def trace(*, record: bool = True, root: Path | None = None) -> tuple[dict[str, Any], str | None]:
    """Trace every link of the theory of change and (by default) record it. Returns (payload, sha or None)."""
    payload = analyse(root=root)
    if not record:
        return payload, None
    sha, run_id = _record(payload, root=root)
    payload["run_id"] = run_id
    return payload, sha
