"""FCM inference — matrix-based steady-state computation.

Pure functions — no file I/O, no commits.  Callers load
substrate, weights, and settings, then pass them in.

FCM inference iterates ``A_new[j] = f(Σ_i A[i] × W[i,j])``
until convergence (or max iterations).  Transfer functions
squash the weighted sum into [0, 1].
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from latris.schema.settings import FCMSettings

# ── Protocols ────────────────────────────────────────────────────────


class _HasDirection(Protocol):
    id: str
    from_id: str
    to_id: str


# ── Result dataclass ─────────────────────────────────────────────────


@dataclass(frozen=True)
class FCMInferenceResult:
    """Result of FCM inference to steady state."""

    activations: dict[str, float]
    """Final activation level per entity (entity_id → value in [0,1])."""

    converged: bool
    """True if the system converged within max_iterations."""

    iterations: int
    """Number of iterations performed."""

    history: tuple[dict[str, float], ...]
    """Activation levels at each iteration (including initial state)."""


# ── Transfer functions ───────────────────────────────────────────────


def _sigmoid(x: float, lam: float) -> float:
    """Standard sigmoid: 1 / (1 + e^(-λx))."""
    try:
        return 1.0 / (1.0 + math.exp(-lam * x))
    except OverflowError:
        return 0.0 if lam * x < 0 else 1.0


def _tanh_rescaled(x: float, lam: float) -> float:
    """Hyperbolic tangent rescaled to [0, 1]."""
    return (math.tanh(lam * x) + 1.0) / 2.0


def _step(x: float, _lam: float) -> float:
    """Step function: 1 if x > 0, else 0."""
    return 1.0 if x > 0.0 else 0.0


_TRANSFER_FUNCTIONS = {
    "sigmoid": _sigmoid,
    "tanh": _tanh_rescaled,
    "step": _step,
}


# ── Core inference ───────────────────────────────────────────────────


def fcm_infer(
    edges: list[_HasDirection],
    weights: dict[str, float],
    entity_ids: list[str],
    *,
    initial_activations: dict[str, float] | None = None,
    clamped: dict[str, float] | None = None,
    settings: FCMSettings | None = None,
) -> FCMInferenceResult:
    """Run FCM inference to steady state.

    Parameters
    ----------
    edges
        Graph edges with ``id``, ``from_id``, ``to_id``.
    weights
        Edge ID → weight in [-1, +1].
    entity_ids
        All entity IDs participating in the FCM.
    initial_activations
        Optional starting activation levels (entity_id → value
        in [0, 1]).  Defaults to 0.5 for all entities.
    clamped
        Optional scenario clamps: entity_id → forced activation.
        Clamped nodes keep their value at every iteration.
    settings
        FCM settings (transfer function, λ, convergence threshold,
        max iterations).  Uses defaults if not provided.

    Returns
    -------
    FCMInferenceResult
        Final activations, convergence status, iteration count,
        and full history.
    """
    if settings is None:
        settings = FCMSettings()

    transfer_fn = _TRANSFER_FUNCTIONS.get(settings.transfer_function, _sigmoid)
    lam = settings.lambda_steepness
    threshold = settings.convergence_threshold
    max_iter = settings.max_iterations
    clamped = clamped or {}

    n = len(entity_ids)
    if n == 0:
        return FCMInferenceResult(
            activations={},
            converged=True,
            iterations=0,
            history=(),
        )

    # Build index mapping
    idx = {eid: i for i, eid in enumerate(entity_ids)}

    # Build weight matrix (row i influences column j)
    # W[i][j] = weight of edge from entity_ids[i] to entity_ids[j]
    W: list[list[float]] = [[0.0] * n for _ in range(n)]
    for e in edges:
        w = weights.get(e.id)
        if w is None:
            continue
        i = idx.get(e.from_id)
        j = idx.get(e.to_id)
        if i is not None and j is not None:
            W[i][j] = w

    # Initial activations
    A = [0.5] * n
    if initial_activations:
        for eid, val in initial_activations.items():
            if eid in idx:
                A[idx[eid]] = val

    # Apply initial clamps
    for eid, val in clamped.items():
        if eid in idx:
            A[idx[eid]] = val

    # Record initial state
    def _snapshot() -> dict[str, float]:
        return {entity_ids[i]: A[i] for i in range(n)}

    history: list[dict[str, float]] = [_snapshot()]

    # Iterate
    converged = False
    iterations = 0
    for iteration in range(max_iter):
        iterations = iteration + 1

        # Compute new activations
        A_new = [0.0] * n
        for j in range(n):
            if entity_ids[j] in clamped:
                A_new[j] = clamped[entity_ids[j]]
            else:
                weighted_sum = sum(A[i] * W[i][j] for i in range(n))
                A_new[j] = transfer_fn(weighted_sum, lam)

        history.append({entity_ids[i]: A_new[i] for i in range(n)})

        # Check convergence
        max_diff = max(abs(A_new[i] - A[i]) for i in range(n))
        if max_diff < threshold:
            converged = True
            A = A_new
            break

        A = A_new

    return FCMInferenceResult(
        activations={entity_ids[i]: A[i] for i in range(n)},
        converged=converged,
        iterations=iterations,
        history=tuple(history),
    )
