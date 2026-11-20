"""Example projects for testing surfaces built on latris — one per model type, shipped in the wheel.

Apps that present latris models (charts, figures, share links, chat connectors) test against these
rather than copies of payloads, so a change in what the library records fails their tests when they
pin the release that makes it, instead of silently breaking a live surface.

``build_example(name, root)`` builds one example project (structure, parameters, datasets and its
analyses, recorded the way a person running them would); ``example_payloads(workdir)`` builds them
all and returns every recorded payload of every result kind. Together the examples record every
result kind the library has: ``tests/test_testing_examples.py`` fails when one is missing.

Builds commit to git, so set a git identity (``GIT_AUTHOR_NAME`` / ``GIT_AUTHOR_EMAIL`` and the
committer pair) first; nothing here needs a network or an AI key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EXAMPLES_DIR = Path(__file__).parent / "examples"


@dataclass(frozen=True)
class Example:
    name: str
    model_types: tuple[str, ...]  # selected for the project, first is the spec's ``model_type``
    question: str
    datasets: dict[str, str] = field(default_factory=dict)  # dataset name → CSV file in ``examples/``

    @property
    def spec_path(self) -> Path:
        return EXAMPLES_DIR / f"{self.name}.json"


EXAMPLES: dict[str, Example] = {e.name: e for e in (
    Example("system", ("sd", "bn", "cld"), "What drives urban air quality and its health effects?"),
    Example("mcda", ("mcda",), "Which site should the new hospital go on?"),
    Example("ach", ("ach",), "Why did the payments service go down on Tuesday?"),
    Example("decision_tree", ("decision_tree",), "Should we launch now or run a pilot first?"),
    Example("markov", ("markov",), "Is the new drug cost-effective?"),
    Example("fault_tree", ("fault_tree",), "How likely is a loss of cooling, and what drives it?"),
    Example("bow_tie", ("bow_tie", "event_tree"), "How well protected are we against a loss of containment?"),
    Example("event_tree", ("event_tree",), "What follows a gas release, and how often?"),
    Example("theory_of_change", ("theory_of_change",), "Does the mentoring programme raise school completion?"),
    Example("toc_impact", ("theory_of_change",), "Did mentoring raise attendance?",
            datasets={"registers": "registers.csv", "schools": "schools.csv"}),
    Example("effect_estimate", ("dag",), "How much does exercise improve heart health?",
            datasets={"survey": "survey.csv"}),
    Example("fcm", ("fcm",), "What happens to congestion when fuel gets dearer?"),
)}


def example_spec_text(name: str) -> str:
    """The example's build spec (JSON), as ``latris build --spec`` reads it."""
    return EXAMPLES[name].spec_path.read_text(encoding="utf-8")


def build_example(name: str, root: Path) -> Path:
    """Build example ``name`` as a new project at ``root`` and run its analyses; returns ``root``.

    Raises ValueError if any analysis in the spec didn't run, so a broken example fails loudly.
    """
    from latris.operations import datasets
    from latris.operations.build import build_from_spec, load_spec
    from latris.operations.init import init_project
    from latris.operations.project import update_selected_models

    ex = EXAMPLES[name]
    init_project(root, statement=ex.question, name=name)
    update_selected_models(list(ex.model_types), root=root)
    for ds_name, file in ex.datasets.items():
        datasets.upload_dataset(EXAMPLES_DIR / file, name=ds_name, root=root)
    built = build_from_spec(load_spec(example_spec_text(name)), root=root)
    if built.notes:
        raise ValueError(f"example {name!r}: " + "; ".join(built.notes))
    return root


def example_payloads(workdir: Path) -> dict[str, list[dict[str, Any]]]:
    """Build every example under ``workdir`` and return {result kind: the payloads its reports show}.

    A kind can have several (e.g. ``toc-impact`` as interrupted time series and as
    difference-in-differences), and each may draw different charts.
    """
    from latris.operations.analysis_results import get_result, report_results

    out: dict[str, list[dict[str, Any]]] = {}
    for name in EXAMPLES:
        root = build_example(name, workdir / name)
        for r in report_results(root=root, include_hidden=True):
            _, payload = get_result(r.run.id, root=root)
            if payload is not None:
                out.setdefault(r.run.result_kind, []).append(payload)
    return out
