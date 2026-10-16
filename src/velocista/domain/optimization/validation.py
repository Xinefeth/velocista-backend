"""Validacion pura de parametros segun el catalogo."""

import math

from velocista.domain.shared.errors import Validation


def validate_parameters(definitions: list[dict], values: dict) -> dict[str, float]:
    expected = {p["key"] for p in definitions}
    if set(values) != expected:
        raise Validation("invalid_parameters", "Parameters must match every controller parameter")
    result = {}
    for parameter in definitions:
        key = parameter["key"]
        value = values[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise Validation("invalid_parameter", f"{key} must be a finite number")
        if not parameter["min"] <= value <= parameter["max"]:
            raise Validation("out_of_range", f"{key} is outside the controller range")
        result[key] = float(value)
    return result
