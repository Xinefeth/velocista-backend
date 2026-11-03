"""Measurements: full calculation from readings to perimeter, area and closure (EN-34).

Each test walks a known shape with simulated phone readings and checks the error stays small.
"""

import pytest

from support.measurement_fixtures import (
    L_SHAPE,
    RECT_10x6,
    gps_walk_readings,
    measurement,
    scaled,
    walk_readings,
)
from velocista.domain.measurements.compute import compute_result
from velocista.domain.shared.errors import Validation


def test_calibrated_steps_measure_the_rectangle_within_3_percent():
    r = compute_result(measurement(), walk_readings(gyro_noise_dps=0.3))
    assert r.quality == "green"
    assert r.corners == 3
    assert abs(r.perimeter_error_pct) < 3
    assert abs(r.area_error_pct) < 3
    assert r.reference_area_m2 == pytest.approx(60)


def test_uncalibrated_gyro_bias_shows_as_closure_error():
    r = compute_result(measurement(), walk_readings(gyro_bias_dps=0.5, gyro_noise_dps=0.3))
    assert r.closure_error_pct > 3
    assert r.heading_drift_deg == pytest.approx(15, abs=3)  # 0.5 °/s · ~30 s
    # la corrección de giro y cierre deja el perímetro bien igual
    assert abs(r.perimeter_error_pct) < 3


def test_gyro_calibration_removes_closure_error():
    readings = walk_readings(gyro_bias_dps=0.5, gyro_noise_dps=0.3)
    r = compute_result(measurement(gyro_bias_dps=0.5), readings)
    assert r.closure_error_pct < 1


def test_no_final_turn_warns_and_still_closes():
    r = compute_result(measurement(), walk_readings(gyro_bias_dps=0.5, face_start=False))
    assert "end_heading_unknown" in r.warnings
    assert r.heading_drift_deg is None
    assert r.corrected_path[-1].x == pytest.approx(0, abs=1e-6)


def test_tape_side_fixes_wrong_step_length():
    readings = walk_readings()
    wrong = compute_result(measurement(step_length_m=0.77), readings)
    fixed = compute_result(measurement(step_length_m=0.77, tape_side_m=10), readings)
    assert wrong.perimeter_error_pct > 8
    assert abs(fixed.perimeter_error_pct) < abs(wrong.perimeter_error_pct) / 2
    # paso real 0.70 / calibrado 0.77; ±1 paso de redondeo en el primer lado (≈ 7 % en 10 m)
    assert fixed.scale_factor == pytest.approx(0.70 / 0.77, abs=0.07)


def test_tape_side_without_corners_warns():
    r = compute_result(measurement(tape_side_m=10), walk_readings(mark_corners=False))
    assert "scale_needs_corner" in r.warnings and r.scale_factor is None


def test_concave_l_shape():
    r = compute_result(measurement(reference=L_SHAPE), walk_readings(L_SHAPE, gyro_noise_dps=0.3))
    assert r.concave and not r.self_crossing
    assert abs(r.area_error_pct) < 6


def test_reference_scale_1_to_n():
    small = scaled(RECT_10x6, 1 / 500)  # plano dibujado a 1:500
    m = measurement(reference=small)
    m = m.__class__(**{**m.__dict__, "reference": m.reference.__class__(small, 500)})
    r = compute_result(m, walk_readings())
    assert r.reference_perimeter_m == pytest.approx(32)


def test_gps_large_field_is_accurate():
    big = scaled(RECT_10x6, 8)  # 80 x 48 m
    r = compute_result(measurement("gps", reference=big), gps_walk_readings(big, sigma=3))
    assert abs(r.perimeter_error_pct) < 5
    assert "gps_space_too_small" not in r.warnings


def test_gps_small_room_warns_to_use_steps():
    r = compute_result(measurement("gps"), gps_walk_readings(RECT_10x6, sigma=3))
    assert "gps_space_too_small" in r.warnings


def test_steps_without_step_length_use_average_step_and_warn():
    # el simulador camina con paso 0.70, igual al paso promedio por defecto
    r = compute_result(measurement(step_length_m=None), walk_readings())
    assert "step_not_calibrated" in r.warnings
    assert abs(r.perimeter_error_pct) < 3


def test_car_without_speed_calibration_is_rejected():
    with pytest.raises(Validation) as e:
        compute_result(measurement("car", step_length_m=None), walk_readings())
    assert e.value.reason == "measurement_not_calibrated"


def test_too_few_readings_is_rejected():
    with pytest.raises(Validation) as e:
        compute_result(measurement(), walk_readings()[:60])
    assert e.value.reason == "measurement_too_short"
