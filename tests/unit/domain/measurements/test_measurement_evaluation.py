"""Measurements: evaluation of the precision model against the algorithm alone (SP-07)."""

import pytest

from support.measurement_fixtures import measurement, walk_readings
from velocista.domain.measurements.evaluation import (
    IMPROVES_GREEN,
    NO_IMPROVEMENT,
    evaluate,
)
from velocista.domain.shared.errors import Validation


def repeated(n=5, step=0.77, bias=0.0, true_bias=0.4):
    return [
        (
            measurement(step_length_m=step, gyro_bias_dps=bias, mid=i),
            walk_readings(gyro_bias_dps=true_bias, gyro_noise_dps=0.3, seed=i),
        )
        for i in range(n)
    ]


@pytest.fixture(scope="module")
def miscalibrated():
    # paso 0.77 en vez de 0.70 y giroscopio sin calibrar (sesgo real 0.4 °/s)
    return evaluate(repeated(), max_attempts=40)


def test_baseline_reports_closure_error_in_metres_and_percent(miscalibrated):
    base = miscalibrated["baseline"]
    assert base["mean_closure_error_m"] > 0
    assert base["mean_closure_error_pct"] > 3
    assert base["quality"] in {"yellow", "red"}


def test_model_lowers_the_closure_error_below_green(miscalibrated):
    base = miscalibrated["baseline"]["mean_closure_error_pct"]
    model = miscalibrated["model"]["mean_closure_error_pct"]
    assert model < base
    assert model < miscalibrated["green_limit_pct"] == 3.0
    assert miscalibrated["improvement_pct_points"] == pytest.approx(base - model)
    assert miscalibrated["verdict"] == IMPROVES_GREEN
    assert miscalibrated["meets_green"] is True


def test_model_also_lowers_the_error_against_the_plan(miscalibrated):
    base = miscalibrated["baseline"]["mean_abs_perimeter_error_pct"]
    model = miscalibrated["model"]["mean_abs_perimeter_error_pct"]
    assert model < base


def test_curve_starts_at_the_baseline_and_never_goes_up(miscalibrated):
    curve = miscalibrated["curve"]
    assert len(curve) == 41
    assert curve[0]["attempt"] == 0
    assert curve[0]["with_model_pct"] == curve[0]["without_model_pct"]
    assert all(p["without_model_pct"] == curve[0]["without_model_pct"] for p in curve)
    assert curve[-1]["with_model_pct"] < curve[0]["with_model_pct"]


def test_table_counts_train_and_holdout_measurements(miscalibrated):
    rows = miscalibrated["measurements"]
    assert miscalibrated["measurement_count"] == 5
    assert miscalibrated["train_count"] == 4
    assert [r["role"] for r in rows] == ["train"] * 4 + ["holdout"]
    assert miscalibrated["holdout_measurement_id"] == 4
    holdout = rows[-1]
    assert holdout["after"]["closure_error_pct"] < holdout["before"]["closure_error_pct"]
    assert miscalibrated["generalizes"] is True


def test_well_calibrated_phone_is_declared_without_improvement():
    out = evaluate(repeated(step=0.70, bias=0.4), max_attempts=10)
    assert out["model"]["mean_closure_error_pct"] <= out["baseline"]["mean_closure_error_pct"]
    if not out["improved"]:
        assert out["verdict"] == NO_IMPROVEMENT


def test_two_measurements_have_no_holdout():
    out = evaluate(repeated(n=2), max_attempts=10)
    assert out["holdout_measurement_id"] is None
    assert out["train_count"] == 2
    assert out["generalizes"] is None


def test_needs_two_measurements():
    with pytest.raises(Validation) as e:
        evaluate(repeated(n=1))
    assert e.value.reason == "model_few_measurements"
