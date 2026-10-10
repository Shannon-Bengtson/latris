"""Tests for compose operations — node suggestions, correlations, apply selections."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import compose as compose_ops
from latris.operations import datasets as ds_ops
from latris.operations.init import init_project
from latris.repo.yaml_io import load_model
from latris.schema import Substrate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="What drives water quality?")
    return root


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    p = tmp_path / "water.csv"
    p.write_text(
        "rainfall,temperature,water_quality,sediment_load\n"
        "120.5,22.3,85.0,15.2\n"
        "95.0,24.1,78.0,18.5\n"
        "140.2,20.8,92.0,12.1\n"
        "80.0,26.0,65.0,22.3\n"
        "110.0,23.5,80.0,16.8\n",
        encoding="utf-8",
        newline="",
    )
    return p


# ---------------------------------------------------------------------------
# suggest_nodes_from_data
# ---------------------------------------------------------------------------


class TestSuggestNodesFromData:
    def test_empty_project_returns_empty(self, project: Path):
        result = compose_ops.suggest_nodes_from_data(root=project)
        assert result == []

    def test_returns_columns_as_suggestions(self, project: Path, sample_csv: Path):
        ds_ops.upload_dataset(sample_csv, name="Water Data", root=project)
        suggestions = compose_ops.suggest_nodes_from_data(root=project)

        labels = [s["label"] for s in suggestions]
        assert "rainfall" in labels
        assert "temperature" in labels
        assert "water_quality" in labels
        assert "sediment_load" in labels

    def test_suggestion_structure(self, project: Path, sample_csv: Path):
        ds_ops.upload_dataset(sample_csv, name="Water Data", root=project)
        suggestions = compose_ops.suggest_nodes_from_data(root=project)

        s = next(s for s in suggestions if s["label"] == "rainfall")
        assert s["source"] == "data"
        assert s["kind"] == "variable"  # numeric column → variable
        assert "Water Data" in s["sourceDetail"]
        assert s["stats"] is not None
        assert s["stats"]["dtype"] == "float64"

    def test_excludes_existing_entities(self, project: Path, sample_csv: Path):
        ds_ops.upload_dataset(sample_csv, name="Water Data", root=project)

        # Add 'rainfall' as an existing entity.
        from latris.operations.nodes import add_node

        add_node("rainfall", root=project)

        suggestions = compose_ops.suggest_nodes_from_data(root=project)
        labels = [s["label"] for s in suggestions]
        assert "rainfall" not in labels
        assert "temperature" in labels

    def test_excludes_index_and_id_columns(self, project: Path, tmp_path: Path):
        csv_path = tmp_path / "indexed.csv"
        csv_path.write_text(
            "idx,value\n1,10\n2,20\n",
            encoding="utf-8",
            newline="",
        )
        dataset, _sha = ds_ops.upload_dataset(csv_path, name="Indexed", root=project)
        # Mark the idx column as an index.
        ds_ops.update_column_metadata(dataset.id, "idx", role="index", root=project)

        suggestions = compose_ops.suggest_nodes_from_data(root=project)
        labels = [s["label"] for s in suggestions]
        assert "idx" not in labels
        assert "value" in labels


# ---------------------------------------------------------------------------
# apply_compose_selections
# ---------------------------------------------------------------------------


class TestApplyComposeSelections:
    def test_creates_nodes_and_edges(self, project: Path):
        ids, sha, _remapped = compose_ops.apply_compose_selections(
            nodes=[
                {"label": "Rainfall", "kind": "variable"},
                {"label": "Water Quality", "kind": "variable"},
            ],
            edges=[
                {"from_label": "Rainfall", "to_label": "Water Quality", "kind": "causal"},
            ],
            root=project,
        )
        assert len(ids) == 3  # 2 nodes + 1 edge
        assert sha

        # Verify substrate.
        from latris.repo.project import require_project

        paths = require_project(project)
        substrate = load_model(Substrate, paths.conceptual_yaml)
        labels = {e.label for e in substrate.entities}
        assert "Rainfall" in labels
        assert "Water Quality" in labels
        assert len(substrate.edges) == 1
        assert substrate.edges[0].kind == "causal"

    def test_coerces_non_substrate_kind(self, project: Path):
        """A non-substrate kind (e.g. a CLD role) is coerced, not rejected."""
        from latris.repo.project import require_project

        ids, sha, remapped = compose_ops.apply_compose_selections(
            nodes=[
                {"label": "Nitrogen Inputs", "kind": "driver"},
                {"label": "Algae Bloom", "kind": "wibble"},  # unknown → concept
                {"label": "Rainfall", "kind": "variable"},  # already valid
            ],
            edges=[
                {"from_label": "Nitrogen Inputs", "to_label": "Algae Bloom", "kind": "drives"},
            ],
            root=project,
        )
        assert len(ids) == 4  # 3 nodes + 1 edge, no hard fail
        assert sha

        paths = require_project(project)
        substrate = load_model(Substrate, paths.conceptual_yaml)
        by_label = {e.label: e.kind for e in substrate.entities}
        assert by_label["Nitrogen Inputs"] == "variable"  # driver → variable
        assert by_label["Algae Bloom"] == "concept"  # unknown → concept
        assert by_label["Rainfall"] == "variable"  # unchanged
        assert substrate.edges[0].kind == "causal"  # unknown edge kind → causal

        # Only the three coerced items are reported; the valid one is not.
        remapped_labels = {r["label"] for r in remapped}
        assert "Nitrogen Inputs" in remapped_labels
        assert "Algae Bloom" in remapped_labels
        assert "Rainfall" not in remapped_labels
        driver_remap = next(r for r in remapped if r["label"] == "Nitrogen Inputs")
        assert driver_remap["from"] == "driver"
        assert driver_remap["to"] == "variable"

    def test_single_commit(self, project: Path):
        from latris.repo import git as git_mod

        sha_before = git_mod.head_sha(project)
        compose_ops.apply_compose_selections(
            nodes=[
                {"label": "A"},
                {"label": "B"},
                {"label": "C"},
            ],
            edges=[
                {"from_label": "A", "to_label": "B"},
                {"from_label": "B", "to_label": "C"},
            ],
            root=project,
        )
        # Should be exactly one new commit (batch).
        log = git_mod.run_git(["log", "--oneline", f"{sha_before}..HEAD"], cwd=project).stdout.strip()
        lines = [line for line in log.splitlines() if line.strip()]
        assert len(lines) == 1
        assert "Compose:" in lines[0]

    def test_empty_apply_no_commit(self, project: Path):
        from latris.repo import git as git_mod

        sha_before = git_mod.head_sha(project)
        ids, sha, _remapped = compose_ops.apply_compose_selections(
            nodes=[],
            edges=[],
            root=project,
        )
        assert ids == []
        # No new commit since nothing was added.
        assert git_mod.head_sha(project) == sha_before

    def test_apply_creates_data_links_for_data_sourced_nodes(self, project: Path):
        """Data-sourced nodes should create DataLink records."""
        from latris.repo.project import require_project
        from latris.repo.yaml_io import load_model
        from latris.schema import DataLinkSet

        compose_ops.apply_compose_selections(
            nodes=[
                {
                    "label": "Rainfall",
                    "kind": "variable",
                    "origin": "data-derived",
                    "source_detail": "Dataset: Weather",
                    "description": "Monthly rainfall in mm.",
                    "dataset_id": "dataset_01ABC",
                    "column_name": "rainfall",
                }
            ],
            edges=[],
            root=project,
        )

        paths = require_project(project)
        assert paths.data_links_yaml.exists()
        links = load_model(DataLinkSet, paths.data_links_yaml)
        assert len(links.entries) == 1
        link = links.entries[0]
        assert link.dataset_id == "dataset_01ABC"
        assert link.column_names == ["rainfall"]
        assert link.statistic == "column-mapping"
        assert link.target_id is not None  # should be the created entity ID

    def test_apply_creates_data_links_for_correlation_edges(self, project: Path):
        """Correlation-sourced edges should create DataLink records."""
        from latris.repo.project import require_project
        from latris.repo.yaml_io import load_model
        from latris.schema import DataLinkSet

        compose_ops.apply_compose_selections(
            nodes=[
                {"label": "A", "kind": "variable"},
                {"label": "B", "kind": "variable"},
            ],
            edges=[
                {
                    "from_label": "A",
                    "to_label": "B",
                    "kind": "association",
                    "origin": "data-derived",
                    "source_detail": "Corr r=0.85",
                    "description": "Pearson r=+0.85 between A and B in Weather.",
                    "dataset_id": "dataset_01XYZ",
                    "from_column": "col_a",
                    "to_column": "col_b",
                    "statistic": "pearson",
                    "stat_value": "r=+0.8500, p=0.000100",
                }
            ],
            root=project,
        )

        paths = require_project(project)
        links = load_model(DataLinkSet, paths.data_links_yaml)
        assert len(links.entries) == 1
        link = links.entries[0]
        assert link.dataset_id == "dataset_01XYZ"
        assert link.column_names == ["col_a", "col_b"]
        assert link.statistic == "pearson"
        assert link.value == "r=+0.8500, p=0.000100"

    def test_no_data_links_for_manual_nodes(self, project: Path):
        """Manual nodes should NOT create DataLink records."""
        from latris.repo.project import require_project

        compose_ops.apply_compose_selections(
            nodes=[{"label": "Manual Node", "kind": "concept", "origin": "human-direct"}],
            edges=[],
            root=project,
        )

        paths = require_project(project)
        assert not paths.data_links_yaml.exists()


# ---------------------------------------------------------------------------
# Descriptions
# ---------------------------------------------------------------------------


class TestApplyDescriptions:
    def test_persists_node_description(self, project: Path):
        """A non-empty description on a manual node should land in descriptions.yaml."""
        from latris.repo.project import require_project
        from latris.schema import DescriptionSet

        compose_ops.apply_compose_selections(
            nodes=[
                {
                    "label": "Rainfall",
                    "kind": "variable",
                    "origin": "human-direct",
                    "description": "Monthly rainfall in mm.",
                }
            ],
            edges=[],
            root=project,
        )

        paths = require_project(project)
        assert paths.descriptions_yaml.exists()
        descriptions = load_model(DescriptionSet, paths.descriptions_yaml)
        values = {d.value for d in descriptions.entries}
        assert "Monthly rainfall in mm." in values

    def test_persists_edge_description(self, project: Path):
        from latris.repo.project import require_project
        from latris.schema import DescriptionSet

        compose_ops.apply_compose_selections(
            nodes=[
                {"label": "A", "kind": "variable"},
                {"label": "B", "kind": "variable"},
            ],
            edges=[
                {
                    "from_label": "A",
                    "to_label": "B",
                    "kind": "causal",
                    "origin": "human-direct",
                    "description": "A drives B via mechanism X.",
                }
            ],
            root=project,
        )

        paths = require_project(project)
        descriptions = load_model(DescriptionSet, paths.descriptions_yaml)
        values = {d.value for d in descriptions.entries}
        assert "A drives B via mechanism X." in values

    def test_rejects_ai_node_without_description(self, project: Path):
        from latris.repo import git as git_mod

        sha_before = git_mod.head_sha(project)
        with pytest.raises(ValueError, match="description required"):
            compose_ops.apply_compose_selections(
                nodes=[
                    {
                        "label": "Mystery",
                        "kind": "variable",
                        "origin": "ai-proposed",
                        "description": "",
                    }
                ],
                edges=[],
                root=project,
            )
        # No partial commit.
        assert git_mod.head_sha(project) == sha_before

    def test_rejects_data_edge_without_description(self, project: Path):
        from latris.repo import git as git_mod

        sha_before = git_mod.head_sha(project)
        with pytest.raises(ValueError, match="description required"):
            compose_ops.apply_compose_selections(
                nodes=[
                    {"label": "A", "kind": "variable"},
                    {"label": "B", "kind": "variable"},
                ],
                edges=[
                    {
                        "from_label": "A",
                        "to_label": "B",
                        "kind": "association",
                        "origin": "data-derived",
                        "description": "   ",  # whitespace only
                    }
                ],
                root=project,
            )
        assert git_mod.head_sha(project) == sha_before

    def test_allows_empty_manual_description(self, project: Path):
        """Manual entries may apply with an empty description and skip the entry."""
        from latris.repo.project import require_project
        from latris.schema import DescriptionSet

        compose_ops.apply_compose_selections(
            nodes=[
                {
                    "label": "Concept",
                    "kind": "concept",
                    "origin": "human-direct",
                    "description": "",
                }
            ],
            edges=[],
            root=project,
        )

        paths = require_project(project)
        if paths.descriptions_yaml.exists():
            descriptions = load_model(DescriptionSet, paths.descriptions_yaml)
            assert all(d.value != "" for d in descriptions.entries)


# ---------------------------------------------------------------------------
# suggest_edges_from_correlations description field
# ---------------------------------------------------------------------------


class TestSuggestEdgesDescription:
    def test_correlation_suggestion_includes_description(self, project: Path):
        # Reuse the correlated_csv fixture inline to avoid plumbing.
        import pandas as pd

        csv_path = project.parent / "corr.csv"
        pd.DataFrame(
            {"a": [1, 2, 3, 4, 5, 6, 7, 8], "b": [2, 4, 6, 8, 10, 12, 14, 16]}
        ).to_csv(csv_path, index=False)

        ds_ops.upload_dataset(csv_path, name="Corr", root=project)
        suggestions = compose_ops.suggest_edges_from_correlations(
            node_labels=["a", "b"], threshold=0.9, root=project
        )
        assert suggestions
        s = suggestions[0]
        assert "description" in s
        assert s["description"]
        assert "Corr" in s["description"]


# ---------------------------------------------------------------------------
# suggest_edges_from_correlations
# ---------------------------------------------------------------------------


@pytest.fixture
def correlated_csv(tmp_path: Path) -> Path:
    """CSV with strongly correlated columns."""
    p = tmp_path / "correlated.csv"
    # rainfall and water_quality are strongly correlated;
    # noise is random-ish.
    p.write_text(
        "rainfall,water_quality,noise\n10,20,5\n20,40,3\n30,60,8\n40,80,1\n50,100,9\n60,120,4\n70,140,7\n80,160,2\n",
        encoding="utf-8",
        newline="",
    )
    return p


class TestSuggestEdgesFromCorrelations:
    def test_no_data_returns_empty(self, project: Path):
        result = compose_ops.suggest_edges_from_correlations(
            node_labels=["A", "B"],
            root=project,
        )
        assert result == []

    def test_finds_correlated_pairs(self, project: Path, correlated_csv: Path):
        ds_ops.upload_dataset(correlated_csv, name="Correlated", root=project)
        suggestions = compose_ops.suggest_edges_from_correlations(
            node_labels=["rainfall", "water_quality", "noise"],
            threshold=0.9,
            root=project,
        )
        # rainfall vs water_quality has r=1.0 (perfect linear).
        assert len(suggestions) >= 1
        pair = suggestions[0]
        assert pair["source"] == "data"
        assert pair["kind"] == "association"
        assert abs(pair["coefficient"]) >= 0.9
        assert pair["pValue"] is not None
        labels = {pair["fromLabel"], pair["toLabel"]}
        assert labels == {"rainfall", "water_quality"}

    def test_threshold_filters_weak_correlations(self, project: Path, correlated_csv: Path):
        ds_ops.upload_dataset(correlated_csv, name="Correlated", root=project)
        # With threshold=0.999, only perfect correlations survive.
        suggestions = compose_ops.suggest_edges_from_correlations(
            node_labels=["rainfall", "water_quality", "noise"],
            threshold=0.999,
            root=project,
        )
        # Only rainfall-water_quality should survive (r=1.0).
        for s in suggestions:
            assert abs(s["coefficient"]) >= 0.999

    def test_ignores_non_matching_labels(self, project: Path, correlated_csv: Path):
        ds_ops.upload_dataset(correlated_csv, name="Correlated", root=project)
        suggestions = compose_ops.suggest_edges_from_correlations(
            node_labels=["unknown_a", "unknown_b"],
            root=project,
        )
        assert suggestions == []


# ---------------------------------------------------------------------------
# compute_correlations (data engine)
# ---------------------------------------------------------------------------


class TestComputeCorrelations:
    def test_basic_correlation(self):
        import pandas as pd

        from latris.operations._data_engine import compute_correlations

        df = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [2, 4, 6, 8, 10]})
        result = compute_correlations(df, threshold=0.5)
        assert len(result) == 1
        assert result[0]["col_a"] == "x"
        assert result[0]["col_b"] == "y"
        assert abs(result[0]["coefficient"] - 1.0) < 0.001

    def test_threshold_filters(self):
        import pandas as pd

        from latris.operations._data_engine import compute_correlations

        df = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [5, 3, 4, 2, 1], "z": [1, 1, 1, 1, 1]})
        result = compute_correlations(df, threshold=0.8)
        # x-y are negatively correlated (r ~ -0.9), should appear.
        # z is constant, no valid correlation.
        assert len(result) >= 1
        assert all(abs(r["coefficient"]) >= 0.8 for r in result)

    def test_spearman_method(self):
        import pandas as pd

        from latris.operations._data_engine import compute_correlations

        df = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [2, 4, 6, 8, 10]})
        result = compute_correlations(df, method="spearman", threshold=0.5)
        assert len(result) == 1
        assert result[0]["method"] == "spearman"

    def test_fewer_than_two_numeric_columns(self):
        import pandas as pd

        from latris.operations._data_engine import compute_correlations

        df = pd.DataFrame({"name": ["a", "b", "c"], "x": [1, 2, 3]})
        result = compute_correlations(df, threshold=0.0)
        assert result == []


# ---------------------------------------------------------------------------
# DataLink schema
# ---------------------------------------------------------------------------


class TestDataLinkSchema:
    def test_round_trip(self, tmp_path: Path):
        from latris.repo.yaml_io import dump_model, load_model
        from latris.schema import DataLink, DataLinkSet

        link = DataLink(
            target_id="node_01ABC",
            attribute="existence",
            dataset_id="dataset_01XYZ",
            column_names=["rainfall", "temperature"],
            statistic="correlation",
            value="r=0.72, p<0.01",
            rationale="Strong positive correlation",
        )
        link_set = DataLinkSet(entries=[link])

        path = tmp_path / "data-links.yaml"
        dump_model(link_set, path)
        loaded = load_model(DataLinkSet, path)

        assert len(loaded.entries) == 1
        loaded_link = loaded.entries[0]
        assert loaded_link.target_id == "node_01ABC"
        assert loaded_link.dataset_id == "dataset_01XYZ"
        assert loaded_link.column_names == ["rainfall", "temperature"]
        assert loaded_link.statistic == "correlation"
        assert loaded_link.value == "r=0.72, p<0.01"
        assert loaded_link.origin == "data-derived"

    def test_default_values(self):
        from latris.schema import DataLink

        link = DataLink(dataset_id="ds_01")
        assert link.attribute == "existence"
        assert link.origin == "data-derived"
        assert link.verification == "unverified"
        assert link.column_names == []
        assert link.target_id is None
