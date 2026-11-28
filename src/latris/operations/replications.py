"""Replications: textbook models rebuilt in Latris, checked against the numbers they are known to give.

Each lives in ``latris/replications/<id>/`` (``spec.json`` + ``replication.yaml``, schema in
``schema/replication.py``) and ships in the wheel, so anyone can rebuild one and see for themselves that
Latris reproduces the original. ``check_replication`` builds the model into a fresh project, runs the
spec's analyses exactly as a person would, and compares each check's measure with its expected value.

Builds commit to git, so a git identity must be configured (globally or by environment variables).
"""

from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from latris.operations.errors import NotFoundError
from latris.repo.yaml_io import load_model
from latris.schema.replication import (
    BnProbability,
    DagAdjustmentSets,
    DagAdjustmentValid,
    LoopCount,
    Replication,
    ReplicationCheck,
    SdPeak,
    SdValue,
)

REPLICATIONS_DIR = Path(__file__).resolve().parent.parent / "replications"


@dataclass
class CheckOutcome:
    id: str
    claim: str
    expected: Any
    actual: Any
    passed: bool
    basis: str
    where: str
    checked: bool


@dataclass
class ReplicationReport:
    id: str
    title: str
    model_type: str
    source: str
    passed: bool
    outcomes: list[CheckOutcome] = field(default_factory=list)
    root: str | None = None  # where the model was built, when it was kept


def list_replications() -> list[Replication]:
    """Every replication that ships with Latris, in id order."""
    return [
        load_model(Replication, d / "replication.yaml")
        for d in sorted(REPLICATIONS_DIR.iterdir())
        if (d / "replication.yaml").is_file()
    ]


def get_replication(rep_id: str) -> Replication:
    known = {r.id: r for r in list_replications()}
    if rep_id not in known:
        raise NotFoundError(f"no replication {rep_id!r}; known: {', '.join(sorted(known))}")
    return known[rep_id]


def spec_path(rep_id: str) -> Path:
    get_replication(rep_id)
    return REPLICATIONS_DIR / rep_id / "spec.json"


def build_replication(rep_id: str, root: Path) -> list[str]:
    """Build replication ``rep_id`` as a new project at ``root`` and run its analyses.

    Returns the run ids of the analyses, in the spec's order. Raises ValueError if any part of the spec
    couldn't be applied or any analysis didn't run, so a broken replication fails loudly rather than
    checking the wrong result.
    """
    from latris.operations.build import build_from_spec, load_spec
    from latris.operations.init import init_project
    from latris.operations.project import update_selected_models

    rep = get_replication(rep_id)
    spec = load_spec(spec_path(rep_id).read_text(encoding="utf-8"))
    init_project(root, statement=rep.question, name=rep.id)
    update_selected_models([rep.model_type], root=root)
    built = build_from_spec(spec, root=root)
    if built.notes:
        raise ValueError(f"replication {rep_id!r}: " + "; ".join(built.notes))
    if len(built.analyses) != len(spec.analyses):
        raise ValueError(f"replication {rep_id!r}: {len(spec.analyses) - len(built.analyses)} analyses didn't run")
    return built.analyses


def check_replication(rep_id: str, *, root: Path | None = None) -> ReplicationReport:
    """Build ``rep_id`` and compare every check with its expected value.

    ``root``: where to build it (a new or empty folder), kept afterwards; by default a temporary folder,
    removed once the checks have run.
    """
    rep = get_replication(rep_id)
    if root is not None:
        return _check(rep, root, keep=True)
    with tempfile.TemporaryDirectory(prefix=f"latris-replication-{rep_id}-") as tmp:
        return _check(rep, Path(tmp) / rep_id, keep=False)


def _check(rep: Replication, root: Path, *, keep: bool) -> ReplicationReport:
    runs = build_replication(rep.id, root)
    reader = _Reader(root, runs)
    outcomes = [_outcome(c, reader) for c in rep.checks]
    return ReplicationReport(
        id=rep.id,
        title=rep.title,
        model_type=rep.model_type,
        source=rep.source.citation,
        passed=all(o.passed for o in outcomes),
        outcomes=outcomes,
        root=str(root) if keep else None,
    )


def _outcome(check: ReplicationCheck, reader: _Reader) -> CheckOutcome:
    actual = reader.measure(check)
    return CheckOutcome(
        id=check.id,
        claim=check.claim,
        expected=check.expected,
        actual=actual,
        passed=_agrees(check, actual),
        basis=check.basis,
        where=check.where,
        checked=check.checked,
    )


def _agrees(check: ReplicationCheck, actual: Any) -> bool:
    expected = check.expected
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual is expected
    if isinstance(expected, list):
        return sorted(sorted(s) for s in expected) == actual
    if not isinstance(actual, (int, float)) or math.isnan(actual):
        return False
    return abs(actual - expected) <= max(check.abs_tol, check.rel_tol * abs(expected))


class _Reader:
    """Reads a measure from the built project: recorded analysis results, or the graph itself."""

    def __init__(self, root: Path, runs: list[str]) -> None:
        self.root = root
        self.runs = runs
        self._payloads: dict[int, dict[str, Any]] = {}

    def measure(self, check: ReplicationCheck) -> Any:
        m = check.measure
        if isinstance(m, BnProbability):
            p = self._payload(m.analysis)
            return float(p["posteriors"][_node_id(p, m.node)][m.state])
        if isinstance(m, SdValue):
            times, series = self._series(m.analysis, m.variable, m.scenario)
            return _interpolate(times, series, m.time)
        if isinstance(m, SdPeak):
            times, series = self._series(m.analysis, m.variable, m.scenario)
            t_peak, v_peak = _peak(times, series)
            return t_peak if m.kind == "sd_peak_time" else v_peak
        if isinstance(m, DagAdjustmentValid):
            return self._adjustment_valid(m)
        if isinstance(m, DagAdjustmentSets):
            return self._adjustment_sets(m)
        if isinstance(m, LoopCount):
            from latris.operations.analysis import analyse_loops

            return float(sum(1 for loop in analyse_loops(root=self.root) if loop.classification == m.polarity))
        raise AssertionError(f"unhandled measure {m!r}")  # pragma: no cover — the union is closed

    def _payload(self, index: int) -> dict[str, Any]:
        from latris.operations.analysis_results import get_result

        if index >= len(self.runs):
            raise ValueError(f"check reads analysis {index}, but the spec has {len(self.runs)}")
        if index not in self._payloads:
            _, payload = get_result(self.runs[index], root=self.root)
            if payload is None:
                raise ValueError(f"analysis {index} recorded no result")
            self._payloads[index] = payload
        return self._payloads[index]

    def _series(self, index: int, variable: str, scenario: str) -> tuple[list[float], list[float]]:
        p = self._payload(index)
        runs = [s for s in p["scenarios"] if s["name"] == scenario]
        if not runs:
            raise ValueError(f"analysis {index} has no scenario {scenario!r}")
        return p["times"], runs[0]["series"][_node_id(p, variable)]

    def _graph(self) -> tuple[dict[str, str], list[Any]]:
        """Factor labels by id, and the causal links (the subgraph DAG analysis works on)."""
        from latris.operations.graph_analysis import causal_edges
        from latris.repo.project import require_project
        from latris.schema import Substrate

        substrate = load_model(Substrate, require_project(self.root).conceptual_yaml)
        return {e.id: e.label for e in substrate.entities}, causal_edges(substrate.edges)

    def _ids(self, labels: dict[str, str], *names: str) -> list[str]:
        by_label = {label.casefold(): node_id for node_id, label in labels.items()}
        missing = [n for n in names if n.casefold() not in by_label]
        if missing:
            raise ValueError(f"no factor {missing[0]!r} in the model")
        return [by_label[n.casefold()] for n in names]

    def _adjustment_valid(self, m: DagAdjustmentValid) -> bool:
        from latris.operations import graph_analysis as ga

        labels, edges = self._graph()
        exposure, outcome, *adjust = self._ids(labels, m.exposure, m.outcome, *m.adjust_for)
        # The back-door criterion (Pearl 2009, def. 3.3.1): no member descends from the exposure, and the set
        # blocks every path into the exposure, tested as d-separation once the exposure's own links are cut.
        descendants: set[str] = set()
        frontier = [exposure]
        while frontier:
            n = frontier.pop()
            for e in edges:
                if e.from_id == n and e.to_id not in descendants:
                    descendants.add(e.to_id)
                    frontier.append(e.to_id)
        if descendants & set(adjust):
            return False
        cut = [e for e in edges if e.from_id != exposure]
        return bool(ga.d_separation(cut, {exposure}, {outcome}, set(adjust)))

    def _adjustment_sets(self, m: DagAdjustmentSets) -> list[list[str]]:
        from latris.operations import graph_analysis as ga

        labels, edges = self._graph()
        exposure, outcome = self._ids(labels, m.exposure, m.outcome)
        return sorted(sorted(labels[z] for z in s) for s in ga.adjustment_sets(exposure, outcome, edges))


def _node_id(payload: dict[str, Any], label: str) -> str:
    for node_id, name in payload.get("labels", {}).items():
        if name.casefold() == label.casefold():
            return str(node_id)
    raise ValueError(f"no factor {label!r} in the result")


def _quadratic(ts: list[float], vs: list[float], t: float) -> float:
    """The parabola through three points, at ``t`` (Lagrange form)."""
    (t0, t1, t2), (v0, v1, v2) = ts, vs
    return float(
        v0 * (t - t1) * (t - t2) / ((t0 - t1) * (t0 - t2))
        + v1 * (t - t0) * (t - t2) / ((t1 - t0) * (t1 - t2))
        + v2 * (t - t0) * (t - t1) / ((t2 - t0) * (t2 - t1))
    )


def _interpolate(times: list[float], series: list[float], t: float) -> float:
    """``series`` at ``t``, by the parabola through the three nearest saved points (a recorded run keeps a
    thinned series, so a straight line between points would add error the simulation doesn't have)."""
    if not times[0] <= t <= times[-1]:
        raise ValueError(f"time {t} is outside the run ({times[0]}–{times[-1]})")
    if len(times) == 1:
        return float(series[0])
    if len(times) == 2:
        return float(series[0] + (t - times[0]) / (times[1] - times[0]) * (series[1] - series[0]))
    i = min(range(len(times)), key=lambda k: abs(times[k] - t))
    i = min(max(i, 1), len(times) - 2)
    return _quadratic(times[i - 1 : i + 2], series[i - 1 : i + 2], t)


def _peak(times: list[float], series: list[float]) -> tuple[float, float]:
    """(time, value) of a series' maximum: the vertex of the parabola through the highest saved point and its
    neighbours, so the answer doesn't depend on where the saved points happen to fall."""
    i = max(range(len(series)), key=series.__getitem__)
    if i == 0 or i == len(series) - 1:
        return float(times[i]), float(series[i])
    (t0, t1, t2), (v0, v1, v2) = times[i - 1 : i + 2], series[i - 1 : i + 2]
    denom = (t0 - t1) * (t0 - t2) * (t1 - t2)
    a = (t2 * (v1 - v0) + t1 * (v0 - v2) + t0 * (v2 - v1)) / denom
    b = (t2 * t2 * (v0 - v1) + t1 * t1 * (v2 - v0) + t0 * t0 * (v1 - v2)) / denom
    if a >= 0:
        return float(times[i]), float(series[i])
    t_peak = -b / (2 * a)
    return t_peak, _quadratic([t0, t1, t2], [v0, v1, v2], t_peak)
