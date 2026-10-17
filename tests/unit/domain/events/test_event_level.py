"""Unit: event levels."""

from velocista.domain.events.entities import EventLevel


def test_event_levels_are_info_warning_error():
    assert [level.value for level in EventLevel] == ["info", "warning", "error"]
