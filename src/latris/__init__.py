__version__ = "0.18.0"

__all__ = ["Model", "__version__", "load"]


def __getattr__(name: str):  # noqa: ANN202 — the public API (``latris.api``), imported on first use
    if name in ("Model", "load"):
        from latris import api

        return getattr(api, name)
    raise AttributeError(f"module 'latris' has no attribute {name!r}")
