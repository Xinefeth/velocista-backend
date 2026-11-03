"""Measurements: step counting, gyroscope heading and closure corrections (EN-35)."""

from math import pi, radians

import pytest

from support.measurement_fixtures import walk_readings
from velocista.domain.measurements.entities import XY, Calibration, Reading
from velocista.domain.measurements.odometry import (
    Segment,
    build_path,
    car_segments,
    correct_heading_drift,
    detect_steps,
    distribute_closure,
    heading_series,
    motion_readings,
)


def test_detect_steps_counts_one_per_stride():
    motion = motion_readings(walk_readings())
    # 32 m a 0.7 m por paso ≈ 46 pasos (±1 por el redondeo de cada lado)
    assert len(detect_steps(motion, Calibration())) == pytest.approx(46, abs=1)


def test_detect_steps_ignores_noise_while_standing():
    still = [Reading(i, i * 20, "motion", gyro_z_dps=0, accel=(0, 0, 9.81)) for i in range(500)]
    assert detect_steps(still, Calibration()) == []


def test_detect_steps_prefers_phone_flags():
    flags = [Reading(i, i * 500, "motion", step=i % 2 == 0) for i in range(10)]
    assert detect_steps(flags, Calibration()) == [0, 1000, 2000, 3000, 4000]


def test_heading_integrates_and_removes_bias():
    # 2 s girando a 45 °/s con un sesgo de 1 °/s
    motion = [Reading(i, i * 20, "motion", gyro_z_dps=46.0) for i in range(101)]
    assert heading_series(motion, 1.0)[-1][1] == pytest.approx(radians(90))
    assert heading_series(motion, 0.0)[-1][1] == pytest.approx(radians(92))


def test_build_path_square():
    segs = [Segment(i, 1.0, h) for i, h in enumerate([0, pi / 2, pi, 3 * pi / 2])]
    end = build_path(segs)[-1]
    assert end.x == pytest.approx(0, abs=1e-9) and end.y == pytest.approx(0, abs=1e-9)


def test_heading_drift_is_removed_when_total_turn_is_near_360():
    segs = [Segment(t, 1.0, 0.0) for t in range(0, 1000, 100)]
    fixed, excess = correct_heading_drift(segs, 2 * pi + radians(10), 0, 1000)
    assert excess == pytest.approx(radians(10))
    assert fixed[-1].heading_rad == pytest.approx(-radians(10) * 0.9)


def test_heading_drift_is_skipped_when_person_did_not_face_start():
    segs = [Segment(0, 1.0, 0.0)]
    fixed, excess = correct_heading_drift(segs, radians(270), 0, 1000)
    assert excess is None and fixed == segs


def test_distribute_closure_ends_at_start_and_keeps_start():
    pts = [XY(0, 0), XY(10, 0), XY(10, 6), XY(0, 6), XY(0.6, -0.4)]
    fixed = distribute_closure(pts)
    assert fixed[0] == XY(0, 0)
    assert fixed[-1].x == pytest.approx(0) and fixed[-1].y == pytest.approx(0)


def test_car_segments_use_speed_model():
    cal = Calibration(speed_k=0.01, speed_c=0.1)
    motion = [Reading(i, i * 100, "motion", gyro_z_dps=0, pwm=50) for i in range(11)]
    total = sum(s.length_m for s in car_segments(motion, cal))
    assert total == pytest.approx((0.01 * 50 + 0.1) * 1.0)


def test_heading_is_exact_with_irregular_intervals():
    # el celular manda giro = cambio de orientación ÷ intervalo, con intervalos de 1 a 98 ms
    times, t = [0], 0
    for i in range(400):
        t += [1, 16, 33, 98][i % 4]
        times.append(t)
    yaw = [360 * k / (len(times) - 1) for k in range(len(times))]  # una vuelta completa
    motion = [Reading(0, times[0], "motion", gyro_z_dps=0.0)] + [
        Reading(
            i,
            times[i],
            "motion",
            gyro_z_dps=(yaw[i] - yaw[i - 1]) / ((times[i] - times[i - 1]) / 1000),
        )
        for i in range(1, len(times))
    ]
    assert heading_series(motion, 0.0)[-1][1] == pytest.approx(2 * pi)
