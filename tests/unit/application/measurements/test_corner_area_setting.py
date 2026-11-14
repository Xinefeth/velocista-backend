"""La tolerancia de corner_area_mismatch es configuración y llega al cálculo."""

import pytest
from pydantic import ValidationError

from velocista.application.measurements.use_cases import MeasurementsService
from velocista.domain.measurements.compute import CORNER_AREA_TOLERANCE_PCT
from velocista.infrastructure.config.settings import Settings


def test_default_and_override(monkeypatch):
    assert Settings(_env_file=None).corner_area_tolerance_pct == CORNER_AREA_TOLERANCE_PCT
    monkeypatch.setenv("CORNER_AREA_TOLERANCE_PCT", "25")
    assert Settings(_env_file=None).corner_area_tolerance_pct == 25


@pytest.mark.parametrize("value", [0, -1, 101])
def test_invalid_tolerance_is_rejected(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, corner_area_tolerance_pct=value)


def test_service_receives_the_tolerance():
    assert MeasurementsService(None, 25).corner_area_tolerance_pct == 25
    assert MeasurementsService(None).corner_area_tolerance_pct == CORNER_AREA_TOLERANCE_PCT
