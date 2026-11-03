"""Measurements: sensor calibration before measuring (EN-35)."""

import random

import pytest

from velocista.domain.measurements.calibration import car_speed, gyro_bias, step_length
from velocista.domain.shared.errors import Validation


def still(bias=0.3, noise=0.1, n=250, seed=1):
    rng = random.Random(seed)
    return [(i * 20, bias + rng.gauss(0, noise)) for i in range(n)]


def test_gyro_bias_is_the_mean_while_still():
    c = gyro_bias(still())
    assert c.bias_dps == pytest.approx(0.3, abs=0.03)
    assert c.duration_ms >= 3000


def test_gyro_rejects_moving_phone():
    with pytest.raises(Validation) as e:
        gyro_bias(still(noise=5))
    assert e.value.reason == "calibration_phone_moved"


def test_gyro_rejects_short_calibration():
    with pytest.raises(Validation) as e:
        gyro_bias(still(n=100))
    assert e.value.reason == "calibration_too_short"


def test_step_length_average_of_three_walks():
    c = step_length([(20, 28), (20, 28), (20, 29)])
    assert c.step_length_m == pytest.approx((20 / 28 * 2 + 20 / 29) / 3)
    assert c.warnings == ("uneven_pace",)  # 0.714 vs 0.690


def test_step_length_even_pace_has_no_warning():
    assert step_length([(20, 28)] * 3).warnings == ()


def test_step_length_needs_three_walks():
    with pytest.raises(Validation):
        step_length([(20, 28), (20, 28)])


def test_step_length_out_of_range():
    with pytest.raises(Validation) as e:
        step_length([(20, 5)] * 3)
    assert e.value.reason == "calibration_step_out_of_range"


def test_car_speed_linear_fit():
    trials = [(pwm, (0.01 * pwm + 0.05) * 4, 4) for pwm in (30, 50, 70)]
    c = car_speed(trials)
    assert c.k == pytest.approx(0.01) and c.c == pytest.approx(0.05) and c.r2 == pytest.approx(1)


def test_car_speed_single_pwm_goes_through_origin():
    c = car_speed([(50, 2.0, 4), (50, 2.2, 4)])
    assert c.c == 0 and c.k == pytest.approx(0.525 / 50)
