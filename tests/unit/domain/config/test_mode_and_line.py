"""Unit: allowed values of operating mode and line color (English contract)."""

from velocista.domain.config.entities import Line, Mode


def test_mode_values_are_english():
    assert {m.value for m in Mode} == {"test", "competition"}


def test_line_values_are_english():
    assert {line.value for line in Line} == {"black", "white"}
