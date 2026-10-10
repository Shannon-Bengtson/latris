"""Real-AI consistency eval for node-producing prompts.

On-demand, NEVER in CI (gated behind ``LATRIS_AI_EVAL=1``; costs real
money). Where the smoke tests assert the prompt is *assembled* correctly, this
measures whether repeated real calls produce *consistent* nodes — the metric
the prompt rework is meant to move.

Method: build a small project, run a node prompt N times, and measure
    - label-set agreement across runs (mean pairwise Jaccard on normalised
      labels) — the granularity/phrasing consistency number;
    - kind-distribution stability — whether the same question yields the same
      entity kinds run-to-run (the baseline failure was all-'concept' one run,
      mostly-'variable' the next);
    - entity count within an expected band.

Run as a report:
    LATRIS_AI_EVAL=1 python -m tests.ai.evals.test_node_consistency
Run as a gated test:
    LATRIS_AI_EVAL=1 python -m pytest tests/ai/evals -n0 -s
"""

from __future__ import annotations

import os
from itertools import combinations
from pathlib import Path

import pytest

from latris.ai import config as ai_config
from latris.ai import credentials as creds
from latris.ai import prompts as prompt_lib
from latris.ai.adapters import get_adapter
from latris.ai.call import _provider_for
from latris.ai.context import build_context
from latris.operations.init import init_project
from latris.operations.project import update_selected_models
from latris.operations.references import add_reference, set_source_snapshot
from latris.repo.layout import ProjectPaths

EVAL_ENABLED = os.environ.get("LATRIS_AI_EVAL") == "1"

pytestmark = pytest.mark.skipif(
    not EVAL_ENABLED,
    reason="real-AI eval; set LATRIS_AI_EVAL=1 (and unset LATRIS_AI_MOCK) to run",
)

# Consistency floors — deliberately loose (LLMs are stochastic); they flag a
# *regression* in consistency, not perfection.
_MIN_MEAN_JACCARD = 0.45
_EXPECTED_COUNT_RANGE = (4, 12)


def _norm(label: str) -> str:
    return " ".join(label.split()).lower()


# Coverage dimensions for the freshwater question + keyword sets to detect them
# in produced labels (the metric the scope contract is meant to move).
_SCOPE_DIMENSIONS = {
    "nutrients": ["nutrient", "nitrogen", "phosph", "fertilis", "fertiliz"],
    "sediment": ["sediment", "erosion", "soil loss"],
    "riparian": ["riparian", "buffer", "vegetation", "wetland"],
    "landmgmt": ["land", "grazing", "stocking", "tillage", "crop", "practice"],
    "hydrology": ["flow", "hydrolog", "runoff", "residence", "discharge", "rainfall"],
}


def _build_eval_project(root: Path, *, scoped: bool = False) -> ProjectPaths:
    init_project(root, statement="What drives freshwater quality in an agricultural catchment?")
    update_selected_models(["cld"], root=root)
    add_reference(
        "smith2020",
        title="Nutrient loading and eutrophication in agricultural catchments",
        authors=["Smith, J."],
        year=2020,
        root=root,
    )
    set_source_snapshot(
        "smith2020",
        retrieval_url="https://example.com/smith2020",
        extract=(
            "Phosphorus and nitrogen loading from fertiliser application drive "
            "algal blooms. Riparian vegetation buffers reduce runoff; soil "
            "erosion increases sediment transport into waterways."
        ),
        kind="abstract",
        root=root,
    )
    if scoped:
        # Populate the scope contract — the lever under test.
        from latris.operations.project import set_foundation_field

        set_foundation_field(
            "coverage_dimensions",
            "nutrient loading (N & P), sediment & soil erosion, riparian/buffer "
            "vegetation, farm land-management practices, hydrology & flow",
            root=root,
        )
        set_foundation_field(
            "granularity_level",
            "each node a specific, measurable, intervenable variable a catchment "
            "manager could monitor or act on",
            root=root,
        )
        set_foundation_field("audience", "a regional catchment-management agency", root=root)
    return ProjectPaths(root)


def _dimension_coverage(label_set: set[str]) -> int:
    """How many of the declared coverage dimensions appear in a run's labels."""
    text = " ".join(label_set)
    return sum(1 for kws in _SCOPE_DIMENSIONS.values() if any(k in text for k in kws))


def _run_prompt_once(prompt_name: str, inputs: dict, paths: ProjectPaths):
    spec = prompt_lib.PROMPT_LIBRARY[prompt_name]
    cfg = ai_config.load(paths)
    model = ai_config.resolve_model(paths)
    provider = _provider_for(model)
    ctx = build_context(prompt_name, inputs, paths)
    temperature = spec.temperature if spec.temperature is not None else cfg.temperature
    adapter = get_adapter()
    with creds.key_in_env([provider]):
        result = adapter.chat(
            model=model,
            system=ctx.system,
            user=ctx.user,
            response_model=spec.response_model,
            temperature=temperature,
            max_tokens=cfg.max_tokens,
        )
    return result.parsed


def _variables_of(parsed) -> list[tuple[str, str]]:
    """Extract (label, kind) pairs from a SuggestedVariablesResult /
    ExtractedVariablesResult."""
    items = getattr(parsed, "variables", None) or []
    return [(v.label, str(v.kind)) for v in items]


def _mean_pairwise_jaccard(runs: list[set[str]]) -> float:
    pairs = list(combinations(runs, 2))
    if not pairs:
        return 1.0
    scores = []
    for a, b in pairs:
        union = a | b
        scores.append(len(a & b) / len(union) if union else 1.0)
    return sum(scores) / len(scores)


def _measure(prompt_name: str, inputs: dict, paths: ProjectPaths, n: int = 5) -> dict:
    label_sets: list[set[str]] = []
    counts: list[int] = []
    kind_dists: list[tuple] = []
    for _ in range(n):
        parsed = _run_prompt_once(prompt_name, inputs, paths)
        pairs = _variables_of(parsed)
        label_sets.append({_norm(lbl) for lbl, _ in pairs})
        counts.append(len(pairs))
        kinds = tuple(sorted(k for _, k in pairs))
        kind_dists.append(kinds)
    return {
        "mean_jaccard": _mean_pairwise_jaccard(label_sets),
        "counts": counts,
        "label_sets": label_sets,
        "kind_dists": kind_dists,
    }


# ── Provenance-completeness (the moat metric) ───────────────────────────
#
# The consistency numbers above say whether nodes are phrased consistently; they
# say nothing about whether the structural edit captured its provenance. This
# measures what the provenance plan is meant to move: the fraction of nodes and
# edges that carry an assumption and/or a grounded evidence link, captured in
# the same call that created them (draft/find-connections apply()).


def _build_model_with_edges(paths: ProjectPaths) -> None:
    """Run DraftConceptualModel for real and apply the first framing, so nodes,
    edges, and their co-authored provenance land in the project."""
    from latris.ai.proposals import DraftModelProposal

    parsed = _run_prompt_once("DraftConceptualModel", {}, paths)
    assert isinstance(parsed, DraftModelProposal) and parsed.framings, "draft produced no framings"
    parsed.selected_index = 0
    parsed.apply(paths)


def _measure_provenance(paths: ProjectPaths) -> dict:
    from latris.operations.edges import list_edges
    from latris.operations.nodes import list_nodes
    from latris.repo.yaml_io import load_model
    from latris.schema import AssumptionLog, EvidenceLinkSet

    node_ids = {n.id for n in list_nodes(paths.root)}
    edge_ids = {e.id for e in list_edges(paths.root)}
    ev = load_model(EvidenceLinkSet, paths.evidence_links_yaml).entries
    assumptions = load_model(AssumptionLog, paths.assumptions_yaml).entries
    ev_targets = {e.target_id for e in ev}
    assume_targets = {a.target_id for a in assumptions}

    def _frac(ids: set[str], targets: set[str]) -> float:
        return len(ids & targets) / len(ids) if ids else 0.0

    return {
        "n_nodes": len(node_ids),
        "n_edges": len(edge_ids),
        "nodes_with_evidence": _frac(node_ids, ev_targets),
        "edges_with_evidence": _frac(edge_ids, ev_targets),
        "nodes_with_assumption": _frac(node_ids, assume_targets),
        "edges_with_assumption": _frac(edge_ids, assume_targets),
    }


def test_provenance_completeness(tmp_path: Path) -> None:
    """A real draft must capture *some* provenance on the model it builds —
    the headline moat metric. Loose floor (LLMs are stochastic); it flags a
    regression to zero-provenance, not a coverage target."""
    assert os.environ.get("LATRIS_AI_MOCK") != "1", (
        "eval must run against the real adapter; unset LATRIS_AI_MOCK"
    )
    paths = _build_eval_project(tmp_path / "proj")
    _build_model_with_edges(paths)
    m = _measure_provenance(paths)

    assert m["n_edges"] >= 1, "draft produced no edges to measure provenance against"
    captured = (
        m["nodes_with_evidence"]
        + m["edges_with_evidence"]
        + m["nodes_with_assumption"]
        + m["edges_with_assumption"]
    )
    assert captured > 0, (
        f"draft captured NO provenance on any node or edge: {m} — "
        "source_bibkeys/assumptions are not reaching the built model."
    )


def _measure_scope(scoped: bool, tmp_path: Path, n: int = 4) -> dict:
    paths = _build_eval_project(tmp_path / ("scoped" if scoped else "base"), scoped=scoped)
    r = _measure("DraftConceptualModel", {"candidate_count": 1}, paths, n=n)
    coverages = [_dimension_coverage(s) for s in r["label_sets"]]
    return {"jaccard": r["mean_jaccard"], "coverage": sum(coverages) / len(coverages), "counts": r["counts"]}


def test_scope_contract_improves_consistency(tmp_path: Path) -> None:
    """Populating the scope contract (coverage dimensions / granularity / audience)
    should make repeated drafts converge and span all declared dimensions — the
    lever validated in the scratchpad A/B. Directional assertions with tolerance
    (real AI is stochastic; this is a gated on-demand eval, not CI)."""
    assert os.environ.get("LATRIS_AI_MOCK") != "1", (
        "eval must run against the real adapter; unset LATRIS_AI_MOCK"
    )
    base = _measure_scope(False, tmp_path)
    scoped = _measure_scope(True, tmp_path)
    print(f"\nbaseline: {base}\nscoped:   {scoped}")
    assert scoped["coverage"] >= 4.5, (
        f"scoped runs should span ~all 5 declared dimensions; got {scoped['coverage']:.1f}"
    )
    assert scoped["coverage"] >= base["coverage"], "scope contract did not improve dimension coverage"
    assert scoped["jaccard"] >= base["jaccard"] - 0.03, (
        f"scope contract worsened run-to-run agreement: {base['jaccard']:.2f} -> {scoped['jaccard']:.2f}"
    )


@pytest.mark.parametrize("prompt_name", ["SuggestVariables", "ExtractVariablesFromEvidence"])
def test_node_consistency(tmp_path: Path, prompt_name: str) -> None:
    assert os.environ.get("LATRIS_AI_MOCK") != "1", (
        "eval must run against the real adapter; unset LATRIS_AI_MOCK"
    )
    paths = _build_eval_project(tmp_path / "proj")
    result = _measure(prompt_name, {}, paths, n=5)

    lo, hi = _EXPECTED_COUNT_RANGE
    assert all(lo <= c <= hi for c in result["counts"]), (
        f"{prompt_name}: entity counts {result['counts']} outside {_EXPECTED_COUNT_RANGE}"
    )
    assert result["mean_jaccard"] >= _MIN_MEAN_JACCARD, (
        f"{prompt_name}: mean pairwise Jaccard {result['mean_jaccard']:.2f} "
        f"below floor {_MIN_MEAN_JACCARD} — granularity/phrasing is inconsistent."
    )


def _report() -> None:
    import tempfile

    for prompt_name in ("SuggestVariables", "ExtractVariablesFromEvidence"):
        with tempfile.TemporaryDirectory() as td:
            paths = _build_eval_project(Path(td) / "proj")
            r = _measure(prompt_name, {}, paths, n=5)
            print(f"\n=== {prompt_name} (N=5) ===")
            print(f"mean pairwise Jaccard: {r['mean_jaccard']:.2f}")
            print(f"entity counts: {r['counts']}")
            for i, (labels, kinds) in enumerate(zip(r["label_sets"], r["kind_dists"], strict=True)):
                from collections import Counter

                print(f"  run{i}: kinds={dict(Counter(kinds))}")
                print(f"         {sorted(labels)}")

    with tempfile.TemporaryDirectory() as td:
        paths = _build_eval_project(Path(td) / "proj")
        _build_model_with_edges(paths)
        m = _measure_provenance(paths)
        print("\n=== DraftConceptualModel — provenance completeness ===")
        print(f"nodes={m['n_nodes']} edges={m['n_edges']}")
        print(f"  nodes w/ evidence:   {m['nodes_with_evidence']:.0%}")
        print(f"  edges w/ evidence:   {m['edges_with_evidence']:.0%}")
        print(f"  nodes w/ assumption: {m['nodes_with_assumption']:.0%}")
        print(f"  edges w/ assumption: {m['edges_with_assumption']:.0%}")


if __name__ == "__main__":
    if not EVAL_ENABLED:
        raise SystemExit("set LATRIS_AI_EVAL=1 (and unset LATRIS_AI_MOCK) to run")
    _report()
