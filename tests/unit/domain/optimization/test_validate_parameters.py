"""Unit: pure validation of controller parameters against the catalog definition."""

import math

import pytest

from velocista.domain.optimization.validation import validate_parameters
from velocista.domain.shared.errors import Validation

DEFINITIONS = [{"key": "kp", "min": 0, "max": 10}, {"key": "kd", "min": 0, "max": 5}]


class TestValidateParameters:
    def test_validate_when_all_in_range_returns_floats(self):
        result = validate_parameters(DEFINITIONS, {"kp": 2, "kd": 1})
        assert result == {"kp": 2.0, "kd": 1.0}
        assert all(isinstance(v, float) for v in result.values())

    @pytest.mark.parametrize("value", [0, 10])
    def test_validate_when_value_on_boundary_is_accepted(self, value):
        assert validate_parameters(DEFINITIONS, {"kp": value, "kd": 0})["kp"] == float(value)

    @pytest.mark.parametrize("value", [-0.001, 10.001])
    def test_validate_when_value_out_of_range_raises_out_of_range(self, value):
        with pytest.raises(Validation) as error:
            validate_parameters(DEFINITIONS, {"kp": value, "kd": 0})
        assert error.value.reason == "out_of_range"

    @pytest.mark.parametrize("values", [{"kp": 1}, {"kp": 1, "kd": 1, "ki": 1}, {}])
    def test_validate_when_keys_do_not_match_raises_invalid_parameters(self, values):
        with pytest.raises(Validation) as error:
            validate_parameters(DEFINITIONS, values)
        assert error.value.reason == "invalid_parameters"

    @pytest.mark.parametrize("value", [True, "1", None, math.nan, math.inf, [1]])
    def test_validate_when_value_is_not_finite_number_raises_invalid_parameter(self, value):
        with pytest.raises(Validation) as error:
            validate_parameters(DEFINITIONS, {"kp": value, "kd": 0})
        assert error.value.reason == "invalid_parameter"
