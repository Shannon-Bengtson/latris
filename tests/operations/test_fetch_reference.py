"""Tests for fetch_reference_source — Phase 4b Tier-1 retrieval.

Hermetic via the http_get injection seam — tests pass a fake fetcher
so no network calls happen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import references as ref_ops
from latris.operations.init import init_project


class FakeResponse:
    """Stub of an httpx.Response — only the attributes the fetcher reads."""

    def __init__(
        self,
        text: str,
        *,
        content_type: str = "text/html",
        url: str = "https://example.org/p",
    ) -> None:
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"content-type": content_type}
        self.url = url

    def raise_for_status(self) -> None:
        return None


@pytest.fixture
def project(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    return root


def test_fetch_html_strips_tags_and_writes_artefact(project: Path) -> None:
    ref_ops.add_reference(
        "smith2023",
        title="X",
        url="https://example.org/p",
        root=project,
    )
    html = (
        "<html><body>"
        "<script>alert('x')</script>"
        "<h1>Pricing study</h1>"
        "<p>Vehicle emissions drive air quality decline.</p>"
        "</body></html>"
    )
    ref, sha = ref_ops.fetch_reference_source(
        "smith2023",
        http_get=lambda url, **_: FakeResponse(html),
        root=project,
    )

    snap = ref.source_snapshot
    assert snap is not None
    assert snap.kind == "full_text_excerpt"
    assert "Vehicle emissions drive air quality decline." in snap.extract
    assert "<script>" not in snap.extract  # tag stripping
    assert "alert" not in snap.extract  # script-block dropped
    assert snap.content_hash.startswith("sha256:")

    # Artefact written + gitignored path.
    from latris.repo.project import require_project

    paths = require_project(project)
    artefact = paths.references_extract_path("smith2023")
    assert artefact.exists()
    assert "Vehicle emissions" in artefact.read_text(encoding="utf-8")


def test_fetch_text_plain_uses_text_directly(project: Path) -> None:
    ref_ops.add_reference("plain1", title="X", url="https://e/x", root=project)
    text = "Plain text body. Vehicle emissions drive air quality decline."
    ref, _ = ref_ops.fetch_reference_source(
        "plain1",
        http_get=lambda url, **_: FakeResponse(text, content_type="text/plain"),
        root=project,
    )
    assert ref.source_snapshot is not None
    assert ref.source_snapshot.extract.startswith("Plain text body.")


def test_fetch_resolves_doi_when_no_url(project: Path) -> None:
    """No url; must resolve via DOI."""
    captured: list[str] = []

    def fake_get(url: str, **_):
        captured.append(url)
        return FakeResponse("<html><body>doi-body</body></html>")

    ref_ops.add_reference("doi1", title="X", doi="10.1000/xyz", root=project)
    ref_ops.fetch_reference_source(
        "doi1",
        http_get=fake_get,
        root=project,
    )
    assert captured[0] == "https://doi.org/10.1000/xyz"


def test_fetch_url_argument_overrides(project: Path) -> None:
    captured: list[str] = []

    def fake_get(url: str, **_):
        captured.append(url)
        return FakeResponse("body")

    ref_ops.add_reference("o1", title="X", url="https://default", root=project)
    ref_ops.fetch_reference_source(
        "o1",
        url="https://override",
        http_get=fake_get,
        root=project,
    )
    assert captured[0] == "https://override"


def test_fetch_without_url_or_doi_raises(project: Path) -> None:
    ref_ops.add_reference("no_url", title="X", root=project)
    with pytest.raises(ValueError, match="no `url` or `doi`"):
        ref_ops.fetch_reference_source(
            "no_url",
            http_get=lambda *_args, **_kw: FakeResponse("body"),
            root=project,
        )


def test_fetch_empty_extracted_text_raises(project: Path) -> None:
    """Empty body (likely paywall / login page) — refuse to write empty snapshot."""
    ref_ops.add_reference("empty1", title="X", url="https://e/x", root=project)
    with pytest.raises(ValueError, match="empty text"):
        ref_ops.fetch_reference_source(
            "empty1",
            http_get=lambda *_args, **_kw: FakeResponse("   "),
            root=project,
        )


def test_refetch_overwrites_snapshot(project: Path) -> None:
    """Refetches overwrite the snapshot. Git history is the audit trail."""
    ref_ops.add_reference("r1", title="X", url="https://e/x", root=project)
    ref_ops.fetch_reference_source(
        "r1",
        http_get=lambda *_a, **_k: FakeResponse("first body"),
        root=project,
    )
    ref, _ = ref_ops.fetch_reference_source(
        "r1",
        http_get=lambda *_a, **_k: FakeResponse("second body — different content"),
        root=project,
    )
    assert "second body" in ref.source_snapshot.extract
    assert "first body" not in ref.source_snapshot.extract
