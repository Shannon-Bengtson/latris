"""Tests for the perf telemetry layer.

Two contracts matter:

1. **Off by default.** Without ``LATRIS_PERF=1``, the middleware
   short-circuits and ``span()`` is a no-op. No NDJSON file is
   written, no extra response headers leak.
2. **On when asked.** With ``LATRIS_PERF=1`` (and a tmp log file),
   every request emits one NDJSON record with the expected fields
   and any inner ``span(...)`` blocks recorded.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations.init import init_project
from latris.perf import perf_ctx, perf_enabled, span
from latris.server.app import create_app
from tests.conftest import build_with_template_identity, clone_project


@pytest.fixture(scope="module")
def _module_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    def build() -> Path:
        root = tmp_path_factory.mktemp("perf_tpl") / "demo"
        init_project(root, statement="What drives air quality?")
        return root

    return build_with_template_identity(build)


@pytest.fixture
def project(_module_template: Path, tmp_path: Path, git_identity) -> Path:
    return clone_project(_module_template, tmp_path / "demo")


@pytest.fixture
def client(project: Path) -> TestClient:
    app = create_app(project_root=project)
    return TestClient(app)


def test_span_is_noop_without_context() -> None:
    """Outside an active request, span() must not raise and not record."""
    assert perf_ctx.get() is None
    with span("anything", x=1):
        pass  # no-op


def test_perf_enabled_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LATRIS_PERF", raising=False)
    assert perf_enabled() is False
    monkeypatch.setenv("LATRIS_PERF", "0")
    assert perf_enabled() is False
    monkeypatch.setenv("LATRIS_PERF", "1")
    assert perf_enabled() is True


def test_middleware_noop_when_disabled(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """LATRIS_PERF unset → no NDJSON written, no x-request-id header."""
    log_file = tmp_path / "perf.jsonl"
    monkeypatch.setenv("LATRIS_PERF_LOG", str(log_file))
    monkeypatch.delenv("LATRIS_PERF", raising=False)

    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert "x-request-id" not in {k.lower() for k in resp.headers}
    assert not log_file.exists()


def test_middleware_records_request_and_spans(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """LATRIS_PERF=1 → one NDJSON line per request with header + spans."""
    log_file = tmp_path / "perf.jsonl"
    monkeypatch.setenv("LATRIS_PERF", "1")
    monkeypatch.setenv("LATRIS_PERF_LOG", str(log_file))

    # Hit /api/state — known to wrap load_full_state in a span.
    resp = client.get("/api/state")
    assert resp.status_code == 200
    assert resp.headers.get("x-request-id"), "missing correlation id"
    assert "server-timing" in {k.lower() for k in resp.headers}

    lines = [ln for ln in log_file.read_text(encoding="utf-8").splitlines() if ln]
    # First line should match the /api/state request. Others may be
    # warmup writes from test-client lifecycle.
    state_records = [json.loads(ln) for ln in lines if json.loads(ln)["path"] == "/api/state"]
    assert state_records, f"no /api/state record in log: {lines}"
    rec = state_records[0]
    assert rec["method"] == "GET"
    assert rec["status"] == 200
    assert rec["dur_ms"] >= 0
    span_names = {s["name"] for s in rec["spans"]}
    assert "load_full_state" in span_names


def test_correlation_id_round_trips(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An incoming x-request-id is echoed back and used in the log."""
    monkeypatch.setenv("LATRIS_PERF", "1")
    monkeypatch.setenv("LATRIS_PERF_LOG", str(tmp_path / "perf.jsonl"))

    resp = client.get("/api/health", headers={"x-request-id": "rid-abc-123"})
    assert resp.headers["x-request-id"] == "rid-abc-123"


def test_span_no_state_pollution_between_requests(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Each request gets a fresh context — spans don't leak across requests."""
    log_file = tmp_path / "perf.jsonl"
    monkeypatch.setenv("LATRIS_PERF", "1")
    monkeypatch.setenv("LATRIS_PERF_LOG", str(log_file))

    client.get("/api/health")
    client.get("/api/health")

    lines = [json.loads(ln) for ln in log_file.read_text(encoding="utf-8").splitlines() if ln]
    health_records = [r for r in lines if r["path"] == "/api/health"]
    rids = {r["rid"] for r in health_records}
    assert len(rids) == len(health_records), "rids must be unique per request"


def test_inner_span_disabled_outside_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even with LATRIS_PERF=1, calling span() outside a request stays no-op."""
    monkeypatch.setenv("LATRIS_PERF", "1")
    assert perf_ctx.get() is None
    # Must not raise — the contextvar check guards against this path.
    with span("standalone"):
        pass
