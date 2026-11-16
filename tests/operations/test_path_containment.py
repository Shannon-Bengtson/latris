"""User-supplied names must never place files outside their directory.

Regressions for path traversal through dataset names, bibkeys, and a
crafted ``dataset.location`` pushed by a collaborator.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import datasets as ds_ops
from latris.operations import references as ref_ops
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths, contained_path, safe_filename_stem
from latris.repo.yaml_io import dump_model, load_model
from latris.schema.datasets import DatasetLibrary
from latris.schema.references import Reference, ReferenceLibrary, validate_bibkey


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.content = text.encode()
        self.headers = {"content-type": "text/plain"}
        self.url = "https://example.org/p"

    def raise_for_status(self) -> None:
        return None


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    return root


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    p = tmp_path / "sample.csv"
    p.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    return p


# ── helpers ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["smith2023", "Smith_2023a", "a.b-c+d"])
def test_safe_filename_stem_keeps_ordinary_names(name: str) -> None:
    assert safe_filename_stem(name) == name


@pytest.mark.parametrize("name", ["../x", "a/b", "a\\b", "..", ".hidden", "smith:2023", "a b", "x" * 300, ""])
def test_safe_filename_stem_hashes_unsafe_names(name: str) -> None:
    stem = safe_filename_stem(name)
    assert stem.startswith("_key-")
    assert "/" not in stem and "\\" not in stem and ".." not in stem


def test_contained_path(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    assert contained_path(base, base / "f.txt") == base / "f.txt"
    with pytest.raises(ValueError):
        contained_path(base, base / ".." / "f.txt")


# ── bibkeys ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("key", ["../../evil", "a/b", "a\\b", "..", ".x", "-x", "a b", "a\nb", "", "k" * 201])
def test_validate_bibkey_rejects_unsafe(key: str) -> None:
    with pytest.raises(ValueError):
        validate_bibkey(key)


@pytest.mark.parametrize("key", ["smith2023", "smith:2023", "O'Brien2020", "müller2021", "a_b-c.d"])
def test_validate_bibkey_accepts_normal_keys(key: str) -> None:
    assert validate_bibkey(key) == key


def test_add_reference_rejects_traversal_key(project: Path) -> None:
    with pytest.raises(ValueError):
        ref_ops.add_reference("../../../../tmp/evil", title="X", url="https://e.org", root=project)


def test_bibtex_import_skips_traversal_key(project: Path) -> None:
    bib = "@article{../../evil, title={Bad}}\n@article{good2020, title={Good}}\n"
    added, _ = ref_ops.import_bibtex(bib, root=project)
    assert [r.bibkey for r in added] == ["good2020"]


def test_fetch_with_legacy_unsafe_bibkey_stays_inside_extracts_dir(project: Path, tmp_path: Path) -> None:
    # A key that predates validation (or was pushed by a collaborator).
    paths = ProjectPaths(project)
    library = load_model(ReferenceLibrary, paths.references_yaml)
    library.entries.append(Reference(bibkey="../../../../outside", title="X", url="https://example.org/p"))
    dump_model(library, paths.references_yaml)

    ref_ops.fetch_reference_source(
        "../../../../outside",
        http_get=lambda url, **_: FakeResponse("full text"),
        root=project,
    )
    artefact = paths.references_extract_path("../../../../outside")
    assert artefact.read_text(encoding="utf-8") == "full text"
    assert paths.references_extracts_dir.resolve() in artefact.resolve().parents
    assert not (tmp_path / "outside.txt").exists()


# ── datasets ─────────────────────────────────────────────────────────


def test_upload_traversal_name_stays_in_data_files(project: Path, sample_csv: Path, tmp_path: Path) -> None:
    dataset, _ = ds_ops.upload_dataset(sample_csv, name="../../../escaped", root=project)
    paths = ProjectPaths(project)
    stored = project / dataset.location
    assert stored.exists()
    assert paths.data_files_dir.resolve() in stored.resolve().parents
    assert dataset.name == "../../../escaped"  # display name kept as typed
    assert not (tmp_path / "escaped.csv").exists()


def test_upload_rejects_blank_name(project: Path, sample_csv: Path) -> None:
    with pytest.raises(ValueError):
        ds_ops.upload_dataset(sample_csv, name="   ", root=project)


def test_crafted_location_is_refused(project: Path, sample_csv: Path) -> None:
    dataset, _ = ds_ops.upload_dataset(sample_csv, name="good", root=project)
    paths = ProjectPaths(project)
    library = load_model(DatasetLibrary, paths.data_datasets_yaml)
    library.entries[0].location = ".git/hooks/pre-commit"
    dump_model(library, paths.data_datasets_yaml)

    with pytest.raises(ValueError, match="escapes"):
        ds_ops.apply_operation(dataset.id, "round_values", {"column": "a", "decimals": 0}, root=project)
    assert not (project / ".git" / "hooks" / "pre-commit").exists()
