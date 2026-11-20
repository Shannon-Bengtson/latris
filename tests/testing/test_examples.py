"""``latris.testing`` examples record every result kind, and each result's charts are the declared ones.

These are the guarantees apps rely on: build the examples, and every result kind a report can show
has a real payload to render; every chart kind a result emits is declared (``chart_kinds``), and
every declared kind is emitted by some example.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.exporters.results import result_charts
from latris.operations.analysis_results import result_surfaces
from latris.testing import EXAMPLES, build_example, example_payloads


@pytest.fixture(scope="module")
def payloads(tmp_path_factory: pytest.TempPathFactory) -> dict:
    with pytest.MonkeyPatch.context() as mp:
        for k in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
            mp.setenv(k, "Test Runner")
        for k in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
            mp.setenv(k, "test-runner@example.invalid")
        return example_payloads(tmp_path_factory.mktemp("examples"))


def test_every_example_has_a_spec_and_its_data():
    for ex in EXAMPLES.values():
        assert ex.spec_path.is_file(), ex.name
        for file in ex.datasets.values():
            assert (ex.spec_path.parent / file).is_file(), (ex.name, file)


def test_every_result_kind_has_an_example(payloads):
    missing = {r.kind for r in result_surfaces()} - set(payloads)
    assert not missing, f"no example records {sorted(missing)}: add analyses to latris/testing/examples/"


@pytest.mark.parametrize("surface", result_surfaces(), ids=lambda r: r.kind)
def test_charts_emitted_are_declared(surface, payloads):
    emitted = {kind for p in payloads[surface.kind] for kind, _ in result_charts(surface.kind, p)}
    assert emitted <= set(surface.chart_kinds), f"declare {sorted(emitted - set(surface.chart_kinds))} in chart_kinds"


def test_every_declared_chart_is_emitted_by_an_example(payloads):
    emitted = {(r.kind, kind) for r in result_surfaces() for p in payloads[r.kind] for kind, _ in result_charts(r.kind, p)}
    declared = {(r.kind, kind) for r in result_surfaces() for kind in r.chart_kinds}
    assert declared <= emitted, f"no example draws {sorted(declared - emitted)}"


def test_a_broken_example_fails_loudly(tmp_path: Path, git_identity, monkeypatch):
    from latris import testing

    monkeypatch.setitem(testing.EXAMPLES, "toc_impact", testing.Example(
        "toc_impact", ("theory_of_change",), "Q?", datasets={}))  # its datasets left out
    with pytest.raises(ValueError, match="not run"):
        build_example("toc_impact", tmp_path / "p")
