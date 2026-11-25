"""A model's contract: declaring the inputs a caller may give it and the outputs it returns.

The contract is what makes a model usable outside the workbench (``docs/engineering/PREDICT.md``): a
pipeline pins a version of the model, reads its contract, and calls ``operations/predict.predict`` with
values for the inputs. Declaring it is deliberate — every input is a promise to whoever calls it — so it
is drafted from the model (:func:`init`) and then edited (:func:`set_input`, :func:`set_output`).

:func:`check` says whether the contract still fits the model; :func:`compare` says what changed between
two versions, sorted by what it means for a caller: breaking, compatible, or internal only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from latris.operations._resolve import resolve_target
from latris.operations._sd_eval import slugify
from latris.operations._units import UnitError, is_compatible, parse_unit
from latris.operations.commit import auto_commit
from latris.operations.predictors import MODEL, Candidate, Predictor, key
from latris.repo import git
from latris.repo.layout import ProjectPaths
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model, load_model_from_string
from latris.schema import Substrate
from latris.schema.contract import Contract, ContractInput, ContractOutput

_UNSET: Any = object()
# What a model's behaviour is made of: a change here with the contract unchanged is "internal".
_MODEL_PATHS = ("substrate", "views/roles", "views/parameters")


# ── the model types that can have one ────────────────────────────────


def predictor_for(model_type: str, paths: ProjectPaths) -> Predictor:
    """The model of ``model_type`` in this project, loaded for running (``operations/predictors``)."""
    import importlib

    from latris.operations import formalisms

    plugin = formalisms.get(model_type)
    if plugin is None or not plugin.predictor:
        able = ", ".join(f.model_type for f in formalisms.all_formalisms() if f.predictor)
        raise ValueError(f"{model_type!r} has no contract: only model types that compute outputs from inputs "
                         f"do ({able})")
    return importlib.import_module(plugin.predictor).build(paths)


def model_types(paths: ProjectPaths) -> list[str]:
    """The model types with a contract in this project."""
    d = paths.contracts_dir
    return sorted(p.stem for p in d.glob("*.yaml")) if d.is_dir() else []


def default_model_type(model_type: str | None, paths: ProjectPaths) -> str:
    """``model_type`` if given; else the one model type with a contract here."""
    if model_type:
        return model_type
    have = model_types(paths)
    if len(have) == 1:
        return have[0]
    if not have:
        raise ValueError("this project has no contract yet: `latris contract init <model type>` drafts one")
    raise ValueError(f"this project has contracts for {', '.join(have)}: say which model type")


# ── reads ────────────────────────────────────────────────────────────


def known_model_type(model_type: str) -> str:
    """``model_type`` if it is one latris knows; refused otherwise. Every read and write of a contract comes
    through here, so a caller's text never chooses a file (``layout.contract_path`` refuses it too)."""
    from latris.operations import formalisms

    known = {f.model_type for f in formalisms.all_formalisms()}
    if not isinstance(model_type, str) or model_type not in known:
        able = ", ".join(sorted(f.model_type for f in formalisms.all_formalisms() if f.predictor))
        raise ValueError(f"unknown model type {str(model_type)[:60]!r}; a contract belongs to one of: {able}")
    return model_type


def get(model_type: str, *, root: Path | None = None) -> Contract | None:
    path = require_project(root).contract_path(known_model_type(model_type))
    return load_model(Contract, path) if path.exists() else None


def require(model_type: str, paths: ProjectPaths) -> Contract:
    contract = get(model_type, root=paths.root)
    if contract is None:
        raise ValueError(f"no contract for {model_type} yet: `latris contract init {model_type}` drafts one")
    return contract


def contract_hash(contract: Contract) -> str:
    """A short hash of the interface: names, the factors they stand for, kinds, units, modes and whether an
    input is required.

    It changes exactly when a caller might have to: a default or a description doesn't change it. A name
    pointed at a different factor does: the caller would be setting, or reading, something else.
    """
    # A cell joins the hash only where there is one, so a contract without cells hashes as it always has.
    interface = {
        "inputs": sorted([i.name, i.target_id, i.kind, i.units, i.mode, i.required, *([i.cell] if i.cell else [])]
                         for i in contract.inputs),
        "outputs": sorted([o.name, o.target_id, o.kind, o.units, o.metric, *([o.cell] if o.cell else [])]
                          for o in contract.outputs),
    }
    return hashlib.sha256(json.dumps(interface, sort_keys=True).encode()).hexdigest()[:12]


def _by_key(items: list[Candidate]) -> dict[str, Candidate]:
    return {c.key: c for c in items}


def entry_key(x: ContractInput | ContractOutput) -> str:
    return key(x.target_id, x.cell)


# ── units ────────────────────────────────────────────────────────────
# Units pint knows (metres, 1/year, dollar) are checked and converted. Units it doesn't (GBP, QALY) are
# opaque: kept as written, compatible only with exactly themselves, never converted.


def _parsed(units: str) -> Any:
    try:
        return parse_unit(units)
    except UnitError:
        return None


def units_compatible(a: str | None, b: str | None) -> bool:
    """Whether a value in ``a`` can be given in ``b``."""
    a, b = (a or "").strip(), (b or "").strip()
    if a == b:
        return True
    pa, pb = _parsed(a), _parsed(b)
    return pa is not None and pb is not None and is_compatible(pa, pb)


def convert(value: float, have: str | None, want: str | None) -> float:
    """``value`` in ``have`` expressed in ``want``; refused when they aren't compatible."""
    have, want = (have or "").strip(), (want or "").strip()
    if not have or not want or have == want:
        return value
    a, b = _parsed(have), _parsed(want)
    if a is None or b is None:
        raise ValueError(f"a value in {have} can't be given in {want}")
    if a == b:
        return value
    from latris.operations._units import Quantity

    try:
        return float(Quantity(float(value), a).to(b).magnitude)
    except Exception as exc:  # pint: another dimension, or units with an offset
        raise ValueError(f"a value in {have} can't be given in {want}") from exc


def describe(model_type: str | None = None, *, root: Path | None = None) -> dict[str, Any]:
    """The contract as a caller reads it: each input with its units, default, range and states; each output
    with its units; the contract's hash; and whether it still fits the model (``problems``)."""
    paths = require_project(root)
    model_type = default_model_type(model_type, paths)
    contract = require(model_type, paths)
    predictor = predictor_for(model_type, paths)
    return _describe(contract, predictor)


def _describe(contract: Contract, predictor: Predictor) -> dict[str, Any]:
    ins, outs = _by_key(predictor.inputs()), _by_key(predictor.outputs())
    inputs = []
    for i in contract.inputs:
        c = ins.get(entry_key(i))
        lo, hi = effective_range(i, c)
        inputs.append({
            "name": i.name, "label": c.label if c else None, "kind": i.kind, "units": i.units, "mode": i.mode,
            "default": i.default if i.default is not None else (_in_units(c.value, c.units, i.units)
                                                                if c and i.kind == "value" else None),
            "valid_min": lo, "valid_max": hi, "states": list(c.states) if c else [], "required": i.required,
            "description": i.description, "target_id": i.target_id, "cell": i.cell,
        })
    outputs = []
    for o in contract.outputs:
        c = outs.get(entry_key(o))
        outputs.append({"name": o.name, "label": c.label if c else None, "kind": o.kind, "units": o.units,
                        "metric": o.metric, "states": list(c.states) if c else [], "description": o.description,
                        "target_id": o.target_id, "cell": o.cell})
    return {"model_type": contract.model_type, "description": contract.description, "hash": contract_hash(contract),
            "inputs": inputs, "outputs": outputs, "problems": _problems(contract, predictor)}


def _in_units(value: Any, have: str | None, want: str | None) -> Any:
    """A model's own value expressed in the contract's units."""
    if value is None or not have or not want or have == want:
        return value
    return convert(float(value), have, want)


def effective_range(i: ContractInput, c: Candidate | None) -> tuple[float | None, float | None]:
    """The range an input accepts without a warning, in the contract's units: the contract's own, else the
    model's."""
    if i.kind != "value":
        return None, None
    lo = i.valid_min if i.valid_min is not None else _in_units(c.valid_min, c.units, i.units) if c else None
    hi = i.valid_max if i.valid_max is not None else _in_units(c.valid_max, c.units, i.units) if c else None
    return lo, hi


def candidates(model_type: str, *, root: Path | None = None) -> dict[str, Any]:
    """What this model could expose: every possible input and output, with what the contract already has."""
    paths = require_project(root)
    predictor = predictor_for(model_type, paths)
    contract = get(model_type, root=paths.root)
    used_in = {entry_key(i): i.name for i in contract.inputs} if contract else {}
    used_out: dict[str, list[str]] = {}
    for o in contract.outputs if contract else []:
        used_out.setdefault(entry_key(o), []).append(o.name)

    def row(c: Candidate, names: list[str]) -> dict[str, Any]:
        return {"target_id": c.target_id, "cell": c.cell, "label": c.label, "kinds": list(c.kinds), "units": c.units,
                "value": c.value, "valid_min": c.valid_min, "valid_max": c.valid_max, "states": list(c.states),
                "role": c.role, "needs_metric": c.needs_metric, "in_contract": names}

    return {"model_type": model_type, "problems": list(predictor.problems),
            "inputs": [row(c, [used_in[c.key]] if c.key in used_in else []) for c in predictor.inputs()],
            "outputs": [row(c, used_out.get(c.key, [])) for c in predictor.outputs()]}


# ── check ────────────────────────────────────────────────────────────


def _problems(contract: Contract, predictor: Predictor) -> list[str]:
    problems = [f"the model isn't ready to run: {p}" for p in predictor.problems]
    ins, outs = _by_key(predictor.inputs()), _by_key(predictor.outputs())
    if not contract.outputs:
        problems.append("the contract has no outputs: a caller would get nothing back")
    for i in contract.inputs:
        c = ins.get(entry_key(i))
        if c is None:
            problems.append(f"input {i.name!r}: its factor is no longer something this model takes as an input")
            continue
        if i.kind not in c.kinds:
            problems.append(f"input {i.name!r}: {c.label} is a {c.kinds[0]}, not a {i.kind}")
        elif i.kind == "value":
            if not units_compatible(i.units, c.units):
                problems.append(f"input {i.name!r} is in {i.units}, but {c.label} is in {c.units}")
        elif i.default is not None and i.default not in c.states:
            problems.append(f"input {i.name!r}: its default {i.default!r} is not a state of {c.label}")
    for o in contract.outputs:
        c = outs.get(entry_key(o))
        if c is None:
            problems.append(f"output {o.name!r}: its factor is no longer something this model computes")
        elif o.kind not in c.kinds:
            problems.append(f"output {o.name!r}: {c.label} can be {' or '.join(c.kinds)}, not a {o.kind}")
        elif o.kind == "value" and c.needs_metric and not o.metric:
            problems.append(f"output {o.name!r}: say which value of {c.label}'s run it is (metric: final, peak…)")
        else:
            problems += [f"output {o.name!r}{p}" for p in (_metric_problem(c, o.metric), _units_problem(c, o)) if p]
    return problems


def model_units(c: Candidate, kind: str, metric: str | None) -> str | None:
    """The units the model gives an output in: the factor's own, except for a measure of a run that isn't in
    them (``peak-time`` is a time; ``total`` is the factor's units times time)."""
    if kind in ("distribution", "choice"):
        return None
    if kind == "value" and metric and c.time_units:
        from latris.operations.sd_sensitivity import parse_metric

        try:
            name = parse_metric(metric)[0]
        except ValueError:
            return c.units
        if name == "peak-time":
            return c.time_units
        if name == "total" and c.units:
            per = f"/{c.time_units}"
            if c.units.replace(" ", "").endswith(per) and c.units.count("/") == 1:
                return c.units.replace(" ", "")[: -len(per)]  # tonne/year over years: tonne
            return f"({c.units}) * {c.time_units}" if any(ch in c.units for ch in "/*+- ") else \
                f"{c.units} * {c.time_units}"
    return c.units


def _metric_problem(c: Candidate, metric: str | None) -> str | None:
    """Why ``metric`` can't be measured on this output's run (``at:T`` outside the time it covers)."""
    if not metric or not c.time_range:
        return None
    from latris.operations.sd_sensitivity import parse_metric

    try:
        name, at = parse_metric(metric)
    except ValueError as exc:
        return f": {exc}"
    lo, hi = c.time_range
    if name == "at" and at is not None and not lo <= at <= hi:
        return f": at:{at:g} is outside the time the model runs over ({lo:g} to {hi:g} {c.time_units or ''})".rstrip()
    return None


def _units_problem(c: Candidate, o: ContractOutput) -> str | None:
    """Why the model's value can't be given in the units the contract promises."""
    have = model_units(c, o.kind, o.metric)
    if not o.units or not have or units_compatible(have, o.units):
        return None
    return (f" is in {o.units}, but {c.label} is in {have} now; set the output again to take the model's units "
            "(a caller reading the old ones must change)")


def convert_output(value: Any, have: str | None, want: str | None) -> Any:
    """A computed value (or each value of a run) in the contract's units."""
    if not have or not want or have == want or value is None:
        return value
    if isinstance(value, list):
        return [None if x is None else convert(float(x), have, want) for x in value]
    return convert(float(value), have, want)


def check(model_type: str | None = None, *, root: Path | None = None) -> list[str]:
    """What stops the contract being used; empty when it fits the model."""
    paths = require_project(root)
    model_type = default_model_type(model_type, paths)
    return _problems(require(model_type, paths), predictor_for(model_type, paths))


# ── writes ───────────────────────────────────────────────────────────


def _save(paths: ProjectPaths, contract: Contract, subject: str, body: str = "") -> str:
    contract = Contract.model_validate(contract.model_dump())  # the whole contract's rules (unique names…)
    path = paths.contract_path(contract.model_type)
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_model(contract, path)
    return auto_commit(paths.root, subject=subject, body=body, paths=[path])


def _unique(name: str, taken: set[str]) -> str:
    out, n = name, 2
    while out in taken:
        out, n = f"{name}_{n}", n + 1
    return out


def _input_from(c: Candidate, name: str) -> ContractInput:
    return ContractInput(name=name, target_id=c.target_id, cell=c.cell, kind=c.kinds[0],  # type: ignore[arg-type]
                         units=(c.units or "dimensionless") if c.kinds[0] == "value" else None)


def _output_from(c: Candidate, name: str, kind: str | None = None, metric: str | None = None) -> ContractOutput:
    kind = kind or ("value" if metric else c.kinds[0])
    if kind == "value" and c.needs_metric and not metric:
        metric = "final"
    return ContractOutput(name=name, target_id=c.target_id, cell=c.cell, kind=kind,  # type: ignore[arg-type]
                          units=model_units(c, kind, metric), metric=metric)


def draft(model_type: str, *, root: Path | None = None) -> Contract:
    """The contract the model suggests: what it treats as given, in; what it is for, out. Nothing is saved."""
    paths = require_project(root)
    predictor = predictor_for(model_type, paths)
    inputs, outputs = [], []
    taken: set[str] = set()
    for c in predictor.inputs():
        if c.suggested:
            name = _unique(slugify(c.label), taken)
            taken.add(name)
            inputs.append(_input_from(c, name))
    taken = set()
    for c in predictor.outputs():
        if c.suggested:
            name = _unique(slugify(c.label), taken)
            taken.add(name)
            outputs.append(_output_from(c, name))
    return Contract(model_type=model_type, inputs=inputs, outputs=outputs)


def init(model_type: str, *, replace: bool = False, root: Path | None = None) -> tuple[Contract, str]:
    """Save the drafted contract (refused if there is one already, unless ``replace``)."""
    paths = require_project(root)
    if get(model_type, root=paths.root) is not None and not replace:
        raise ValueError(f"{model_type} already has a contract; edit it, or replace it (--replace)")
    contract = draft(model_type, root=paths.root)
    if not contract.outputs:
        raise ValueError(f"the {model_type} model doesn't say what it is for yet (no outcome or output), so there "
                         "is nothing to draft; mark its output first")
    sha = _save(paths, contract, f"Contract for {model_type}: {len(contract.inputs)} input(s), "
                                 f"{len(contract.outputs)} output(s)")
    return contract, sha


def _candidate(paths: ProjectPaths, target: str, pool: list[Candidate], what: str,
               cell: str | None = None) -> Candidate:
    """The candidate for ``target`` (a factor, or a link when the model's parameters sit on links), and
    ``cell`` when the factor has several."""
    substrate = load_model(Substrate, paths.conceptual_yaml)
    # What belongs to the whole model (a discount rate) is named "model".
    tid = MODEL if target == MODEL and any(c.target_id == MODEL for c in pool) else resolve_target(target, substrate)
    mine = [c for c in pool if c.target_id == tid]
    label = next((e.label for e in substrate.entities if e.id == tid), "the model" if tid == MODEL else None)
    if label is None:  # a link: only model types that hold parameters on links (a Markov transition) take one
        if not mine:
            raise ValueError(f"{target!r} is a link; a contract names factors")
        label = mine[0].label
    if not mine:
        raise ValueError(f"{label} can't be {what} of this model. It could be: "
                         + (", ".join(dict.fromkeys(c.label for c in pool)) or "(nothing yet)"))
    if cell is not None:
        found = next((c for c in mine if c.cell == cell), None)
        if found is None:
            raise ValueError(f"{label} has no {cell!r} to be {what}; it has: "
                             + ", ".join(f"{c.cell} ({c.label})" for c in mine if c.cell))
        return found
    if len(mine) > 1:
        raise ValueError(f"{label} holds several things that can be {what}; say which with its cell: "
                         + "; ".join(f"{c.cell} ({c.label})" for c in mine))
    return mine[0]


def set_input(
    model_type: str,
    target: str,
    *,
    name: str | None = None,
    units: str | None = None,
    default: Any = _UNSET,
    valid_min: Any = _UNSET,
    valid_max: Any = _UNSET,
    mode: str | None = None,
    required: bool | None = None,
    description: str | None = None,
    cell: str | None = None,
    root: Path | None = None,
) -> tuple[ContractInput, str]:
    """Add a factor (or, with ``cell``, one of its parameters) to the contract as an input, or change the input
    it already is (only what is given)."""
    paths = require_project(root)
    c = _candidate(paths, target, predictor_for(model_type, paths).inputs(), "an input", cell)
    contract = get(model_type, root=paths.root) or Contract(model_type=model_type)
    current = next((i for i in contract.inputs if entry_key(i) == c.key), None)
    taken = {i.name for i in contract.inputs if i is not current}
    base = current.model_dump() if current else _input_from(c, _unique(slugify(c.label), taken)).model_dump()
    given = {"name": name, "units": units, "mode": mode, "required": required, "description": description}
    changed = {k: v for k, v in given.items() if v is not None}
    changed |= {k: v for k, v in (("default", default), ("valid_min", valid_min), ("valid_max", valid_max))
                if v is not _UNSET}
    entry = ContractInput.model_validate({**base, **changed})
    if entry.kind == "value" and not units_compatible(entry.units, c.units):
        raise ValueError(f"{c.label} is in {c.units}; an input in {entry.units} can't set it")
    if entry.kind == "state" and entry.default is not None and entry.default not in c.states:
        raise ValueError(f"{entry.default!r} is not a state of {c.label} (states: {', '.join(c.states)})")
    contract.inputs = [i for i in contract.inputs if i is not current] + [entry]
    sha = _save(paths, contract, f"Contract for {model_type}: input {entry.name} ({c.label})")
    return entry, sha


def set_output(
    model_type: str,
    target: str,
    *,
    name: str | None = None,
    kind: str | None = None,
    metric: str | None = None,
    description: str | None = None,
    cell: str | None = None,
    root: Path | None = None,
) -> tuple[ContractOutput, str]:
    """Add an output to the contract, or change the one called ``name``.

    A factor can be several outputs (a system dynamics stock's whole run, and its peak), so an output is
    identified by its name: without ``name`` the factor's own (slugified) is used. A name that already
    stands for another factor is refused: a caller reading it would silently get something else. Remove it
    first to reuse the name.

    An output being changed keeps its units while the model's are still compatible with them (the value is
    converted on the way out); otherwise it takes the model's.
    """
    paths = require_project(root)
    predictor = predictor_for(model_type, paths)
    c = _candidate(paths, target, predictor.outputs(), "an output", cell)
    contract = get(model_type, root=paths.root) or Contract(model_type=model_type)
    name = name or slugify(c.label)
    current = next((o for o in contract.outputs if o.name == name), None)
    if current is not None and entry_key(current) != c.key:
        other = _by_key(predictor.outputs()).get(entry_key(current))
        raise ValueError(f"the contract already has an output called {name!r}, for "
                         f"{other.label if other else 'another factor'}; give {c.label}'s another name (--name), "
                         f"or remove that one first (`latris contract remove {model_type} {name}`)")
    if metric:
        from latris.operations.sd_sensitivity import parse_metric

        parse_metric(metric)
    entry = _output_from(c, name, kind or (current.kind if current and not metric else None),
                         metric or (current.metric if current and kind in (None, "value") else None))
    if entry.kind not in c.kinds:
        raise ValueError(f"{c.label} can be {' or '.join(c.kinds)}, not a {entry.kind}")
    if entry.metric and not c.needs_metric:
        raise ValueError(f"{c.label} is a single value: it has no metric")
    bad = _metric_problem(c, entry.metric)
    if bad:
        raise ValueError(f"output {entry.name!r}{bad}")
    if (current and current.units and entry.units and (current.kind, current.metric) == (entry.kind, entry.metric)
            and _units_problem(c, current) is None):
        entry = entry.model_copy(update={"units": current.units})
    if description is not None or current:
        entry = entry.model_copy(update={"description": description if description is not None
                                         else current.description if current else ""})
    contract.outputs = [o for o in contract.outputs if o is not current] + [entry]
    sha = _save(paths, contract, f"Contract for {model_type}: output {entry.name} ({c.label})")
    return entry, sha


def remove(model_type: str, name: str, *, root: Path | None = None) -> str:
    """Take an input or an output out of the contract, by its name."""
    paths = require_project(root)
    contract = require(model_type, paths)
    inputs = [i for i in contract.inputs if i.name != name]
    outputs = [o for o in contract.outputs if o.name != name]
    if len(inputs) == len(contract.inputs) and len(outputs) == len(contract.outputs):
        known = ", ".join([i.name for i in contract.inputs] + [o.name for o in contract.outputs])
        raise ValueError(f"the contract has no input or output named {name!r} (it has: {known})")
    contract.inputs, contract.outputs = inputs, outputs
    return _save(paths, contract, f"Contract for {model_type}: removed {name}")


# ── what changed between two versions ────────────────────────────────


def _at(paths: ProjectPaths, model_type: str, sha: str) -> Contract | None:
    rel = paths.contract_path(model_type).relative_to(paths.root).as_posix()
    try:
        return load_model_from_string(Contract, git.show_file(paths.root, sha, rel))
    except git.GitError:
        return None


def compare(base: str, head: str | None = None, *, model_type: str | None = None,
            root: Path | None = None) -> dict[str, Any]:
    """What changed for a caller between two versions (``head`` defaults to the latest save).

    - **breaking**: a caller written against ``base`` may fail or be misread on ``head`` — an input or
      output gone or renamed, pointed at a different factor, its kind or units changed (in the contract, or
      in the model so that it can no longer be given in the contract's), an input now required, a new
      required input;
    - **compatible**: the caller still works — an optional input or an output added, a default or a valid
      range changed, an input no longer required;
    - **internal**: the contract is the same, but the model behind it changed, so the same inputs may give
      different outputs.
    """
    from latris.operations.predict import resolve_ref

    paths = require_project(root)
    a = resolve_ref(base, paths)
    b = resolve_ref(head or "HEAD", paths)
    model_type = default_model_type(model_type, paths)
    old, new = _at(paths, model_type, a), _at(paths, model_type, b)
    breaking: list[str] = []
    compatible: list[str] = []
    if old is None and new is None:
        raise ValueError(f"neither version has a contract for {model_type}")
    if old is None:
        compatible.append("the contract is new")
    elif new is None:
        breaking.append("the contract was removed")
    else:
        _compare_inputs(old, new, breaking, compatible)
        _compare_outputs(old, new, breaking, compatible)
        breaking += _model_units_changed(paths, model_type, a, b, old, new)
    model_changed = bool(git.changed_paths(paths.root, a, b, list(_MODEL_PATHS))) if a != b else False
    verdict = "breaking" if breaking else "compatible" if compatible else "internal" if model_changed else "same"
    return {"model_type": model_type, "base": a, "head": b, "verdict": verdict, "breaking": breaking,
            "compatible": compatible, "model_changed": model_changed,
            "base_hash": contract_hash(old) if old else None, "head_hash": contract_hash(new) if new else None}


def _output_unit_problems(paths: ProjectPaths, model_type: str, sha: str, contract: Contract) -> dict[str, str] | None:
    """Output name → why the model at ``sha`` can't give it in the contract's units; None if that version
    can't be loaded (written by another latris, say), in which case nothing is claimed about it."""
    from pydantic import ValidationError

    from latris.operations.predict import materialise

    try:
        outs = _by_key(predictor_for(model_type, ProjectPaths(materialise(sha, paths))).outputs())
    except (ValueError, ValidationError, git.GitError, OSError):
        return None
    found = {}
    for o in contract.outputs:
        c = outs.get(entry_key(o))
        problem = _units_problem(c, o) if c else None
        if problem:
            found[o.name] = problem
    return found


def _model_units_changed(paths: ProjectPaths, model_type: str, a: str, b: str, old: Contract,
                         new: Contract) -> list[str]:
    """Outputs whose contract still promises the same units while the model stopped giving them: the
    contract reads "same", but a caller no longer gets what it says."""
    if a == b:
        return []
    after = _output_unit_problems(paths, model_type, b, new)
    if not after:
        return []
    before = _output_unit_problems(paths, model_type, a, old) or {}
    return [f"output {name}{why}" for name, why in sorted(after.items()) if name not in before]


def _compare_inputs(old: Contract, new: Contract, breaking: list[str], compatible: list[str]) -> None:
    before, after = {i.name: i for i in old.inputs}, {i.name: i for i in new.inputs}
    for name, i in sorted(before.items()):
        j = after.get(name)
        if j is None:
            breaking.append(f"input {name} was removed")
            continue
        if i.target_id != j.target_id:
            breaking.append(f"input {name} now sets a different factor")
        elif i.cell != j.cell:
            breaking.append(f"input {name} now sets a different parameter of its factor")
        if (i.kind, i.units, i.mode) != (j.kind, j.units, j.mode):
            breaking.append(f"input {name} changed from {_shape(i)} to {_shape(j)}")
        if j.required and not i.required:
            breaking.append(f"input {name} is now required")
        elif i.required and not j.required:
            compatible.append(f"input {name} is no longer required")
        if i.default != j.default:
            compatible.append(f"input {name}: default changed from {i.default} to {j.default}")
        if (i.valid_min, i.valid_max) != (j.valid_min, j.valid_max):
            compatible.append(f"input {name}: valid range changed")
    for name, j in sorted(after.items()):
        if name not in before:
            (breaking if j.required else compatible).append(
                f"input {name} was added" + (" and is required" if j.required else ""))


def _compare_outputs(old: Contract, new: Contract, breaking: list[str], compatible: list[str]) -> None:
    before, after = {o.name: o for o in old.outputs}, {o.name: o for o in new.outputs}
    for name, o in sorted(before.items()):
        p = after.get(name)
        if p is None:
            breaking.append(f"output {name} was removed")
            continue
        if o.target_id != p.target_id:
            breaking.append(f"output {name} now reports a different factor")
        elif o.cell != p.cell:
            breaking.append(f"output {name} now reports a different result of its factor")
        if (o.kind, o.units, o.metric) != (p.kind, p.units, p.metric):
            breaking.append(f"output {name} changed from {_shape(o)} to {_shape(p)}")
    compatible.extend(f"output {name} was added" for name in sorted(after) if name not in before)


def _shape(x: ContractInput | ContractOutput) -> str:
    if isinstance(x, ContractInput):
        return f"a value in {x.units}" if x.kind == "value" else f"a state ({x.mode})"
    return {"value": f"a value in {x.units}" + (f" ({x.metric})" if x.metric else ""),
            "series": f"a series in {x.units}", "distribution": "a distribution", "choice": "a choice"}[x.kind]
