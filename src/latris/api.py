"""The public Python API: load a model, pinned to a version if you like, and call it.

    import latris

    model = latris.load("path/to/project", ref="Client deliverable v1")
    result = model.predict({"flow_depth": 2.5})
    result["outputs"]["discharge"]["value"]      # the number
    result["warnings"]                           # e.g. an input outside its valid range
    result["provenance"]["commit"]               # exactly which version produced it

This is the whole supported surface for now (``docs/engineering/PREDICT.md``). Everything under
``latris.operations`` and ``latris.schema`` is internal and may change between releases.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class Model:
    """A model at one version, ready to be called. Build it once; ``predict`` writes nothing."""

    def __init__(self, loaded: Any) -> None:
        self._loaded = loaded

    @property
    def model_type(self) -> str:
        return self._loaded.model_type

    @property
    def commit(self) -> str | None:
        """The commit this model was loaded from."""
        return self._loaded.commit

    @property
    def contract(self) -> dict[str, Any]:
        """The contract: ``inputs`` and ``outputs`` (name, label, kind, units, default, valid range, states),
        its ``hash``, any ``problems``, and this version's ``provenance``."""
        return self._loaded.describe()

    def predict(self, inputs: dict[str, Any] | None = None, *, require: str | None = None) -> dict[str, Any]:
        """Run the model. ``inputs``: contract input name → a number (in the input's units), a string with
        units (``"250 cm"``) or a state's name. Returns ``outputs``, the ``inputs`` used, ``warnings`` and
        ``provenance``. ``require="approved"`` refuses a version that hasn't been approved."""
        return self._loaded.predict(inputs, require=require)

    def predict_many(self, rows: list[dict[str, Any]], *, require: str | None = None) -> list[dict[str, Any]]:
        """``predict`` for each set of inputs."""
        return self._loaded.predict_many(rows, require=require)

    def __repr__(self) -> str:
        return f"<latris.Model {self.model_type} at {(self.commit or 'working folder')[:10]}>"


def load(path: str | Path = ".", *, ref: str | None = None, model_type: str | None = None) -> Model:
    """Load the model in the project at ``path``.

    ``ref`` pins it: a commit, a milestone's name or a version's name. Without it, the project's files as
    they are now. ``model_type`` says which model when the project has contracts for several.
    """
    from latris.operations import predict as ops

    return Model(ops.load(model_type=model_type, ref=ref, root=Path(path)))
