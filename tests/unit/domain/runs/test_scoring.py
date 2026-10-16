import pytest

from velocista.domain.optimization.validation import validate_parameters
from velocista.domain.runs.scoring import best_lap, calculate_j
from velocista.domain.shared.errors import Validation


def test_scoring_and_best_lap():
    assert calculate_j(10, 0.5, True) == 11
    assert calculate_j(None, 0.5, False) == 120
    laps = [
        {"number": 1, "time_s": 9, "accumulated_error": 2, "finished": True},
        {"number": 2, "time_s": 10, "accumulated_error": 0.5, "finished": True},
    ]
    assert best_lap(laps)["number"] == 2
    assert best_lap([{**laps[0], "finished": False}])["number"] == 1


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_scoring_rejects_invalid_measurements(value):
    with pytest.raises(ValueError):
        calculate_j(value, 0.5, True)


@pytest.mark.parametrize(
    "values", [{}, {"kp": True}, {"kp": 11}, {"kp": float("nan")}, {"kp": 1, "unknown": 2}]
)
def test_controller_parameter_validation(values):
    with pytest.raises(Validation):
        validate_parameters([{"key": "kp", "min": 0, "max": 10}], values)
