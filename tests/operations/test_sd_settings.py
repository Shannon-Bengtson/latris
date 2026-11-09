"""The SD clock is stored with the model and checked against the flows; SD has an outcome."""

from __future__ import annotations

import pytest

from latris.operations import analysis_results as ar
from latris.operations import sd as sd_ops
from latris.operations.interpret import _outcome_ids
from latris.operations.view_roles import set_role
from latris.repo.project import require_project

pytest.importorskip("scipy")


def test_a_monthly_model_on_a_yearly_clock_warns(sd_bathtub_root):
    root = sd_bathtub_root
    # The bathtub's flows are per year, so the default (years) clock is fine.
    assert sd_ops.notes(root=root) == []
    sd_ops.set_equation("Inflow", "inflow_rate", "liter/month", root=root)
    sd_ops.set_constant("Inflow Rate", 5, "liter/month", root=root)
    sd_ops.set_equation("Outflow", "water * drain_rate", "liter/month", root=root)
    sd_ops.set_constant("Drain Rate", 0.1, "1/month", root=root)
    (note,) = sd_ops.notes(root=root)
    assert "Flows are per month" in note and "clock runs in years" in note and "--time-units month" in note
    result = sd_ops.simulate(final_time=36, root=root)
    assert note in result.warnings and result.times[-1] == 36  # 36 *years*, as the note warns

    sd_ops.set_settings(time_units="month", final_time=36, root=root)
    assert sd_ops.notes(root=root) == []
    monthly = sd_ops.simulate(root=root)
    assert monthly.time_units == "month" and monthly.times[-1] == 36 and not monthly.warnings
    # 36 months of drain at 10%/month vs 36 years: very different ends.
    assert monthly.series[next(i for i, r in monthly.roles.items() if r == "stock")][-1] != pytest.approx(
        result.series[next(i for i, r in result.roles.items() if r == "stock")][-1]
    )


def test_settings_validate_and_age_old_results(sd_bathtub_root):
    root = sd_bathtub_root
    with pytest.raises(ValueError, match="at least one"):
        sd_ops.set_settings(root=root)
    with pytest.raises(ValueError, match="not a time"):
        sd_ops.set_settings(time_units="liter", root=root)
    sd_ops.record_simulation(sd_ops.simulate(final_time=5, root=root), root=root)
    assert not ar.report_results(root=root)[0].stale
    sd_ops.set_settings(dt=0.1, root=root)
    assert ar.report_results(root=root)[0].stale
    assert sd_ops.build_settings(base=sd_ops.get_settings(root=root), dt=0.5).dt == 0.5  # a run's option wins


def test_sd_outcome_is_kept_with_the_settings(sd_bathtub_root):
    root = sd_bathtub_root
    target_id, _ = set_role("Water", "sd", "outcome", root=root)
    assert _outcome_ids(require_project(root), "sd") == {target_id}
    roles = {e.target_id: e.value for e in sd_ops.get_roles(root=root).entries}
    assert roles[target_id] == "stock"  # still a stock
