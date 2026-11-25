"""Refusals and repairs found by clicking through Build, Data and References."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from latris.operations.init import init_project
from latris.server.app import create_app

CSV = b"pm25,traffic\n1,2\n3,4\n"


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="Test")
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


def _upload(client: TestClient, filename: str = "air quality.csv", **data: str):
    return client.post("/api/datasets/upload", files={"file": (filename, CSV, "text/csv")}, data=data)


def test_an_uploaded_dataset_is_named_after_its_file(client: TestClient) -> None:
    assert _upload(client).json()["result"]["name"] == "air quality"
    assert _upload(client).json()["result"]["name"] == "air quality (2)"
    assert _upload(client, name="Monitoring").json()["result"]["name"] == "Monitoring"


def test_clip_needs_a_numeric_bound(client: TestClient) -> None:
    ds = _upload(client).json()["result"]["id"]
    bad = client.post(f"/api/datasets/{ds}/operations", json={"kind": "clip_values", "params": {"column": "pm25", "min": None, "max": None}})
    assert bad.status_code == 422 and "lowest" in bad.json()["detail"]
    assert "Clipped" not in str(client.get(f"/api/datasets/{ds}/actions").json())
    text = client.post(f"/api/datasets/{ds}/operations", json={"kind": "clip_values", "params": {"column": "pm25", "min": "a", "max": 3}})
    assert text.status_code == 422


def test_data_evidence_checks_columns_refuses_duplicates_and_can_be_removed(client: TestClient) -> None:
    ds = _upload(client).json()["result"]["id"]
    node = client.post("/api/nodes", json={"label": "PM2.5"}).json()["result"]["id"]
    body = {"target": node, "dataset_id": ds, "column_names": ["pm25"]}
    unknown = client.post("/api/evidence/data-links", json={**body, "column_names": ["nope"]})
    assert unknown.status_code == 422 and "no column 'nope'" in unknown.json()["detail"]
    assert client.post("/api/evidence/data-links", json=body).status_code == 201
    again = client.post("/api/evidence/data-links", json=body)
    assert again.status_code == 422 and "already attached" in again.json()["detail"]
    assert client.post("/api/evidence/data-links/remove", json=body).status_code == 200
    assert client.post("/api/evidence/data-links/remove", json=body).status_code == 404


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/provenance/assumptions", {"statement": "   "}),
        ("/api/provenance/questions", {"question": ""}),
        ("/api/provenance/decisions", {"statement": " ", "rationale": "x"}),
        ("/api/challenges", {"argument": "  "}),
    ],
)
def test_a_blank_record_is_refused(client: TestClient, path: str, body: dict) -> None:
    r = client.post(path, json=body)
    assert r.status_code == 422, r.text
    assert "needs some text" in r.json()["detail"]


def test_a_blank_project_name_is_refused(client: TestClient) -> None:
    r = client.patch("/api/project", json={"name": "  "})
    assert r.status_code == 422 and "needs a name" in r.json()["detail"]


def test_a_reference_url_is_a_web_address(client: TestClient) -> None:
    bad = client.post("/api/references", json={"bibkey": "x2024", "title": "T", "url": "javascript:alert(1)"})
    assert bad.status_code == 422 and "http://" in bad.json()["detail"]
    assert client.post("/api/references", json={"bibkey": "x2024", "title": "T", "url": "https://example.org/a"}).status_code == 201
    assert client.put("/api/references/x2024", json={"url": "data:text/html,hi"}).status_code == 422
    assert client.put("/api/references/x2024", json={"url": "ftp://example.org/a"}).status_code == 422
    bare = client.put("/api/references/x2024", json={"url": "www.who.int/guidelines"})
    assert bare.status_code == 200 and bare.json()["result"]["url"] == "https://www.who.int/guidelines"
    port = client.put("/api/references/x2024", json={"url": "example.org:8080/x"})
    assert port.json()["result"]["url"] == "https://example.org:8080/x"


def test_removing_a_cited_reference_is_refused_in_plain_words(client: TestClient) -> None:
    client.post("/api/references", json={"bibkey": "x2024", "title": "T"})
    node = client.post("/api/nodes", json={"label": "A"}).json()["result"]["id"]
    assert client.post("/api/evidence", json={"target": node, "bibkey": "x2024"}).status_code == 201
    r = client.delete("/api/references/x2024")
    assert r.status_code == 422
    assert "citation still uses it" in r.json()["detail"] and "latris" not in r.json()["detail"]


def test_bibtex_latex_is_decoded(client: TestClient) -> None:
    bib = '@article{m2020, title={Exposure to {PM2.5} in {M}unich}, author={M{\\"u}ller, Jos{\\\'e} and Doe, A.}, journal={{Air} Journal}, year={2020}}'
    ref = client.post("/api/references/import-bibtex", json={"bibtex": bib}).json()["result"][0]
    assert ref["title"] == "Exposure to PM2.5 in Munich"
    assert ref["authors"] == ["Müller, José", "Doe, A."]
    assert ref["container"] == "Air Journal"


def test_bibtex_import_drops_a_url_that_is_not_a_web_address(client: TestClient) -> None:
    bib = "@misc{a1, title={A}, url={javascript:alert(1)}}\n@misc{b1, title={B}, url={https://example.org/b}}"
    refs = {r["bibkey"]: r for r in client.post("/api/references/import-bibtex", json={"bibtex": bib}).json()["result"]}
    assert refs["a1"]["url"] is None and refs["b1"]["url"] == "https://example.org/b"


def test_a_lookup_that_cannot_reach_the_service_says_so(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def down(*_a, **_k):
        raise httpx.ConnectError("proxy refused")

    monkeypatch.setattr(httpx, "get", down)
    r = client.post("/api/references/import-doi", json={"doi": "10.1000/xyz123"})
    assert r.status_code == 422 and "Couldn't reach" in r.json()["detail"]
    s = client.get("/api/references/search", params={"q": "air"})
    assert s.status_code == 422 and "Couldn't reach" in s.json()["detail"]


def test_a_duplicate_label_is_refused_without_an_internal_id(client: TestClient) -> None:
    client.post("/api/nodes", json={"label": "A"})
    r = client.post("/api/nodes", json={"label": "A"})
    assert r.status_code == 422 and "node_" not in r.json()["detail"]
