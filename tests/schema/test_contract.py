"""Contract schema: inputs (a value with units, or a state) and outputs (value, series, distribution)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from latris.repo.yaml_io import dump_model, load_model
from latris.schema.contract import Contract, ContractInput, ContractOutput


def test_input_rules():
    assert ContractInput(name="flow_depth", target_id="n", units="m").kind == "value"
    for bad in ("Flow depth", "2fast", "flow-depth", ""):
        with pytest.raises(ValidationError, match="not a valid name"):
            ContractInput(name=bad, target_id="n", units="m")
    with pytest.raises(ValidationError, match="needs units"):
        ContractInput(name="x", target_id="n")
    with pytest.raises(ValidationError, match="minimum below its maximum"):
        ContractInput(name="x", target_id="n", units="m", valid_min=3, valid_max=1)
    with pytest.raises(ValidationError, match="can't be text"):
        ContractInput(name="x", target_id="n", units="m", default="deep")
    with pytest.raises(ValidationError, match="never be used"):
        ContractInput(name="x", target_id="n", units="m", default=1, required=True)
    state = ContractInput(name="rain", target_id="n", kind="state", mode="set", default="yes")
    assert state.units is None and state.mode == "set"
    with pytest.raises(ValidationError, match="no units or range"):
        ContractInput(name="rain", target_id="n", kind="state", units="m")
    with pytest.raises(ValidationError, match="the state's name"):
        ContractInput(name="rain", target_id="n", kind="state", default=1.0)


def test_output_rules():
    assert ContractOutput(name="peak", target_id="n", units="m", metric="peak").kind == "value"
    with pytest.raises(ValidationError, match="its kind is 'value'"):
        ContractOutput(name="run", target_id="n", kind="series", units="m", metric="peak")
    with pytest.raises(ValidationError, match="no units"):
        ContractOutput(name="p", target_id="n", kind="distribution", units="m")


def test_contract_rules_and_round_trip(tmp_path: Path):
    a = ContractInput(name="depth", target_id="n1", units="m", valid_min=0.2, valid_max=3, description="stage")
    with pytest.raises(ValidationError, match="input name"):
        Contract(model_type="sd", inputs=[a, ContractInput(name="depth", target_id="n2", units="m")])
    with pytest.raises(ValidationError, match="one input only"):
        Contract(model_type="sd", inputs=[a, ContractInput(name="depth_again", target_id="n1", units="cm")])
    # One factor can be several outputs, under different names.
    c = Contract(model_type="sd", description="Channel capacity", inputs=[a], outputs=[
        ContractOutput(name="load", target_id="s", kind="series", units="tonne"),
        ContractOutput(name="peak_load", target_id="s", units="tonne", metric="peak"),
    ])
    with pytest.raises(ValidationError, match="output name"):
        Contract(model_type="sd", outputs=[c.outputs[0], c.outputs[0]])
    dump_model(c, tmp_path / "c.yaml")
    assert load_model(Contract, tmp_path / "c.yaml") == c
