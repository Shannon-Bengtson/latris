"""Tests for the expanded reference operations: get, update, remove, import_bibtex, id backfill."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from latris.operations import evidence as evidence_ops
from latris.operations import nodes as node_ops
from latris.operations import references as ref_ops
from latris.operations.init import init_project


@pytest.fixture
def project(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    return root


# ── ID generation ────────────────────────────────────────────────────


def test_reference_has_id(project) -> None:
    ref, _ = ref_ops.add_reference("smith2024", title="Test", root=project)
    assert ref.id.startswith("reference_")
    assert len(ref.id) > len("reference_")


def test_get_reference_by_bibkey(project) -> None:
    ref_ops.add_reference("smith2024", title="Test", root=project)
    ref = ref_ops.get_reference("smith2024", root=project)
    assert ref.bibkey == "smith2024"
    assert ref.title == "Test"


def test_get_reference_by_id(project) -> None:
    added, _ = ref_ops.add_reference("smith2024", title="Test", root=project)
    ref = ref_ops.get_reference(added.id, root=project)
    assert ref.bibkey == "smith2024"


def test_get_reference_not_found(project) -> None:
    with pytest.raises(ValueError, match="no reference"):
        ref_ops.get_reference("nonexistent", root=project)


# ── Update ──────────────────────────────────────────────────────────


def test_update_reference(project) -> None:
    ref_ops.add_reference("smith2024", title="Old title", root=project)
    updated, sha = ref_ops.update_reference(
        "smith2024",
        title="New title",
        year=2024,
        container="Nature",
        root=project,
    )
    assert updated.title == "New title"
    assert updated.year == 2024
    assert updated.container == "Nature"
    assert sha  # commit was made

    # Verify persistence.
    ref = ref_ops.get_reference("smith2024", root=project)
    assert ref.title == "New title"


def test_update_reference_not_found(project) -> None:
    with pytest.raises(ValueError, match="no reference"):
        ref_ops.update_reference("nonexistent", title="X", root=project)


# ── Remove ──────────────────────────────────────────────────────────


def test_remove_reference(project) -> None:
    ref_ops.add_reference("smith2024", title="Test", root=project)
    removed, sha = ref_ops.remove_reference("smith2024", root=project)
    assert removed.bibkey == "smith2024"
    assert sha

    # Verify it's gone.
    refs = ref_ops.list_references(project)
    assert len(refs) == 0


def test_remove_reference_with_evidence_raises(project) -> None:
    node, _ = node_ops.add_node("X", root=project)
    ref_ops.add_reference("smith2024", title="Test", root=project)
    evidence_ops.add_evidence(node.id, "description", "smith2024", root=project)

    with pytest.raises(ValueError, match="evidence link"):
        ref_ops.remove_reference("smith2024", root=project)


# ── BibTeX import ───────────────────────────────────────────────────

SAMPLE_BIBTEX = """\
@article{fowler2007,
  title={Linking climate change modelling to impacts studies},
  author={Fowler, H. and Blenkinsop, S. and Tebaldi, C.},
  year={2007},
  journal={International Journal of Climatology},
  doi={10.1002/joc.1556}
}

@book{ipcc2021,
  title={Climate Change 2021: The Physical Science Basis},
  author={IPCC},
  year={2021},
  publisher={Cambridge University Press}
}
"""


def test_import_bibtex_basic(project) -> None:
    refs, sha = ref_ops.import_bibtex(SAMPLE_BIBTEX, root=project)
    assert len(refs) == 2
    assert sha

    bibkeys = {r.bibkey for r in refs}
    assert "fowler2007" in bibkeys
    assert "ipcc2021" in bibkeys

    # Verify persistence.
    all_refs = ref_ops.list_references(project)
    assert len(all_refs) == 2

    # Check field mapping.
    fowler = next(r for r in all_refs if r.bibkey == "fowler2007")
    assert fowler.year == 2007
    assert "Fowler, H." in fowler.authors
    assert fowler.container == "International Journal of Climatology"
    assert fowler.doi == "10.1002/joc.1556"
    assert fowler.imported_from == "bibtex"


def test_import_bibtex_skips_duplicates(project) -> None:
    ref_ops.add_reference("fowler2007", title="Existing", root=project)
    refs, sha = ref_ops.import_bibtex(SAMPLE_BIBTEX, root=project)
    # Only ipcc2021 should be added (fowler2007 already exists).
    assert len(refs) == 1
    assert refs[0].bibkey == "ipcc2021"


def test_import_bibtex_empty(project) -> None:
    refs, sha = ref_ops.import_bibtex("", root=project)
    assert len(refs) == 0
    assert sha == ""


BIBTEX_WITH_ABSTRACT = """\
@article{jones2020,
  title={Water quality and rainfall},
  author={Jones, A. and Smith, B.},
  year={2020},
  journal={Environmental Science},
  abstract={This study examines the relationship between rainfall intensity and downstream water quality in coastal catchments.}
}
"""


def test_import_bibtex_extracts_abstract(project) -> None:
    refs, sha = ref_ops.import_bibtex(BIBTEX_WITH_ABSTRACT, root=project)
    assert len(refs) == 1
    assert refs[0].abstract is not None
    assert "rainfall intensity" in refs[0].abstract

    # Verify persistence round-trip.
    all_refs = ref_ops.list_references(project)
    jones = next(r for r in all_refs if r.bibkey == "jones2020")
    assert jones.abstract is not None
    assert "coastal catchments" in jones.abstract


def test_import_bibtex_no_abstract_yields_none(project) -> None:
    refs, sha = ref_ops.import_bibtex(SAMPLE_BIBTEX, root=project)
    assert len(refs) == 2
    # Neither entry has an abstract field.
    for r in refs:
        assert r.abstract is None


# ── Abstract field round-trip ──────────────────────────────────────


def test_abstract_field_round_trip(project) -> None:
    """Reference with abstract persists and round-trips through YAML."""
    ref, _sha = ref_ops.add_reference(
        "test2025",
        title="Test Abstract Round-Trip",
        root=project,
    )
    # Manually set abstract since add_reference doesn't expose it.
    from latris.repo.project import require_project
    from latris.repo.yaml_io import dump_model, load_model
    from latris.schema import ReferenceLibrary

    paths = require_project(project)
    library = load_model(ReferenceLibrary, paths.references_yaml)
    entry = next(r for r in library.entries if r.bibkey == "test2025")
    entry.abstract = "A test abstract for round-trip verification."
    dump_model(library, paths.references_yaml)

    # Reload and verify.
    library2 = load_model(ReferenceLibrary, paths.references_yaml)
    entry2 = next(r for r in library2.entries if r.bibkey == "test2025")
    assert entry2.abstract == "A test abstract for round-trip verification."


# ── OpenAlex abstract reconstruction ──────────────────────────────


def test_reconstruct_abstract() -> None:
    from latris.operations.references import _reconstruct_abstract

    inverted = {"This": [0], "is": [1], "a": [2], "test": [3], "abstract": [4]}
    assert _reconstruct_abstract(inverted) == "This is a test abstract"


def test_reconstruct_abstract_none() -> None:
    from latris.operations.references import _reconstruct_abstract

    assert _reconstruct_abstract(None) is None
    assert _reconstruct_abstract({}) is None


# ── ID backfill ─────────────────────────────────────────────────────


def test_id_backfill(project) -> None:
    """References written without id keys (legacy YAML) get stable IDs on load."""
    from latris.repo.project import require_project

    paths = require_project(project)

    # Write YAML without id keys — simulating a pre-ID-era reference file.
    paths.references_yaml.write_text(
        "entries:\n  - bibkey: smith2024\n    title: Test\n    authors: []\n",
        encoding="utf-8",
    )

    # First load should detect missing ids and persist them.
    refs = ref_ops.list_references(project)
    assert len(refs) == 1
    assert refs[0].id.startswith("reference_")
    assert len(refs[0].id) > len("reference_")

    # YAML should now contain the id key.
    yaml_text = paths.references_yaml.read_text(encoding="utf-8")
    assert "id:" in yaml_text


def test_id_backfill_ids_stable_across_loads(project) -> None:
    """Once backfilled, reference IDs remain identical on subsequent loads."""
    from latris.repo.project import require_project

    paths = require_project(project)

    # Write YAML without id keys.
    paths.references_yaml.write_text(
        "entries:\n"
        "  - bibkey: a2024\n"
        "    title: Alpha\n"
        "    authors: []\n"
        "  - bibkey: b2024\n"
        "    title: Beta\n"
        "    authors: []\n",
        encoding="utf-8",
    )

    # First load — triggers backfill.
    refs1 = ref_ops.list_references(project)
    ids1 = [r.id for r in refs1]

    # Second load — should return the same IDs (no new random IDs).
    refs2 = ref_ops.list_references(project)
    ids2 = [r.id for r in refs2]

    assert ids1 == ids2


def test_id_backfill_no_spurious_write(project) -> None:
    """After IDs are persisted, subsequent loads don't rewrite the file."""
    import os

    from latris.repo.project import require_project

    paths = require_project(project)

    # Write YAML without id keys and trigger backfill.
    paths.references_yaml.write_text(
        "entries:\n  - bibkey: smith2024\n    title: Test\n    authors: []\n",
        encoding="utf-8",
    )
    ref_ops.list_references(project)  # triggers backfill write

    mtime_after_backfill = os.path.getmtime(paths.references_yaml)

    # Second load should NOT write to the file.
    ref_ops.list_references(project)
    mtime_after_second_load = os.path.getmtime(paths.references_yaml)

    assert mtime_after_backfill == mtime_after_second_load


# ── Search (mocked) ────────────────────────────────────────────────


def test_search_references_mocked() -> None:
    """Test that search_references correctly maps OpenAlex results."""
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {
        "results": [
            {
                "title": "Climate modelling advances",
                "authorships": [
                    {"author": {"display_name": "Jane Smith"}},
                    {"author": {"display_name": "Bob Jones"}},
                ],
                "publication_year": 2023,
                "doi": "https://doi.org/10.1234/test",
                "primary_location": {
                    "source": {"display_name": "Nature Climate Change"},
                    "landing_page_url": "https://example.com/paper",
                },
            }
        ]
    }

    with patch("httpx.get", return_value=fake_resp):
        candidates = ref_ops.search_references("climate modelling", limit=1)

    assert len(candidates) == 1
    c = candidates[0]
    assert c.title == "Climate modelling advances"
    assert "Jane Smith" in c.authors
    assert c.year == 2023
    assert c.doi == "10.1234/test"
    assert c.url == "https://example.com/paper"
    assert c.imported_from == "openalex"


# ── DOI normalization ──────────────────────────────────────────────


def test_normalize_doi_bare() -> None:
    from latris.operations.references import _normalize_doi

    assert _normalize_doi("10.1002/joc.1556") == "10.1002/joc.1556"


def test_normalize_doi_https_url() -> None:
    from latris.operations.references import _normalize_doi

    assert _normalize_doi("https://doi.org/10.1002/joc.1556") == "10.1002/joc.1556"


def test_normalize_doi_dx_url() -> None:
    from latris.operations.references import _normalize_doi

    assert _normalize_doi("http://dx.doi.org/10.1002/joc.1556") == "10.1002/joc.1556"


def test_normalize_doi_prefix() -> None:
    from latris.operations.references import _normalize_doi

    assert _normalize_doi("doi:10.1002/joc.1556") == "10.1002/joc.1556"


def test_normalize_doi_invalid() -> None:
    from latris.operations.references import _normalize_doi

    with pytest.raises(ValueError, match="could not extract"):
        _normalize_doi("not-a-doi")


# ── DOI import (mocked) ───────────────────────────────────────────

_FAKE_OPENALEX_WORK = {
    "title": "Climate modelling advances",
    "authorships": [
        {"author": {"display_name": "Jane Smith"}},
    ],
    "publication_year": 2023,
    "doi": "https://doi.org/10.1234/test",
    "primary_location": {
        "source": {"display_name": "Nature Climate Change"},
        "landing_page_url": "https://example.com/paper",
    },
    "abstract_inverted_index": None,
}


def _mock_openalex_response(paper: dict | None = None) -> MagicMock:
    fake = MagicMock()
    fake.status_code = 200
    fake.raise_for_status = MagicMock()
    fake.json.return_value = paper or _FAKE_OPENALEX_WORK
    return fake


def test_import_doi_basic(project) -> None:
    with patch("httpx.get", return_value=_mock_openalex_response()):
        ref, sha = ref_ops.import_doi("10.1234/test", root=project)

    assert ref.bibkey == "smith2023"
    assert ref.doi == "10.1234/test"
    assert ref.imported_from == "doi"
    assert ref.title == "Climate modelling advances"
    assert sha

    # Verify persistence.
    all_refs = ref_ops.list_references(project)
    assert len(all_refs) == 1
    assert all_refs[0].doi == "10.1234/test"


def test_import_doi_duplicate_raises(project) -> None:
    ref_ops.add_reference("existing", title="X", doi="10.1234/test", root=project)
    with pytest.raises(ValueError, match="already exists"):
        ref_ops.import_doi("10.1234/test", root=project)


def test_import_doi_bibkey_collision(project) -> None:
    """When bibkey collides, a suffix is appended."""
    ref_ops.add_reference("smith2023", title="Existing", root=project)

    with patch("httpx.get", return_value=_mock_openalex_response()):
        ref, sha = ref_ops.import_doi("10.1234/test", root=project)

    assert ref.bibkey == "smith2023_2"


def test_import_doi_not_found(project) -> None:
    import httpx

    fake_resp = MagicMock(spec=httpx.Response)
    fake_resp.status_code = 404
    fake_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found",
        request=MagicMock(),
        response=fake_resp,
    )

    with patch("httpx.get", return_value=fake_resp), pytest.raises(ValueError, match="not found on OpenAlex"):
        ref_ops.import_doi("10.9999/nonexistent", root=project)


def test_import_doi_accepts_url_format(project) -> None:
    """Accepts https://doi.org/... format."""
    with patch("httpx.get", return_value=_mock_openalex_response()) as mock_get:
        ref, _ = ref_ops.import_doi("https://doi.org/10.1234/test", root=project)

    assert ref.doi == "10.1234/test"
    # Verify the URL passed to httpx includes the normalized DOI.
    call_url = mock_get.call_args[0][0]
    assert "10.1234/test" in call_url


# ── Source access + snapshot (AI interrogation Phase 2a) ─────────────


def test_compute_source_access_no_abstract_no_snapshot(project) -> None:
    ref, _ = ref_ops.add_reference("smith2024", title="Test", root=project)
    assert ref_ops.compute_source_access(ref) == "title_only"


def test_compute_source_access_with_abstract(project) -> None:
    from latris.repo.yaml_io import dump_model, load_model
    from latris.schema import ReferenceLibrary

    ref_ops.add_reference("smith2024", title="Test", root=project)
    lib_path = ref_ops.load_library.__wrapped__ if False else None  # noqa
    # Mutate abstract directly via load/dump (no public setter today).
    from latris.repo.layout import ProjectPaths

    lib_path = ProjectPaths(project).references_yaml
    lib = load_model(ReferenceLibrary, lib_path)
    lib.entries[0].abstract = "Captured abstract."
    dump_model(lib, lib_path)

    ref = ref_ops.get_reference("smith2024", root=project)
    assert ref_ops.compute_source_access(ref) == "abstract"


def test_compute_source_access_landing_page_does_not_grant_abstract(project) -> None:
    ref_ops.add_reference("smith2024", title="Test", root=project)
    ref_ops.set_source_snapshot(
        "smith2024",
        retrieval_url="https://example.org/smith2024",
        extract="Generic publisher landing copy.",
        kind="landing_page_text",
        root=project,
    )
    ref = ref_ops.get_reference("smith2024", root=project)
    # landing_page_text snapshots must NOT confer abstract-level access.
    assert ref_ops.compute_source_access(ref) == "title_only"


def test_compute_source_access_abstract_snapshot_grants_abstract(project) -> None:
    ref_ops.add_reference("smith2024", title="Test", root=project)
    ref_ops.set_source_snapshot(
        "smith2024",
        retrieval_url="https://example.org/smith2024",
        extract="Real abstract content.",
        kind="abstract",
        root=project,
    )
    ref = ref_ops.get_reference("smith2024", root=project)
    assert ref_ops.compute_source_access(ref) == "abstract"


def test_compute_source_access_full_text_excerpt_grants_abstract(project) -> None:
    ref_ops.add_reference("smith2024", title="Test", root=project)
    ref_ops.set_source_snapshot(
        "smith2024",
        retrieval_url="https://example.org/smith2024",
        extract="Excerpt of full text.",
        kind="full_text_excerpt",
        root=project,
    )
    ref = ref_ops.get_reference("smith2024", root=project)
    # Phase 2 treats `full_text_excerpt` as ≥ abstract for source-access
    # purposes; Phase 4 will further promote to `full_text_chunk` after
    # apply()-time quote validation.
    assert ref_ops.compute_source_access(ref) == "abstract"


def test_set_source_snapshot_persists_and_hashes(project) -> None:
    ref_ops.add_reference("smith2024", title="Test", root=project)
    ref, sha = ref_ops.set_source_snapshot(
        "smith2024",
        retrieval_url="https://example.org/smith2024",
        extract="Extract text.",
        kind="abstract",
        root=project,
    )
    assert sha
    assert ref.source_snapshot is not None
    assert ref.source_snapshot.retrieval_url == "https://example.org/smith2024"
    assert ref.source_snapshot.kind == "abstract"
    assert ref.source_snapshot.content_hash.startswith("sha256:")
    # Verify deterministic hashing.
    import hashlib

    expected = "sha256:" + hashlib.sha256(b"Extract text.").hexdigest()
    assert ref.source_snapshot.content_hash == expected

    # Persistence round-trip.
    fetched = ref_ops.get_reference("smith2024", root=project)
    assert fetched.source_snapshot is not None
    assert fetched.source_snapshot.content_hash == expected


def test_add_evidence_infers_source_access_from_abstract(project) -> None:
    """add_evidence must promote source_access=abstract when the ref qualifies."""
    from latris.repo.layout import ProjectPaths
    from latris.repo.yaml_io import dump_model, load_model
    from latris.schema import ReferenceLibrary

    node, _ = node_ops.add_node("X", root=project)
    ref_ops.add_reference("smith2024", title="Test", root=project)

    lib_path = ProjectPaths(project).references_yaml
    lib = load_model(ReferenceLibrary, lib_path)
    lib.entries[0].abstract = "Captured abstract."
    dump_model(lib, lib_path)

    link, _ = evidence_ops.add_evidence(node.id, "description", "smith2024", root=project)
    assert link.source_access == "abstract"


def test_add_evidence_keeps_title_only_when_only_landing_snapshot(project) -> None:
    node, _ = node_ops.add_node("X", root=project)
    ref_ops.add_reference("smith2024", title="Test", root=project)
    ref_ops.set_source_snapshot(
        "smith2024",
        retrieval_url="https://example.org/smith2024",
        extract="Generic landing copy.",
        kind="landing_page_text",
        root=project,
    )
    link, _ = evidence_ops.add_evidence(node.id, "description", "smith2024", root=project)
    assert link.source_access == "title_only"
