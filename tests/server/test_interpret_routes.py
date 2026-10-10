"""Server-side tests for `/api/interpret/*` routes.

Focuses on the AI interrogation Phase 2b decoration: every section
returned by an interpret endpoint must carry ``hedge_active`` and
``coverage_ratio`` so the GUI can surface the hedge indicator.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations.commit import auto_commit
from latris.operations.edges import add_edge
from latris.operations.evidence import add_evidence
from latris.operations.findings import record_new_finding, set_finding_maturity
from latris.operations.init import init_project
from latris.operations.interpret import initialise_sections
from latris.operations.nodes import add_node
from latris.operations.references import add_reference
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import dump_model, load_model
from latris.schema.project import ProjectFoundation
from latris.server.app import create_app


@pytest.fixture
def project_with_cld(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="What drives nutrient runoff?")
    paths = ProjectPaths(root)
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    foundation.selected_model_types = ["cld"]
    dump_model(foundation, paths.project_yaml)
    auto_commit(root, subject="Select CLD", paths=[paths.project_yaml])

    add_node("Nutrient load", root=root)
    add_node("Algal bloom", root=root)
    add_edge("Nutrient load", "Algal bloom", root=root)
    add_edge("Algal bloom", "Nutrient load", root=root)
    return root


@pytest.fixture
def client(project_with_cld: Path) -> TestClient:
    return TestClient(create_app(project_root=project_with_cld))


def test_get_interpretation_decorates_hedge_signals(
    client: TestClient, project_with_cld: Path
) -> None:
    initialise_sections(root=project_with_cld)
    resp = client.get("/api/interpret")
    assert resp.status_code == 200
    sections = resp.json()["sections"]
    assert sections, "expected at least one interpret section"
    for s in sections:
        assert "hedge_active" in s
        assert "coverage_ratio" in s
        # Empty evidence base + zero accepted findings → hedge active.
        if s["model_type"] == "cld":
            assert s["hedge_active"] is True
            assert s["coverage_ratio"] == 0.0


def test_initialise_response_includes_hedge_signals(
    client: TestClient, project_with_cld: Path
) -> None:
    record_new_finding(
        "Some structural finding",
        category="structure",
        model_type="cld",
        root=project_with_cld,
    )
    resp = client.post("/api/interpret/initialise")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sections"]
    cld_section = next(s for s in body["sections"] if s["model_type"] == "cld")
    assert "hedge_active" in cld_section
    assert "coverage_ratio" in cld_section


def test_hedge_signals_clear_when_findings_accepted(
    client: TestClient, project_with_cld: Path
) -> None:
    """Accepting a finding must flip hedge_active to False on subsequent fetch."""
    finding, _ = record_new_finding(
        "High connectivity",
        category="structure",
        model_type="cld",
        root=project_with_cld,
    )
    initialise_sections(root=project_with_cld)

    sections = client.get("/api/interpret").json()["sections"]
    cld = next(s for s in sections if s["model_type"] == "cld")
    assert cld["hedge_active"] is True

    set_finding_maturity(finding.id, maturity="approved", root=project_with_cld)

    sections_after = client.get("/api/interpret").json()["sections"]
    cld_after = next(s for s in sections_after if s["model_type"] == "cld")
    assert cld_after["hedge_active"] is False


def test_hedge_signals_clear_above_threshold(
    client: TestClient, project_with_cld: Path
) -> None:
    """Pushing coverage above 50% must flip hedge_active to False."""
    initialise_sections(root=project_with_cld)
    add_reference("ref1", title="Ref 1", root=project_with_cld)
    # 4 elements (2 nodes + 2 edges); cite 3 → 75% > 0.5.
    add_evidence("Nutrient load", "description", "ref1", root=project_with_cld)
    add_evidence("Algal bloom", "description", "ref1", root=project_with_cld)
    # Cite an edge by resolving via the substrate.
    from latris.repo.yaml_io import load_model as _lm
    from latris.schema import Substrate

    sub = _lm(Substrate, ProjectPaths(project_with_cld).conceptual_yaml)
    add_evidence(sub.edges[0].id, "polarity", "ref1", root=project_with_cld)

    sections = client.get("/api/interpret").json()["sections"]
    cld = next(s for s in sections if s["model_type"] == "cld")
    assert cld["hedge_active"] is False
    assert cld["coverage_ratio"] >= 0.5


# ── Claim refresh + CRUD + AI prose endpoints ────────────────────────────


def _first_section_id(client: TestClient) -> str:
    sections = client.get("/api/interpret").json()["sections"]
    assert sections, "expected initialised sections"
    return sections[0]["id"]


def test_refresh_claims_single_section(
    client: TestClient, project_with_cld: Path
) -> None:
    initialise_sections(root=project_with_cld)
    section_id = _first_section_id(client)

    resp = client.post(f"/api/interpret/refresh-claims/{section_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["section"]["id"] == section_id
    # Decoration is applied to the single-section response too.
    assert "hedge_active" in body["section"]
    assert "coverage_ratio" in body["section"]
    # Structural claims are extracted deterministically from the substrate.
    assert body["section"]["claims"], "expected non-empty extracted claims"
    assert body["commit_sha"]


def test_refresh_all_claims(client: TestClient, project_with_cld: Path) -> None:
    initialise_sections(root=project_with_cld)
    resp = client.post("/api/interpret/refresh-all-claims")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sections"], "expected sections in refresh-all response"
    for s in body["sections"]:
        assert "hedge_active" in s
        assert "coverage_ratio" in s
    assert body["commit_sha"]


def test_patch_prose_saves_human_edit(
    client: TestClient, project_with_cld: Path
) -> None:
    initialise_sections(root=project_with_cld)
    section_id = _first_section_id(client)

    resp = client.patch(
        f"/api/interpret/{section_id}/prose",
        json={"prose": "Hand-written interpretation."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["section"]["id"] == section_id
    assert body["section"]["prose"] == "Hand-written interpretation."
    assert body["section"]["generation_state"] == "edited"
    assert "hedge_active" in body["section"]
    assert body["commit_sha"]


def test_sections_for_model_returns_specs(client: TestClient) -> None:
    resp = client.get("/api/interpret/sections-for-model/cld")
    assert resp.status_code == 200
    specs = resp.json()["specs"]
    assert specs, "expected at least one section spec for cld"
    section_types = {s["section_type"] for s in specs}
    assert "structural_summary" in section_types
    for s in specs:
        assert "cld" in s["applicable_model_types"]
        assert s["prompt_name"]


def test_sections_for_model_unknown_returns_empty(client: TestClient) -> None:
    resp = client.get("/api/interpret/sections-for-model/not_a_model_type")
    assert resp.status_code == 200
    assert resp.json()["specs"] == []


# ── AI prose generation (mocked) ─────────────────────────────────────────


def _register_prose_mock(text: str = "Mock interpretation prose.") -> None:
    from latris.ai.adapters import MockAdapter
    from latris.ai.adapters.base import ChatResult
    from latris.ai.proposals import InterpretProseResult

    MockAdapter.reset_shared()
    MockAdapter.shared().register_default(
        response_cls=InterpretProseResult,
        result=ChatResult(
            parsed=InterpretProseResult(prose=text),
            raw="(mock prose)",
            model_id="mock",
        ),
    )


def test_generate_prose_happy_path(
    client: TestClient, project_with_cld: Path, monkeypatch
) -> None:
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    _register_prose_mock("Generated structural interpretation.")
    initialise_sections(root=project_with_cld)
    section_id = _first_section_id(client)

    resp = client.post(f"/api/interpret/generate-prose/{section_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["section"]["id"] == section_id
    assert body["section"]["prose"] == "Generated structural interpretation."
    assert body["section"]["generation_state"] == "generated"
    assert "hedge_active" in body["section"]
    assert body["commit_sha"]


def test_generate_prose_blocked_by_completeness_gate(
    client: TestClient, project_with_cld: Path, monkeypatch
) -> None:
    """With blocking-mode on and a required+open gap, prose generation is refused."""
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    _register_prose_mock()
    initialise_sections(root=project_with_cld)
    section_id = _first_section_id(client)

    # Turn on blocking-mode in ai_config.
    from latris.ai import config as ai_config
    from latris.repo.layout import ProjectPaths

    paths = ProjectPaths(project_with_cld)
    cfg = ai_config.load(paths)
    cfg.completeness_gate_blocking = True
    ai_config.save(paths, cfg)

    # Persist a completeness report with a required, open missing variable
    # for the section's model type.
    from latris.operations.completeness import save_report
    from latris.schema import CompletenessReport, MissingVariable

    model_type = client.get("/api/interpret").json()["sections"]
    mt = next(s for s in model_type if s["id"] == section_id)["model_type"]
    report = CompletenessReport(
        model_type=mt,
        entries=[
            MissingVariable(
                name="Rainfall",
                rationale="Required driver.",
                required_for=["answer"],
                severity="required",
                confidence="high",
            )
        ],
    )
    save_report(report, subject="seed blocking report", root=project_with_cld)

    resp = client.post(f"/api/interpret/generate-prose/{section_id}")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error"] == "completeness_gate_blocked"
    assert detail["model_type"] == mt
    assert detail["blocking_missing_variable_ids"]


def test_generate_prose_blocking_mode_passes_when_no_required_gaps(
    client: TestClient, project_with_cld: Path, monkeypatch
) -> None:
    """Blocking-mode on but only non-required/non-open gaps → generation proceeds."""
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    _register_prose_mock("Prose despite recommended gap.")
    initialise_sections(root=project_with_cld)
    section_id = _first_section_id(client)

    from latris.ai import config as ai_config
    from latris.operations.completeness import save_report
    from latris.repo.layout import ProjectPaths
    from latris.schema import CompletenessReport, MissingVariable

    paths = ProjectPaths(project_with_cld)
    cfg = ai_config.load(paths)
    cfg.completeness_gate_blocking = True
    ai_config.save(paths, cfg)

    mt = next(
        s for s in client.get("/api/interpret").json()["sections"]
        if s["id"] == section_id
    )["model_type"]
    # A recommended gap (not "required") must not block generation.
    report = CompletenessReport(
        model_type=mt,
        entries=[
            MissingVariable(
                name="Wind",
                rationale="Nice to have.",
                required_for=[],
                severity="recommended",
                confidence="medium",
            )
        ],
    )
    save_report(report, subject="seed non-blocking report", root=project_with_cld)

    resp = client.post(f"/api/interpret/generate-prose/{section_id}")
    assert resp.status_code == 200
    assert resp.json()["section"]["prose"] == "Prose despite recommended gap."
