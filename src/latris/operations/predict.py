"""Predict — run a model on a caller's inputs, statelessly, on a pinned version if asked.

``docs/engineering/PREDICT.md`` has the design. In short: a model declares a contract
(``operations/contract.py``); a caller gives values for its inputs and gets its outputs back, with what it
should know about them (warnings) and exactly what produced them (provenance: the commit, the contract's
hash, the review state of that version).

Nothing is written to the project. That is the difference from an analysis, which is recorded for the
report: a prediction is a call, made by a pipeline or a person, as many times as they like.

A **pinned** run (``ref``: a commit, a milestone's name, a version's name) reads that commit's files, not
the working folder: the commit is exported once to a cache folder and loaded from there
(:func:`materialise`). :class:`LoadedModel` keeps the compiled model, so many calls cost one load.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from latris.operations import contract as contract_ops
from latris.operations._units import with_units
from latris.operations.predictors import Candidate, Predictor
from latris.repo import git
from latris.repo.layout import ProjectPaths, pinned_cache_dir
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model, load_model_from_string
from latris.schema.contract import Contract, ContractInput

REVIEW_LEVELS = ("proposed", "reviewed", "approved")


def _span(lo: float | None, hi: float | None, units: str) -> str:
    if lo is None:
        return f"at most {with_units(f'{hi:g}', units)}"
    if hi is None:
        return f"at least {with_units(f'{lo:g}', units)}"
    return f"{lo:g} to {with_units(f'{hi:g}', units)}"


def _refuse_impossible(i: ContractInput, c: Candidate, shown: float, value: float) -> None:
    """A value the model can't take at all (a probability above 1) is refused, not warned about."""
    if c.exact and ((c.valid_min is not None and value < c.valid_min)
                    or (c.valid_max is not None and value > c.valid_max)):
        span = _span(c.valid_min, c.valid_max, "")
        raise ValueError(f"input {i.name!r} = {with_units(f'{shown:g}', i.units or '')} is impossible: {c.label} "
                         f"must be {span}")


# ── which commit ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class Pin:
    commit: str
    ref: str
    milestone: dict[str, Any] | None = None  # {name, maturity} when the ref named a milestone


def _milestone(ref: str, paths: ProjectPaths) -> dict[str, Any] | None:
    """The milestone called ``ref`` (by name or id), on any version."""
    from latris.operations import lineage
    from latris.schema.lineage import MilestoneLog

    rel = paths.milestones_yaml.relative_to(paths.root).as_posix()
    try:
        tree = lineage.get_lineage_tree(paths.root)
    except (git.GitError, ValueError, OSError):
        return None
    for node in tree["nodes"]:
        try:
            branch = lineage._branch_for_version(node, tree)
            log = load_model_from_string(MilestoneLog, git.show_file(paths.root, branch, rel))
        except git.GitError:
            continue
        for m in log.entries:
            if ref in (m.id, m.name):
                return {"name": m.name, "maturity": m.maturity, "commit": m.commit_sha}
    return None


def pin(ref: str, paths: ProjectPaths) -> Pin:
    """The commit ``ref`` stands for: a milestone (by name), else anything git can name (a commit, a branch),
    else a version by its name."""
    found = _milestone(ref, paths)
    if found:
        return Pin(found["commit"], ref, {"name": found["name"], "maturity": found["maturity"]})
    try:
        return Pin(git.resolve_commit(paths.root, ref), ref)
    except git.GitError:
        pass
    from latris.operations import lineage

    try:
        tree = lineage.get_lineage_tree(paths.root)
        node = lineage._resolve_version(ref, tree["nodes"])
        return Pin(git.resolve_commit(paths.root, lineage._branch_for_version(node, tree)), ref)
    except (git.GitError, ValueError, LookupError) as exc:
        raise ValueError(f"no commit, milestone or version called {ref!r} in this project") from exc


def resolve_ref(ref: str, paths: ProjectPaths) -> str:
    return pin(ref, paths).commit


def materialise(commit: str, paths: ProjectPaths) -> Path:
    """A folder holding the project exactly as it was at ``commit`` (exported once, then reused)."""
    dest = pinned_cache_dir() / commit
    if (dest / ".graph-tooling").is_dir():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f"{commit[:12]}-", dir=dest.parent)) / "tree"
    try:
        git.export_commit(paths.root, commit, staging)
        if not (staging / ".graph-tooling").is_dir():
            raise ValueError(f"commit {commit[:10]} is not a Latris project")
        try:
            staging.rename(dest)
        except OSError:  # another process exported it first
            if not (dest / ".graph-tooling").is_dir():
                raise
    finally:
        git.remove_tree(staging.parent)
    return dest


# ── a loaded model ───────────────────────────────────────────────────


def _review(paths: ProjectPaths, milestone: dict[str, Any] | None) -> dict[str, Any]:
    """Who has stood behind this version: the version's own maturity, and the milestone's if one was named."""
    from latris.schema.lineage import LineageNode

    out: dict[str, Any] = {"version": None, "maturity": None, "milestone": milestone}
    if paths.lineage_node_yaml.exists():
        node = load_model(LineageNode, paths.lineage_node_yaml)
        out.update(version=node.name, maturity=node.maturity)
    return out


class LoadedModel:
    """A model of one type, at one commit (or the working folder), compiled and ready to be called.

    ``predict`` is pure: build one of these, call it as often as needed.
    """

    def __init__(self, paths: ProjectPaths, model_type: str, *, source: ProjectPaths | None = None,
                 pinned: Pin | None = None) -> None:
        from pydantic import ValidationError

        import latris
        from latris.schema import ProjectFoundation

        source = source or paths
        self.model_type = model_type
        try:
            self.contract: Contract = contract_ops.require(model_type, paths)
            self.predictor: Predictor = contract_ops.predictor_for(model_type, paths)
            project = load_model(ProjectFoundation, paths.project_yaml)
        except ValidationError as exc:
            raise ValueError("this version of the model can't be read by this version of latris "
                             f"({latris.__version__}): {exc.errors()[0]['msg']}") from exc
        self.problems = contract_ops._problems(self.contract, self.predictor)
        self._ins = {c.key: c for c in self.predictor.inputs()}
        try:
            commit, dirty = (pinned.commit, False) if pinned else (git.head_sha(source.root), git.is_dirty(source.root))
        except git.GitError:
            commit, dirty = None, False
        self.provenance: dict[str, Any] = {
            "project": project.name, "model_type": model_type, "ref": pinned.ref if pinned else None,
            "commit": commit, "uncommitted_changes": dirty, "contract_hash": contract_ops.contract_hash(self.contract),
            "latris_version": latris.__version__, "review": _review(paths, pinned.milestone if pinned else None),
        }

    @property
    def commit(self) -> str | None:
        return self.provenance["commit"]

    def describe(self) -> dict[str, Any]:
        """The contract as a caller reads it, with this version's provenance."""
        return {**contract_ops._describe(self.contract, self.predictor), "provenance": dict(self.provenance)}

    # ── one call ──

    def _number(self, i: ContractInput, c: Candidate, given: Any) -> tuple[float, float]:
        """A given value as (in the contract's units, in the model's units). ``given`` is a number, a string
        such as "250 cm", or {"value": 250, "units": "cm"}."""
        units = i.units or ""
        if isinstance(given, dict):
            given, units = given.get("value"), given.get("units") or units
            if not isinstance(units, str):
                raise ValueError(f"input {i.name!r}: units must be text such as \"cm\", got {units!r}")
        elif isinstance(given, str):
            head, _, tail = given.strip().partition(" ")
            given, units = head, tail.strip() or units
        try:
            if isinstance(given, bool):
                raise TypeError
            number = float(given)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"input {i.name!r} needs a number, got {given!r}") from exc
        if not contract_ops.units_compatible(units, i.units):
            raise ValueError(f"input {i.name!r} is in {i.units}; a value in {units} can't be used")
        return (contract_ops.convert(number, units, i.units),
                contract_ops.convert(number, units, c.units or i.units))

    def predict(self, inputs: dict[str, Any] | None = None, *, require: str | None = None) -> dict[str, Any]:
        """Run the model on ``inputs`` (by the contract's input names) and return its outputs.

        Returns ``{"outputs": {name: {value | series | distribution | choice, units, label}}, "inputs": {name: {value,
        units, source}}, "warnings": [...], "provenance": {...}}``. An input left out takes the contract's
        default, else the model's own value. A value outside its valid range is used as given and reported
        in ``warnings``. ``require`` ("reviewed" or "approved") refuses a version that hasn't reached it.
        """
        self._require(require)
        if self.problems:
            raise ValueError("the contract can't be run: " + "; ".join(self.problems))
        given = dict(inputs or {})
        known = {i.name for i in self.contract.inputs}
        unknown = sorted(set(given) - known)
        if unknown:
            raise ValueError(f"unknown input(s) {', '.join(unknown)}; this contract takes: "
                             f"{', '.join(sorted(known)) or '(no inputs)'}")
        values, modes, used, warnings = self._inputs(given)
        run = self.predictor.run(values, modes, list(self.contract.outputs))
        declared = {contract_ops.entry_key(i) for i in self.contract.inputs}
        notes = warnings + [text for target, text in run.warnings if target not in declared]
        if self.provenance["uncommitted_changes"]:
            notes.append("the model has changes that aren't saved yet, so this result can't be traced to a commit")
        return {"outputs": self._outputs(run.outputs), "inputs": used, "warnings": notes,
                "provenance": dict(self.provenance)}

    def _inputs(self, given: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str], dict[str, Any], list[str]]:
        """What the run takes (values and modes by key), what was used for each input, and range warnings."""
        values: dict[str, Any] = {}
        modes: dict[str, str] = {}
        used: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        for i in self.contract.inputs:
            k = contract_ops.entry_key(i)
            c = self._ins[k]
            raw, source = (given[i.name], "given") if i.name in given and given[i.name] is not None else (
                (i.default, "default") if i.default is not None else (None, "model"))
            if raw is None and i.required:
                raise ValueError(f"input {i.name!r} is required")
            if i.kind == "state":
                modes[k] = i.mode
                if raw is not None:
                    values[k] = str(raw)
                used[i.name] = {"value": None if raw is None else str(raw), "units": None, "source": source}
                continue
            if raw is None:  # the model's own value: nothing to set
                shown = contract_ops._in_units(c.value, c.units, i.units)
            else:
                shown, values[k] = self._number(i, c, raw)
                _refuse_impossible(i, c, shown, values[k])
            used[i.name] = {"value": shown, "units": i.units, "source": source}
            lo, hi = contract_ops.effective_range(i, c)
            if shown is not None and ((lo is not None and shown < lo) or (hi is not None and shown > hi)):
                warnings.append(f"input {i.name} = {with_units(f'{shown:g}', i.units or '')} is outside its valid "
                                f"range ({_span(lo, hi, i.units or '')}): the result is an extrapolation")
        return values, modes, used, warnings

    def _outputs(self, computed: dict[str, Any]) -> dict[str, Any]:
        """Each output in the contract's units (the model computes in its own), under the field of its kind."""
        outs = {c.key: c for c in self.predictor.outputs()}
        outputs = {}
        for o in self.contract.outputs:
            c, result = outs.get(contract_ops.entry_key(o)), computed[o.name]
            have = contract_ops.model_units(c, o.kind, o.metric) if c else None
            try:
                if o.kind == "series" and isinstance(result, dict):
                    result = {**result, "values": contract_ops.convert_output(result["values"], have, o.units)}
                elif o.kind == "value":
                    result = contract_ops.convert_output(result, have, o.units)
            except ValueError as exc:
                raise ValueError(f"output {o.name!r}: {exc}") from exc
            # value | series | distribution | choice: the field the result is under
            outputs[o.name] = {o.kind: result, "units": o.units, "label": c.label if c else None}
        return outputs

    def predict_many(self, rows: list[dict[str, Any]], *, require: str | None = None) -> list[dict[str, Any]]:
        """``predict`` for each row of inputs, on the one loaded model."""
        return [self.predict(row, require=require) for row in rows]

    def _require(self, level: str | None) -> None:
        if not level:
            return
        if level not in REVIEW_LEVELS[1:]:
            raise ValueError("require must be 'reviewed' or 'approved'")
        review = self.provenance["review"]
        have = (review["milestone"] or {}).get("maturity") or review["maturity"] or "proposed"
        if REVIEW_LEVELS.index(have) < REVIEW_LEVELS.index(level):
            what = f"milestone {review['milestone']['name']!r}" if review["milestone"] else "this version"
            raise ValueError(f"{what} is {have}, not {level}")


def load(*, model_type: str | None = None, ref: str | None = None, root: Path | None = None) -> LoadedModel:
    """Load a model for calling: the working folder's, or (``ref``) a pinned version's."""
    paths = require_project(root)
    if ref is not None and not isinstance(ref, str):
        raise ValueError(f"ref must be the name of a commit, milestone or version, got {ref!r}")
    if not (ref or "").strip():  # no ref, or an empty one (a form left blank): the working folder
        return LoadedModel(paths, contract_ops.default_model_type(model_type, paths))
    pinned = pin(ref, paths)
    at = ProjectPaths(materialise(pinned.commit, paths))
    return LoadedModel(at, contract_ops.default_model_type(model_type, at), source=paths, pinned=pinned)


def predict(inputs: dict[str, Any] | None = None, *, model_type: str | None = None, ref: str | None = None,
            require: str | None = None, root: Path | None = None) -> dict[str, Any]:
    """One call: load (see :func:`load`) and run. For many calls, keep the loaded model."""
    return load(model_type=model_type, ref=ref, root=root).predict(inputs, require=require)


def parse_assignment(text: str) -> tuple[str, Any]:
    """``"depth=2.5"``, ``"depth=250 cm"`` or ``"rain=yes"`` → (input name, value as given)."""
    name, sep, value = (text or "").partition("=")
    if not sep or not name.strip() or not value.strip():
        raise ValueError(f"expected 'input=value', got {text!r}")
    return name.strip(), value.strip()
