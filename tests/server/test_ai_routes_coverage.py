"""Coverage-focused tests for AI routes: prompts, chains, ExpandBibliography,
and SuggestCitations URL validation.

These exercise the server-side transform paths (OpenAlex search,
URL validation) with the network dependencies monkeypatched, plus the
prompt-chain start/advance/reject/abort endpoints. Hermetic — relies on
LATRIS_AI_MOCK=1 and stubbed network calls.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from latris.ai import proposals as P
from latris.ai.adapters.base import ChatResult
from latris.ai.adapters.mock_adapter import MockAdapter
from latris.operations import nodes as node_ops
from latris.operations import references as ref_ops
from latris.operations.init import init_project
from latris.server.app import create_app


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    MockAdapter.reset_shared()
    yield
    MockAdapter.reset_shared()


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="Water quality and price drivers?")
    node_ops.add_node("Price", kind="variable", root=root)
    node_ops.add_node("Demand", kind="variable", root=root)
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project), raise_server_exceptions=False)


# ── mock registration helpers ────────────────────────────────────────


def _register_draft() -> None:
    MockAdapter.shared().register_default(
        response_cls=P.DraftModelProposal,
        result=ChatResult(
            parsed=P.DraftModelProposal(
                framings=[
                    P.DraftFraming(
                        name="Framing A",
                        entities=[P.DraftEntity(label="Supply", kind="variable")],
                        edges=[P.DraftEdge(from_label="Supply", to_label="Demand")],
                        rationale="Supply-side.",
                    ),
                ],
            ),
            raw="(raw)",
            model_id="mock-model",
            token_usage={"input_tokens": 10, "output_tokens": 20},
            cost_usd=0.001,
        ),
    )


def _register_assumptions() -> None:
    MockAdapter.shared().register_default(
        response_cls=P.AssumptionsProposal,
        result=ChatResult(
            parsed=P.AssumptionsProposal(target_id="x", assumptions=[]),
            raw="(raw)",
            model_id="mock-model",
        ),
    )


def _register_search_plan() -> None:
    MockAdapter.shared().register_default(
        response_cls=P.BibliographySearchPlan,
        result=ChatResult(
            parsed=P.BibliographySearchPlan(
                queries=[
                    P.SearchQuery(query="water quality pricing", rationale="core topic"),
                    P.SearchQuery(query="coastal demand", rationale="adjacent"),
                ],
            ),
            raw="(raw)",
            model_id="mock-model",
            token_usage={"input_tokens": 5, "output_tokens": 5},
            cost_usd=0.0,
        ),
    )


def _register_citations() -> None:
    MockAdapter.shared().register_default(
        response_cls=P.CitationsProposal,
        result=ChatResult(
            parsed=P.CitationsProposal(
                new_references=[
                    P.CitationSuggestion(
                        bibkey="smith2020",
                        title="Pricing water",
                        url="https://example.org/smith2020",
                    ),
                    P.CitationSuggestion(
                        bibkey="nolink2019",
                        title="No link here",
                    ),
                ],
                evidence_links=[],
            ),
            raw="(raw)",
            model_id="mock-model",
        ),
    )


def _fake_search_results(query: str, *, limit: int = 10):
    """Two refs; the second is shared across queries to exercise dedup."""
    return [
        SimpleNamespace(
            bibkey="openalex_a",
            title="Water Quality Pricing Models",
            authors=["A. Author", "B. Author", "C. Author", "D. Author"],
            year=2021,
            doi="10.1/abc",
            url="https://openalex.org/a",
            abstract="A study of water quality and price demand drivers.",
        ),
        SimpleNamespace(
            bibkey="openalex_dup",
            title="Shared Title",
            authors=["E. Author"],
            year=2019,
            doi=None,
            url="https://openalex.org/dup",
            abstract="unrelated topic",
        ),
    ]


# ── /prompts and /chains listing ─────────────────────────────────────


def test_list_prompts(client: TestClient) -> None:
    resp = client.get("/api/ai/prompts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    sample = data[0]
    assert {"name", "title", "description", "scope", "intent", "wired"} <= set(sample)
    names = {p["name"] for p in data}
    assert "DraftConceptualModel" in names


def test_list_chains(client: TestClient) -> None:
    resp = client.get("/api/ai/chains")
    assert resp.status_code == 200
    data = resp.json()
    names = {c["name"] for c in data}
    assert "draft-model" in names
    draft = next(c for c in data if c["name"] == "draft-model")
    assert draft["step_count"] == 3
    assert draft["steps"][0] == "DraftConceptualModel"


# ── ExpandBibliography / FindFoundationalReferences flow ─────────────


@pytest.mark.parametrize("prompt_name", ["ExpandBibliography", "FindFoundationalReferences"])
def test_bibliography_preview_searches_openalex(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, prompt_name: str
) -> None:
    _register_search_plan()
    monkeypatch.setattr(ref_ops, "search_references", _fake_search_results)

    resp = client.post(
        "/api/ai/call",
        json={"prompt_name": prompt_name, "inputs": {}, "auto_apply": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["adoption"] == "pending"
    refs = data["proposal"]["new_references"]
    # Two queries return the same two refs each; dedup by title keeps 2.
    assert len(refs) == 2
    assert {r["bibkey"] for r in refs} == {"openalex_a", "openalex_dup"}
    assert all(r["url_verified"] for r in refs)
    assert "Semantic Scholar" in data["rendered"]


def test_bibliography_apply_uses_cache(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    _register_search_plan()
    monkeypatch.setattr(ref_ops, "search_references", _fake_search_results)

    resp = client.post(
        "/api/ai/call",
        json={"prompt_name": "ExpandBibliography", "inputs": {}, "auto_apply": False},
    )
    interaction_id = resp.json()["interaction_id"]

    resp = client.post(
        f"/api/ai/apply/{interaction_id}",
        json={"approved_indices": [0]},
    )
    assert resp.status_code == 200
    applied = resp.json()["applied_ids"]
    assert len(applied) == 1  # only index 0 approved

    bibkeys = {r.bibkey for r in ref_ops.list_references(root=project)}
    assert "openalex_a" in bibkeys
    assert "openalex_dup" not in bibkeys  # index 1 not approved


def test_bibliography_apply_all(client: TestClient, monkeypatch: pytest.MonkeyPatch, project: Path) -> None:
    _register_search_plan()
    monkeypatch.setattr(ref_ops, "search_references", _fake_search_results)

    resp = client.post(
        "/api/ai/call",
        json={"prompt_name": "ExpandBibliography", "inputs": {}, "auto_apply": False},
    )
    interaction_id = resp.json()["interaction_id"]

    # No approved_indices → apply all cached references.
    resp = client.post(f"/api/ai/apply/{interaction_id}", json={})
    assert resp.status_code == 200
    assert len(resp.json()["applied_ids"]) == 2

    bibkeys = {r.bibkey for r in ref_ops.list_references(root=project)}
    assert {"openalex_a", "openalex_dup"} <= bibkeys


def test_bibliography_apply_expired_cache_returns_410(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register_search_plan()
    monkeypatch.setattr(ref_ops, "search_references", _fake_search_results)

    resp = client.post(
        "/api/ai/call",
        json={"prompt_name": "ExpandBibliography", "inputs": {}, "auto_apply": False},
    )
    interaction_id = resp.json()["interaction_id"]

    # Simulate cache eviction (e.g. server restart).
    from latris.server.routes import ai as ai_routes

    ai_routes._expand_bib_cache.clear()

    resp = client.post(f"/api/ai/apply/{interaction_id}", json={})
    assert resp.status_code == 410


# ── SuggestCitations URL validation ──────────────────────────────────


def test_suggest_citations_validates_urls(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register_citations()
    from latris.ai import validate_urls

    monkeypatch.setattr(validate_urls, "check_url", lambda url: True)

    nodes = client.get("/api/nodes").json()
    resp = client.post(
        "/api/ai/call",
        json={
            "prompt_name": "SuggestCitations",
            "inputs": {"target_id": nodes[0]["id"], "target_attribute": "description"},
            "auto_apply": False,
        },
    )
    assert resp.status_code == 200
    refs = resp.json()["proposal"]["new_references"]
    # The reference with no URL/DOI is dropped; the one with a URL is verified.
    assert len(refs) == 1
    assert refs[0]["bibkey"] == "smith2020"
    assert refs[0]["url_verified"] is True


def test_suggest_citations_apply_with_indices(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    from latris.ai import validate_urls

    monkeypatch.setattr(validate_urls, "check_url", lambda url: True)

    nodes = client.get("/api/nodes").json()
    target_id = nodes[0]["id"]

    MockAdapter.shared().register_default(
        response_cls=P.CitationsProposal,
        result=ChatResult(
            parsed=P.CitationsProposal(
                new_references=[
                    P.CitationSuggestion(
                        bibkey="keep2020", title="Keep me", url="https://example.org/keep"
                    ),
                ],
                evidence_links=[
                    P.EvidenceAttachment(
                        target_id=target_id,
                        attribute="existence",
                        bibkey="keep2020",
                        rationale="supports it",
                    ),
                ],
            ),
            raw="(raw)",
            model_id="mock-model",
        ),
    )

    resp = client.post(
        "/api/ai/call",
        json={
            "prompt_name": "SuggestCitations",
            "inputs": {"target_id": target_id, "target_attribute": "description"},
            "auto_apply": False,
        },
    )
    interaction_id = resp.json()["interaction_id"]

    resp = client.post(
        f"/api/ai/apply/{interaction_id}",
        json={"approved_indices": [0, 1]},
    )
    assert resp.status_code == 200
    assert len(resp.json()["applied_ids"]) >= 1

    bibkeys = {r.bibkey for r in ref_ops.list_references(root=project)}
    assert "keep2020" in bibkeys


# ── Chain start / advance / reject / abort ───────────────────────────


def test_chain_start_happy(client: TestClient) -> None:
    _register_draft()
    resp = client.post(
        "/api/ai/chain/start",
        json={"chain_name": "draft-model", "inputs": {"focus": "Price"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["chain_name"] == "draft-model"
    assert data["step_index"] == 0
    assert data["total_steps"] == 3
    assert data["step_prompt_name"] == "DraftConceptualModel"
    assert data["chain_status"] == "active"
    assert data["result"]["adoption"] == "pending"
    assert data["session_id"]


def test_chain_start_unknown_chain_returns_404(client: TestClient) -> None:
    resp = client.post(
        "/api/ai/chain/start",
        json={"chain_name": "no-such-chain", "inputs": {}},
    )
    assert resp.status_code == 404


def test_chain_advance_happy(client: TestClient) -> None:
    _register_draft()
    _register_assumptions()
    start = client.post(
        "/api/ai/chain/start",
        json={"chain_name": "draft-model", "inputs": {"focus": "Price"}},
    ).json()
    session_id = start["session_id"]

    # Approve + apply framing 0, advance to the GenerateAssumptions step.
    resp = client.post(
        f"/api/ai/chain/advance/{session_id}",
        json={"selected_index": 0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["step_index"] == 1
    assert data["step_prompt_name"] == "GenerateAssumptions"
    assert data["result"]["prompt_name"] == "GenerateAssumptions"


def test_chain_advance_unknown_session_returns_404(client: TestClient) -> None:
    resp = client.post("/api/ai/chain/advance/nope", json={})
    assert resp.status_code == 404


def test_chain_reject_step_happy(client: TestClient) -> None:
    _register_draft()
    _register_assumptions()
    start = client.post(
        "/api/ai/chain/start",
        json={"chain_name": "draft-model", "inputs": {"focus": "Price"}},
    ).json()
    session_id = start["session_id"]

    resp = client.post(f"/api/ai/chain/reject-step/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["step_index"] == 1
    assert data["step_prompt_name"] == "GenerateAssumptions"


def test_chain_reject_step_unknown_session_returns_404(client: TestClient) -> None:
    resp = client.post("/api/ai/chain/reject-step/nope")
    assert resp.status_code == 404


def test_chain_abort_happy(client: TestClient) -> None:
    _register_draft()
    start = client.post(
        "/api/ai/chain/start",
        json={"chain_name": "draft-model", "inputs": {"focus": "Price"}},
    ).json()
    session_id = start["session_id"]

    resp = client.post(f"/api/ai/chain/abort/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["chain_status"] == "aborted"
    assert data["session_id"] == session_id


def test_chain_abort_unknown_session_returns_404(client: TestClient) -> None:
    resp = client.post("/api/ai/chain/abort/nope")
    assert resp.status_code == 404
