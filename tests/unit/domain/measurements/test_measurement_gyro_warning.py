"""Aviso gyro_calibration_suspect: el giroscopio real no coincide con el calibrado."""

import pytest

from support.measurement_fixtures import RECT_10x6, measurement, scaled, walk_readings
from velocista.domain.measurements.compute import compute_result

FIELD = scaled(RECT_10x6, 9)  # 90 × 54 m


def run(real_bias, calibrated=0.4, **walk):
    readings = walk_readings(FIELD, gyro_bias_dps=real_bias, gyro_noise_dps=0.3, seed=1, **walk)
    return compute_result(measurement(gyro_bias_dps=calibrated), readings)


@pytest.mark.parametrize("face_start", [True, False])
def test_badly_calibrated_gyro_is_flagged(face_start):
    r = run(real_bias=1.5, face_start=face_start)  # real 1,5 °/s contra 0,4 calibrado
    assert "end_heading_unknown" in r.warnings
    assert "gyro_calibration_suspect" in r.warnings
    assert abs(r.turn_total_deg - 360) > 100


def test_well_calibrated_walk_has_neither_warning():
    r = run(real_bias=0.4)
    assert "end_heading_unknown" not in r.warnings
    assert "gyro_calibration_suspect" not in r.warnings


def test_not_facing_the_start_is_not_blamed_on_the_gyro():
    r = run(real_bias=0.4, face_start=False)  # giro de ~270°: faltó orientarse, no calibrar
    assert "end_heading_unknown" in r.warnings
    assert "gyro_calibration_suspect" not in r.warnings


def test_the_warning_only_informs():
    bad = run(real_bias=1.5)
    again = run(real_bias=1.5)
    assert bad.perimeter_m == again.perimeter_m and bad.area_m2 == again.area_m2
    assert bad.heading_drift_deg is None  # sin corregir, igual que con end_heading_unknown solo
