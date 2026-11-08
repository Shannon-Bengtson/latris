"""`latris link`: the model travels inside an app.latris.app link, offline."""

from __future__ import annotations

import base64
import json
import zlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import share_link
from latris.operations.build import build_from_spec, load_spec
from latris.operations.findings import list_findings
from latris.operations.init import init_project
from latris.operations.interpret import load_interpretation
from latris.operations.project import update_selected_models
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import AssumptionLog, ChallengeLog, ReferenceLibrary

SPEC = """
outcome: Volunteer departures
factors:
  - {label: Workload, description: Hours asked of each volunteer.}
  - {label: Burnout}
  - {label: Volunteer departures}
links:
  - {from: Workload, to: Burnout, polarity: "+", reason: "More hours, more exhaustion.", confidence: high,
     sources: [smith2021], contradicts: [tuohy2015]}
  - {from: Burnout, to: Volunteer departures, polarity: "+", reason: Exhausted volunteers leave.}
  - {from: Volunteer departures, to: Workload, polarity: "+", reason: Fewer people share the work.}
sources:
  - {key: smith2021, title: Volunteer burnout, authors: ["Smith, J"], year: 2021, notes: "n=412; burnout OR 2.1"}
  - {key: tuohy2015, title: Workload and retention revisited, year: 2015}
assumptions:
  - Service demand stays steady.
  - {text: Hours are comparable across programs., target: Workload -> Burnout, rationale: Same roster rules.}
questions: ["Does recognition matter independently of workload?"]
findings:
  - {statement: Overload is a reinforcing loop., category: structure, targets: [Workload, Burnout -> Volunteer departures]}
challenges:
  - {argument: Burnout may lag workload by months., target: Workload -> Burnout}
interpretation:
  - {section: answer_to_question, prose: Workload drives departures through burnout.}
"""


def _project(root: Path) -> Path:
    init_project(root, statement="Why are volunteers leaving?", name="Volunteers")
    update_selected_models(["cld"], root=root)
    return root


@pytest.fixture
def built(tmp_path: Path, git_identity) -> Path:
    root = _project(tmp_path / "a")
    build_from_spec(load_spec(SPEC), root=root)
    return root


def test_the_spec_carries_targets_findings_challenges_and_prose(built: Path) -> None:
    paths = ProjectPaths(built)
    assumptions = load_model(AssumptionLog, paths.assumptions_yaml).entries
    assert assumptions[1].target_id and assumptions[1].target_id.startswith("edge_")
    assert assumptions[1].rationale == "Same roster rules."
    assert load_model(ReferenceLibrary, paths.references_yaml).entries[0].notes == "n=412; burnout OR 2.1"
    (finding,) = list_findings(root=built)
    assert finding.maturity == "proposed" and len(finding.target_ids) == 2
    (challenge,) = load_model(ChallengeLog, paths.challenges_yaml).entries
    assert challenge.state == "open" and challenge.target_id.startswith("edge_")
    answer = next(s for s in load_interpretation(root=built).sections if s.section_type == "answer_to_question")
    assert answer.prose == "Workload drives departures through burnout."
    assert answer.claims and answer.claims_at_generation == answer.claims  # not stale on arrival


def test_bad_targets_are_refused_before_anything_changes(tmp_path: Path, git_identity) -> None:
    root = _project(tmp_path / "b")
    bad = SPEC.replace("target: Workload -> Burnout, rationale", "target: Workload -> Nowhere, rationale")
    bad = bad.replace("section: answer_to_question", "section: the_answer")
    with pytest.raises(ValueError) as exc:
        build_from_spec(load_spec(bad), root=root)
    assert "no link 'Workload -> Nowhere'" in str(exc.value)
    assert "no section 'the_answer'" in str(exc.value)


def test_round_trip_through_a_link(built: Path, tmp_path: Path, git_identity) -> None:
    link = share_link.make_link(root=built)
    assert link.url.startswith("https://app.latris.app/open#")
    assert (link.factors, link.links, link.long) == (3, 3, False)

    payload = share_link.decode_payload(link.url.split("#", 1)[1])
    assert payload.name == "Volunteers" and payload.question == "Why are volunteers leaving?"

    copy = _project(tmp_path / "copy")
    build_from_spec(payload.spec, root=copy)
    _, original = share_link.export_spec(root=built)
    _, again = share_link.export_spec(root=copy)
    assert again == original


def test_app_url_can_be_overridden(built: Path, monkeypatch) -> None:
    monkeypatch.setenv(share_link.APP_URL_ENV, "http://localhost:8770/")
    assert share_link.make_link(root=built).url.startswith("http://localhost:8770/open#")


@pytest.mark.parametrize(
    "fragment",
    ["", "not-base64!!", base64.urlsafe_b64encode(b"plain").decode(), "#" + "A" * 50],
)
def test_malformed_links_are_refused(fragment: str) -> None:
    with pytest.raises(ValueError, match="isn't a Latris model link"):
        share_link.decode_payload(fragment)


def _pack(obj: object) -> str:
    comp = zlib.compressobj(level=9, wbits=-15)
    data = comp.compress(json.dumps(obj).encode()) + comp.flush()
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def test_oversized_and_future_links_are_refused() -> None:
    huge = {"v": 1, "name": "x", "question": "q", "spec": {"questions": ["y" * 500_000]}}
    with pytest.raises(ValueError, match="too large"):
        share_link.decode_payload(_pack(huge))
    with pytest.raises(ValueError, match="newer Latris"):
        share_link.decode_payload(_pack({"v": 9, "name": "x", "question": "q", "spec": {}}))


def test_cli_prints_the_link_and_json(built: Path, monkeypatch) -> None:
    monkeypatch.chdir(built)
    out = CliRunner().invoke(app, ["link"])
    assert out.exit_code == 0, out.output
    assert out.output.splitlines()[0].startswith("https://app.latris.app/open#")
    assert "Nothing was uploaded" in out.output
    data = json.loads(CliRunner().invoke(app, ["--json", "link"]).stdout.strip().splitlines()[-1])["result"]
    assert data["factors"] == 3 and data["url"].startswith("https://app.latris.app/open#")


def test_export_points_agents_at_the_link(built: Path, monkeypatch) -> None:
    monkeypatch.chdir(built)
    out = CliRunner().invoke(app, ["export", "md", "--no-ai", "-o", "r.md"])
    assert "`latris link`" in out.output
    quiet = CliRunner().invoke(app, ["--json", "export", "md", "--no-ai", "-o", "r.md"])
    assert "latris link" not in quiet.output


# ── quantified models: parameters travel, results are recomputed on arrival ──


def _comparable(root: Path) -> list[tuple[str, dict]]:
    """Report results with node ids replaced by labels (ids differ between projects)."""
    from latris.operations import analysis_results as ar
    from latris.schema import Substrate

    sub = load_model(Substrate, ProjectPaths(root).conceptual_yaml)
    names = {e.id: e.label for e in sub.entities} | {e.id: "edge" for e in sub.edges}
    out = []
    for r in ar.report_results(root=root):
        text = json.dumps({k: v for k, v in r.payload.items() if k != "seconds"}, sort_keys=True)
        for i, label in names.items():
            text = text.replace(i, label)
        out.append((r.run.result_kind, json.loads(text)))
    return out


def test_an_sd_model_travels_with_its_analyses(sd_bathtub_root: Path, tmp_path: Path) -> None:
    pytest.importorskip("scipy")
    from latris.operations import sd as sd_ops
    from latris.operations import sd_scenarios, uncertainty

    root = sd_bathtub_root
    update_selected_models(["sd"], root=root)
    settings = {"final_time": 10, "dt": 0.25, "method": "euler"}
    sd_scenarios.set_scenario("Faster drain", ["Drain Rate=0.2"], reason="plumber's quote", root=root)
    uncertainty.set_uncertainty("Drain Rate", "triangular", {"min": 0.05, "mode": 0.1, "max": 0.2},
                                origin="ai-proposed", root=root)
    payload, runs = sd_ops.simulate_scenarios(["Faster drain"], ["Inflow Rate=6"], **settings, root=root)
    sd_ops.record_comparison(payload, runs, root=root)
    sd_ops.record_monte_carlo(sd_ops.run_monte_carlo(runs=50, seed=7, settings=settings, root=root), root=root)
    sd_ops.record_sensitivity(sd_ops.run_sensitivity("Water", metric="at:5", settings=settings, root=root),
                              root=root)
    sd_ops.record_loops(sd_ops.run_loops(scenario="Faster drain", settings=settings, root=root), root=root)

    link = share_link.make_link(root=root)
    assert not link.long and link.chars < 10_000
    spec = share_link.decode_payload(link.url.split("#", 1)[1]).spec
    assert [a.kind for a in spec.analyses] == ["simulate", "monte_carlo", "sensitivity", "loops"]

    copy = tmp_path / "copy"
    init_project(copy, statement="How full does the bathtub get?")
    update_selected_models(["sd"], root=copy)
    result = build_from_spec(spec, verified_by="ai", root=copy)
    assert not result.notes and len(result.analyses) == 4 and result.parameters >= 10
    assert _comparable(copy) == _comparable(root)
    (range_,) = uncertainty.list_uncertainty(root=copy)
    assert range_.origin == "ai-proposed" and range_.verification == "unverified"


def test_a_bn_model_travels_with_its_query(tmp_path: Path, git_identity) -> None:
    pytest.importorskip("pgmpy")
    from latris.operations import bn as bn_ops
    from latris.operations import edges as edge_ops
    from latris.operations import nodes as node_ops

    root = tmp_path / "bn"
    init_project(root, statement="Will it be wet?")
    update_selected_models(["bn"], root=root)
    rain = node_ops.add_node("Rain", kind="variable", root=root)[0]
    sprinkler = node_ops.add_node("Sprinkler", kind="variable", root=root)[0]
    wet = node_ops.add_node("Wet", kind="variable", root=root)[0]
    edge_ops.add_edge(rain.id, wet.id, kind="causal", root=root)
    edge_ops.add_edge(sprinkler.id, wet.id, kind="causal", root=root)
    for n in ("Rain", "Sprinkler", "Wet"):
        bn_ops.set_state_space(n, ["yes", "no"], root=root)
    bn_ops.set_cpt("Rain", [], [0.2, 0.8], root=root)
    bn_ops.set_cpt("Sprinkler", [], [0.4, 0.6], root=root)
    bn_ops.set_cpt("Wet", ["Rain", "Sprinkler"], [0.99, 0.01, 0.9, 0.1, 0.8, 0.2, 0.05, 0.95], root=root)
    bn_ops.record_query(bn_ops.infer(query=["Rain"], evidence={"Wet": "yes"}, root=root), root=root)

    spec = share_link.decode_payload(share_link.make_link(root=root).url.split("#", 1)[1]).spec
    assert spec.bn and spec.bn.tables[2].probabilities == [0.99, 0.01, 0.9, 0.1, 0.8, 0.2, 0.05, 0.95]
    copy = tmp_path / "copy"
    init_project(copy, statement="Will it be wet?")
    update_selected_models(["bn"], root=copy)
    build_from_spec(spec, root=copy)
    assert _comparable(copy) == _comparable(root)
