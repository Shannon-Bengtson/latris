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
