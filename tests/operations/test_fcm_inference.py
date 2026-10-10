"""Tests for FCM inference engine."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from latris.operations.fcm_inference import fcm_infer
from latris.schema.settings import FCMSettings


@dataclass
class E:
    """Minimal edge for testing."""

    id: str
    from_id: str
    to_id: str


class TestFCMInference:
    def test_empty_graph(self):
        result = fcm_infer([], {}, [])
        assert result.converged is True
        assert result.iterations == 0
        assert result.activations == {}

    def test_single_node_no_edges(self):
        result = fcm_infer([], {}, ["a"])
        assert result.converged is True
        assert "a" in result.activations
        assert result.activations["a"] == pytest.approx(0.5, abs=0.01)

    def test_single_positive_edge(self):
        """a → b with weight 0.8: b should activate higher than default."""
        edges = [E("e1", "a", "b")]
        weights = {"e1": 0.8}
        result = fcm_infer(edges, weights, ["a", "b"])
        assert result.converged is True
        # b receives positive influence from a (default 0.5), so b > 0.5
        assert result.activations["b"] > 0.5

    def test_single_negative_edge(self):
        """a → b with weight -0.8: b should deactivate below default."""
        edges = [E("e1", "a", "b")]
        weights = {"e1": -0.8}
        result = fcm_infer(edges, weights, ["a", "b"])
        assert result.converged is True
        # b receives negative influence, so b < 0.5
        assert result.activations["b"] < 0.5

    def test_triangle_converges(self):
        """Triangle with all positive weights should converge."""
        edges = [E("e1", "a", "b"), E("e2", "b", "c"), E("e3", "c", "a")]
        weights = {"e1": 0.5, "e2": 0.5, "e3": 0.5}
        result = fcm_infer(edges, weights, ["a", "b", "c"])
        assert result.converged is True
        # All should settle above 0.5 (mutual reinforcement)
        for val in result.activations.values():
            assert val > 0.5

    def test_clamped_node(self):
        """Clamping a → 1.0 forces it high; b should respond."""
        edges = [E("e1", "a", "b")]
        weights = {"e1": 0.9}
        result = fcm_infer(
            edges,
            weights,
            ["a", "b"],
            clamped={"a": 1.0},
        )
        assert result.converged is True
        assert result.activations["a"] == pytest.approx(1.0)
        # b should be significantly activated
        assert result.activations["b"] > 0.6

    def test_clamped_node_zero(self):
        """Clamping a → 0.0 forces it low; b should respond."""
        edges = [E("e1", "a", "b")]
        weights = {"e1": 0.9}
        result = fcm_infer(
            edges,
            weights,
            ["a", "b"],
            clamped={"a": 0.0},
        )
        assert result.activations["a"] == pytest.approx(0.0)
        # b receives near-zero influence → settles near sigmoid(0) = 0.5
        assert result.activations["b"] == pytest.approx(0.5, abs=0.05)

    def test_initial_activations(self):
        """Custom initial activations should be used."""
        result = fcm_infer([], {}, ["a", "b"], initial_activations={"a": 0.9, "b": 0.1})
        assert result.converged is True
        assert result.history[0]["a"] == pytest.approx(0.9)
        assert result.history[0]["b"] == pytest.approx(0.1)

    def test_history_recorded(self):
        """History should include initial state + iteration states."""
        edges = [E("e1", "a", "b")]
        weights = {"e1": 0.5}
        result = fcm_infer(edges, weights, ["a", "b"])
        assert len(result.history) >= 2  # at least initial + 1 iteration
        assert "a" in result.history[0]
        assert "b" in result.history[0]

    def test_max_iterations_reached(self):
        """With max_iterations=1, should stop after one iteration."""
        edges = [E("e1", "a", "b"), E("e2", "b", "a")]
        weights = {"e1": 0.9, "e2": 0.9}
        settings = FCMSettings(max_iterations=1, convergence_threshold=0.0001)
        result = fcm_infer(edges, weights, ["a", "b"], settings=settings)
        assert result.iterations == 1
        # May or may not have converged in 1 iteration

    def test_non_convergence_detected(self):
        """With very strict threshold and few iterations, non-convergence flagged."""
        edges = [E("e1", "a", "b"), E("e2", "b", "a")]
        weights = {"e1": 0.99, "e2": -0.99}
        settings = FCMSettings(
            max_iterations=3,
            convergence_threshold=1e-10,
            lambda_steepness=5.0,
        )
        result = fcm_infer(edges, weights, ["a", "b"], settings=settings)
        assert result.iterations == 3
        assert result.converged is False

    def test_tanh_transfer_function(self):
        edges = [E("e1", "a", "b")]
        weights = {"e1": 0.8}
        settings = FCMSettings(transfer_function="tanh")
        result = fcm_infer(edges, weights, ["a", "b"], settings=settings)
        assert result.converged is True
        assert 0.0 <= result.activations["b"] <= 1.0

    def test_step_transfer_function(self):
        edges = [E("e1", "a", "b")]
        weights = {"e1": 0.8}
        settings = FCMSettings(transfer_function="step")
        result = fcm_infer(edges, weights, ["a", "b"], settings=settings)
        assert result.converged is True
        # Step function outputs 0 or 1
        assert result.activations["b"] in (0.0, 1.0)

    def test_lambda_steepness_affects_result(self):
        """Higher lambda → more extreme activations."""
        edges = [E("e1", "a", "b")]
        weights = {"e1": 0.8}
        result_low = fcm_infer(edges, weights, ["a", "b"], settings=FCMSettings(lambda_steepness=0.5))
        result_high = fcm_infer(edges, weights, ["a", "b"], settings=FCMSettings(lambda_steepness=5.0))
        # Higher lambda should push b further from 0.5
        assert abs(result_high.activations["b"] - 0.5) > abs(result_low.activations["b"] - 0.5)

    def test_missing_weight_edge_ignored(self):
        """Edges without weights in the weights dict are treated as zero weight."""
        edges = [E("e1", "a", "b"), E("e2", "b", "c")]
        weights = {"e1": 0.8}  # e2 missing
        result = fcm_infer(edges, weights, ["a", "b", "c"])
        assert result.converged is True
        # c should not be influenced by b (missing weight = 0)
        assert result.activations["c"] == pytest.approx(0.5, abs=0.05)

    def test_activations_in_valid_range(self):
        """All activations should be in [0, 1] regardless of inputs."""
        edges = [
            E("e1", "a", "b"),
            E("e2", "b", "c"),
            E("e3", "c", "a"),
            E("e4", "a", "c"),
        ]
        weights = {"e1": 1.0, "e2": -1.0, "e3": 0.5, "e4": -0.5}
        result = fcm_infer(edges, weights, ["a", "b", "c"], settings=FCMSettings(lambda_steepness=10.0))
        for val in result.activations.values():
            assert 0.0 <= val <= 1.0
