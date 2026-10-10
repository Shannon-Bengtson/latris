"""CompletenessGate operations (AI interrogation Phase 2c).

The gate runs before each ``Interpret*`` prompt. It identifies
variables required to answer the modelling question that are missing
from the model. Reports persist per model type so override decisions
survive subsequent runs.

Override flow uses the existing :class:`Exclusion` record (from
:mod:`latris.schema.provenance`) — a vanilla statement +
rationale — plus a back-reference on the ``MissingVariable`` row
(``excluded_via_id``). This avoids adding a discriminator to
``Exclusion`` while keeping the audit chain intact.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from latris.operations.commit import auto_commit
from latris.operations.provenance import add_exclusion
from latris.repo.layout import ProjectPaths
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import (
    CompletenessReport,
    ExclusionLog,
    HumanActor,
    MissingVariable,
    Substrate,
)

# ── Loading / saving ────────────────────────────────────────────────────


def _report_path(paths: ProjectPaths, model_type: str) -> Path:
    return paths.completeness_report_yaml(model_type)


def load_report(model_type: str, *, root: Path | None = None) -> CompletenessReport:
    """Load the per-model-type completeness report (empty if absent)."""
    paths = require_project(root)
    path = _report_path(paths, model_type)
    if not path.exists():
        return CompletenessReport(model_type=model_type)
    return load_model(CompletenessReport, path)


def save_report(
    report: CompletenessReport,
    *,
    subject: str,
    root: Path | None = None,
) -> str:
    """Persist a completeness report and commit."""
    paths = require_project(root)
    path = _report_path(paths, report.model_type)
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_model(report, path)
    return auto_commit(paths.root, subject=subject, paths=[path])


# ── Listing + filtering ─────────────────────────────────────────────────


def list_missing_variables(
    model_type: str,
    *,
    disposition_filter: str | None = None,
    root: Path | None = None,
) -> list[MissingVariable]:
    report = load_report(model_type, root=root)
    if disposition_filter is None:
        return list(report.entries)
    return [mv for mv in report.entries if mv.disposition == disposition_filter]


def get_missing_variable(
    model_type: str, missing_var_id: str, *, root: Path | None = None
) -> MissingVariable:
    report = load_report(model_type, root=root)
    for mv in report.entries:
        if mv.id == missing_var_id:
            return mv
    raise ValueError(f"no missing-variable {missing_var_id!r} in {model_type} report")


# ── Merging gate results ────────────────────────────────────────────────


def _excluded_names(model_type: str, paths: ProjectPaths) -> set[str]:
    """Names of variables the user has previously excluded for this model.

    Combines the per-model-type ``excluded`` and ``dismissed`` rows
    (back-reference path) with name matches against project-wide
    ``ExclusionLog`` (legacy / human-authored fallback). All names
    are lower-cased so case mismatches don't slip through.
    """
    names: set[str] = set()
    path = _report_path(paths, model_type)
    if path.exists():
        report = load_model(CompletenessReport, path)
        for mv in report.entries:
            if mv.disposition in {"excluded", "dismissed"}:
                names.add(mv.name.strip().lower())

    if paths.exclusions_yaml.exists():
        log = load_model(ExclusionLog, paths.exclusions_yaml)
        prefix = "Variable '"
        for ex in log.entries:
            stmt = ex.statement
            if stmt.startswith(prefix) and "' deliberately excluded" in stmt:
                # Recover the variable name from the canonical statement.
                inner = stmt[len(prefix) :].split("'", 1)[0]
                names.add(inner.strip().lower())
    return names


def _modelled_entity_labels(paths: ProjectPaths) -> set[str]:
    if not paths.conceptual_yaml.exists():
        return set()
    sub = load_model(Substrate, paths.conceptual_yaml)
    return {e.label.strip().lower() for e in sub.entities}


def merge_gate_result(
    result, *, root: Path | None = None
) -> tuple[CompletenessReport, str]:
    """Merge a CompletenessGateResult into the on-disk report.

    Preserves rows whose status is ``excluded``, ``dismissed``, or
    ``added_to_model``. Drops new proposals that match excluded
    names or current entity labels. Existing ``open`` rows whose
    name matches a new proposal get their rationale / required_for /
    severity / confidence updated rather than duplicated.
    """
    from latris.ai.proposals import (
        CompletenessGateResult as _CompletenessGateResult,
    )
    from latris.ai.proposals import (
        MissingVariableProposal as _MissingVariableProposal,
    )

    if not isinstance(result, _CompletenessGateResult):
        raise TypeError("merge_gate_result expects a CompletenessGateResult")

    from latris.operations.interpret import coverage_ratio as _compute_coverage_ratio

    paths = require_project(root)
    model_type = result.model_type or "cld"
    existing = load_report(model_type, root=root)
    # Coverage ratio is a deterministic count over the substrate; recompute
    # rather than trusting whatever value the AI returned (the prompt now
    # instructs the model to leave the field at its default).
    _cited, _total, ratio = _compute_coverage_ratio(model_type, paths)
    existing.coverage_ratio = ratio

    excluded = _excluded_names(model_type, paths)
    modelled = _modelled_entity_labels(paths)

    # Fast lookup of existing entries by lowercased name.
    by_name: dict[str, MissingVariable] = {
        mv.name.strip().lower(): mv for mv in existing.entries
    }

    new_proposals: Iterable[_MissingVariableProposal] = result.entries
    for proposal in new_proposals:
        key = proposal.name.strip().lower()
        if key in excluded or key in modelled:
            continue  # respect prior decisions / current model state
        if key in by_name:
            mv = by_name[key]
            if mv.disposition == "open":
                mv.rationale = proposal.rationale
                mv.required_for = list(proposal.required_for)
                mv.severity = proposal.severity  # type: ignore[assignment]
                mv.confidence = proposal.confidence  # type: ignore[assignment]
            # Excluded / added_to_model rows stay untouched.
            continue
        existing.entries.append(
            MissingVariable(
                name=proposal.name,
                rationale=proposal.rationale,
                required_for=list(proposal.required_for),
                severity=proposal.severity,  # type: ignore[arg-type]
                confidence=proposal.confidence,  # type: ignore[arg-type]
            )
        )

    sha = save_report(
        existing,
        subject=f"CompletenessGate report ({model_type}): {len(existing.entries)} entries",
        root=root,
    )
    return existing, sha


# ── State transitions ───────────────────────────────────────────────────


def override_missing_variable(
    model_type: str,
    missing_var_id: str,
    rationale: str,
    *,
    root: Path | None = None,
) -> tuple[MissingVariable, str]:
    """Create an Exclusion + flip MissingVariable.disposition to ``excluded``.

    Authorship comes from the project's git identity via the standard
    ``add_exclusion`` operation; the caller does not pass an actor.
    """
    report = load_report(model_type, root=root)
    target = next((mv for mv in report.entries if mv.id == missing_var_id), None)
    if target is None:
        raise ValueError(f"no missing-variable {missing_var_id!r} in {model_type} report")
    if target.disposition == "excluded":
        return target, ""

    statement = f"Variable '{target.name}' deliberately excluded from model scope"
    exclusion, _exclusion_sha = add_exclusion(
        statement=statement,
        rationale=rationale,
        root=root,
    )
    target.disposition = "excluded"
    target.excluded_via_id = exclusion.id

    sha = save_report(
        report,
        subject=f"Override missing-variable '{target.name}'",
        root=root,
    )
    return target, sha


def dismiss_missing_variable(
    model_type: str,
    missing_var_id: str,
    *,
    root: Path | None = None,
) -> tuple[MissingVariable, str]:
    """Mark a missing-variable row as dismissed without creating an Exclusion."""
    report = load_report(model_type, root=root)
    target = next((mv for mv in report.entries if mv.id == missing_var_id), None)
    if target is None:
        raise ValueError(f"no missing-variable {missing_var_id!r} in {model_type} report")
    if target.disposition == "dismissed":
        return target, ""
    target.disposition = "dismissed"
    sha = save_report(
        report,
        subject=f"Dismiss missing-variable '{target.name}'",
        root=root,
    )
    return target, sha


def mark_added_to_model(
    model_type: str,
    missing_var_id: str,
    entity_id: str,
    *,
    root: Path | None = None,
) -> tuple[MissingVariable, str]:
    """Record that the user added an entity that resolves a missing variable."""
    report = load_report(model_type, root=root)
    target = next((mv for mv in report.entries if mv.id == missing_var_id), None)
    if target is None:
        raise ValueError(f"no missing-variable {missing_var_id!r} in {model_type} report")
    target.disposition = "added_to_model"
    target.added_entity_id = entity_id
    sha = save_report(
        report,
        subject=f"Mark missing-variable '{target.name}' as added",
        root=root,
    )
    return target, sha


# ── Gate runner ─────────────────────────────────────────────────────────


def run_completeness_gate(
    model_type: str,
    *,
    claims: list[str] | None = None,
    approver: HumanActor | None = None,
    confirm=None,
    root: Path | None = None,
) -> tuple[CompletenessReport, str]:
    """Invoke the CompletenessGate prompt and merge the result.

    Helper that wraps :func:`latris.ai.call.run_call` so server
    routes / CLI / capability walks can run the gate without
    threading the AI plumbing themselves.
    """
    from latris.ai.call import run_call
    from latris.ai.render import render as ai_render

    paths = require_project(root)
    if approver is None:
        from latris.repo import git as git_mod

        name, email = git_mod.ensure_identity(paths.root)
        approver = HumanActor(name=name, email=email)

    def _render(parsed):
        return ai_render("CompletenessGate", parsed)

    run_call(
        prompt_name="CompletenessGate",
        inputs={"model_type": model_type, "claims": list(claims or [])},
        approver=approver,
        confirm=confirm or (lambda _r, _p: True),
        render=_render,
        preview_only=False,
        root=paths.root,
    )

    report = load_report(model_type, root=root)
    return report, ""


# ── Blocking-mode error ─────────────────────────────────────────────────


class CompletenessGateBlockedError(RuntimeError):
    """Raised when the gate is blocking-mode and required gaps are open.

    Carries the offending IDs so the route layer can return a 4xx
    body the GUI can act on.
    """

    def __init__(self, model_type: str, blocking_ids: list[str]) -> None:
        super().__init__(
            f"CompletenessGate blocking — {len(blocking_ids)} required missing-variable(s) open for {model_type}"
        )
        self.model_type = model_type
        self.blocking_ids = list(blocking_ids)
