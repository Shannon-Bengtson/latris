"""The pure Markdown helpers the report and the formalism plugins share."""

from __future__ import annotations

from latris.exporters import md


def test_fmt():
    assert md.fmt(None) == "—"
    assert md.fmt(0.123456) == "0.1235"
    assert md.fmt(1234567) == "1.235e+06"
    assert md.fmt(3) == "3"
    assert md.fmt("high") == "high"


def test_esc_keeps_a_table_cell_on_one_line():
    assert md.esc("a | b\nc") == "a \\| b c"
    assert md.esc(1.5) == "1.5"


def test_table_escapes_cells_and_ends_with_a_blank_line():
    assert md.table(["A", "B"], [["x|y", "line\nbreak"]]) == [
        "| A | B |", "|---|---|", "| x\\|y | line break |", ""]
    assert md.table(["Only"], []) == ["| Only |", "|---|", ""]


def test_grounding_names_where_an_unreviewed_number_came_from():
    assert md.grounding("ai-proposed", "human-verified") == "reviewed"
    assert md.grounding("ai-proposed", None) == "AI-proposed, not yet reviewed"
    assert md.grounding("data-derived", "unverified") == "from data, not yet reviewed"
    assert md.grounding("human-elicited", None) == "elicited, not yet reviewed"
    assert md.grounding(None, None) == "entered, not yet reviewed"
    assert md.grounding("human-entered", None) == "entered, not yet reviewed"
