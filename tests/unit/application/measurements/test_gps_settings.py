"""CU-4: the GPS analysis limits are configuration, not constants in the code."""

import pytest
from pydantic import ValidationError

from velocista.infrastructure.config.settings import Settings


def build(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_defaults():
    cfg = build().gps_config()
    assert cfg.target_pct == 10 and cfg.min_trials == 5
    assert cfg.accuracy_thresholds_m == (3, 5, 10, 20)
    assert cfg.wait_seconds == (5, 10, 20) and cfg.distance_bands_m == (5, 20, 50)


def test_can_be_changed_from_the_environment(monkeypatch):
    monkeypatch.setenv("GPS_TARGET_PCT", "5")
    monkeypatch.setenv("GPS_MIN_TRIALS", "8")
    monkeypatch.setenv("GPS_WAIT_SECONDS", "3, 6.5,12")
    cfg = build().gps_config()
    assert cfg.target_pct == 5 and cfg.min_trials == 8
    assert cfg.wait_seconds == (3, 6.5, 12)


@pytest.mark.parametrize(
    "kw",
    [
        {"gps_target_pct": 0},
        {"gps_min_trials": 0},
        {"gps_wait_seconds": "10,5"},
        {"gps_accuracy_thresholds_m": ""},
        {"gps_distance_bands_m": "0,5"},
    ],
)
def test_invalid_values_are_rejected(kw):
    with pytest.raises(ValidationError):
        build(**kw)
