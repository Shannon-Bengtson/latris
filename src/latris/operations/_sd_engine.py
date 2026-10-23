"""ODE integration — the ONLY module that imports scipy.

Works on plain floats: ``sd_inference`` strips units before calling in and
re-attaches them after, so scipy never sees a pint quantity. scipy is imported
lazily and lives in the existing ``data``/``server`` extras; Euler needs no
scipy at all.

Method mapping (``SDSettings.integration_method``):

- ``euler``    — fixed-step forward Euler at ``dt``, hand-rolled (scipy has none).
- ``rk4``      — ``solve_ivp(method="RK45", max_step=dt)``: adaptive 4(5)-order
  Runge–Kutta never stepping past ``dt``. Not the classical fixed-step RK4 of
  Vensim/Stella; results agree to solver tolerance, not bit-for-bit.
- ``rk2``      — ``solve_ivp(method="RK23", max_step=dt)``.
- ``adaptive`` — ``solve_ivp(method="RK45")`` with free step selection.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

Derivative = Callable[[float, list[float]], list[float]]

_RTOL = 1e-6
_ATOL = 1e-9
_EPS = 1e-9


@dataclass(frozen=True)
class EngineResult:
    times: list[float]
    states: list[list[float]]  # states[i][j]: stock j at times[i]
    success: bool
    message: str
    algorithm: str
    library_version: str


def _import_solve_ivp():
    try:
        import scipy
        from scipy.integrate import solve_ivp
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "System Dynamics simulation with rk2/rk4/adaptive requires scipy. "
            "Install it with: pip install 'latris[data]' (or use --method euler)"
        ) from exc
    return solve_ivp, scipy.__version__


def report_times(t0: float, t1: float, interval: float) -> list[float]:
    """Reporting grid from t0 to t1 inclusive, at ``interval`` spacing."""
    n = int((t1 - t0) / interval + _EPS)
    times = [t0 + k * interval for k in range(n + 1)]
    if t1 - times[-1] > _EPS * max(1.0, abs(t1)):
        times.append(t1)
    return times


def _euler(rhs: Derivative, y0: list[float], t0: float, t1: float, dt: float, interval: float) -> EngineResult:
    from latris import __version__

    stride = max(1, round(interval / dt))
    n_steps = int((t1 - t0) / dt + _EPS)
    t, y = t0, list(y0)
    times, states = [t], [list(y)]
    for k in range(1, n_steps + 1):
        dy = rhs(t, y)
        y = [yi + dt * di for yi, di in zip(y, dy, strict=True)]
        t = t0 + k * dt
        if k % stride == 0 or k == n_steps:
            times.append(t)
            states.append(list(y))
    if t1 - t > _EPS * max(1.0, abs(t1)):  # final partial step
        h = t1 - t
        dy = rhs(t, y)
        y = [yi + h * di for yi, di in zip(y, dy, strict=True)]
        times.append(t1)
        states.append(list(y))
    return EngineResult(
        times=times, states=states, success=True, message="completed",
        algorithm=f"forward-euler[dt={dt}]", library_version=f"latris {__version__}",
    )


def integrate(
    rhs: Derivative,
    y0: list[float],
    t0: float,
    t1: float,
    *,
    method: str,
    dt: float,
    interval: float,
) -> EngineResult:
    """Integrate ``dy/dt = rhs(t, y)`` from ``t0`` to ``t1``, reporting every ``interval``."""
    if method == "euler":
        return _euler(rhs, y0, t0, t1, dt, interval)

    solve_ivp, version = _import_solve_ivp()
    if method == "rk4":
        scipy_method, kwargs, label = "RK45", {"max_step": dt}, f"RK45,max_step={dt}"
    elif method == "rk2":
        scipy_method, kwargs, label = "RK23", {"max_step": dt}, f"RK23,max_step={dt}"
    elif method == "adaptive":
        scipy_method, kwargs, label = "RK45", {}, "RK45"
    else:
        raise ValueError(f"unknown integration method {method!r}; use euler, rk2, rk4 or adaptive")

    t_eval = report_times(t0, t1, interval)
    sol = solve_ivp(
        lambda t, y: rhs(float(t), [float(v) for v in y]),
        (t0, t1), list(y0), method=scipy_method, t_eval=t_eval, rtol=_RTOL, atol=_ATOL, **kwargs,
    )
    times = [float(t) for t in sol.t]
    states = [[float(sol.y[j][i]) for j in range(len(y0))] for i in range(len(times))]
    return EngineResult(
        times=times, states=states, success=bool(sol.success), message=str(sol.message),
        algorithm=f"scipy.integrate.solve_ivp[{label}]", library_version=f"scipy {version}",
    )
