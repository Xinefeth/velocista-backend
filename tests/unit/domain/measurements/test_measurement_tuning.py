"""Measurements: precision model with repeated measurements (SP-07)."""

import pytest

from support.measurement_fixtures import measurement, walk_readings
from velocista.domain.measurements.tuning import tune
from velocista.domain.shared.errors import Validation


def repeated(n=5, step=0.77, bias=0.0, true_bias=0.4):
    return [
        (
            measurement(step_length_m=step, gyro_bias_dps=bias, mid=i),
            walk_readings(gyro_bias_dps=true_bias, gyro_noise_dps=0.3, seed=i),
        )
        for i in range(n)
    ]


def test_model_lowers_the_error_and_learns_the_parameters():
    out = tune(repeated(), max_attempts=40)
    assert out["final_cost"] < out["baseline_cost"] / 3
    assert out["final_params"]["gyro_bias_dps"] == pytest.approx(0.4, abs=0.1)
    assert out["final_params"]["step_length_m"] == pytest.approx(0.70, abs=0.03)
    assert out["meets_green"]


def test_model_is_checked_on_a_measurement_it_did_not_see():
    out = tune(repeated(), max_attempts=40)
    assert out["holdout"]["measurement_id"] == 4
    assert out["generalizes"] is True


def test_error_by_attempt_never_goes_up():
    out = tune(repeated(), max_attempts=30)
    best = [a["best_cost"] for a in out["attempts"]]
    assert len(best) == 30
    assert all(b <= a for a, b in zip(best, best[1:], strict=False))


def test_already_calibrated_does_not_get_worse():
    out = tune(repeated(step=0.70, bias=0.4), max_attempts=20)
    assert out["final_cost"] <= out["baseline_cost"]


def test_needs_two_measurements():
    with pytest.raises(Validation):
        tune(repeated(n=1))


def test_rejects_gps():
    m = measurement("gps")
    with pytest.raises(Validation) as e:
        tune([(m, []), (m, [])])
    assert e.value.reason == "model_gps_unsupported"
