"""Measurements: validation of measurements and of each incoming phone reading (EN-32)."""

from dataclasses import replace

import pytest

from support.measurement_fixtures import measurement
from velocista.domain.measurements.entities import Reading
from velocista.domain.measurements.validation import (
    reading_problem,
    validate_measurement,
)
from velocista.domain.shared.errors import Validation


def reason_of(m) -> str:
    with pytest.raises(Validation) as e:
        validate_measurement(m)
    return e.value.reason


def test_valid_measurement_passes():
    validate_measurement(measurement())


@pytest.mark.parametrize(
    "changes, reason",
    [
        ({"method": "laser"}, "measurement_method_invalid"),
        ({"source": "x"}, "measurement_source_invalid"),
        ({"mount": "pocket"}, "measurement_mount_invalid"),
        ({"method": "car", "mount": "hand"}, "measurement_mount_invalid"),
        ({"place_name": "  "}, "measurement_place_invalid"),
        ({"device_id": ""}, "measurement_device_invalid"),
        ({"tape_side_m": 0}, "measurement_tape_invalid"),
    ],
)
def test_invalid_measurement(changes, reason):
    assert reason_of(replace(measurement(), **changes)) == reason


@pytest.mark.parametrize(
    "reading, problem",
    [
        (Reading(0, 0, "motion", gyro_z_dps=1.0, accel=(0, 0, 9.8)), None),
        (Reading(0, 0, "gps", lat=-8.1, lon=-79.0, accuracy_m=5), None),
        (Reading(0, 0, "corner"), None),
        (Reading(0, 0, "wifi"), "kind_unknown"),
        (Reading(-1, 0, "corner"), "seq_or_time_invalid"),
        (Reading(0, 0, "gps", lat=-8.1, lon=-79.0), "gps_incomplete"),
        (Reading(0, 0, "gps", lat=95, lon=0, accuracy_m=5), "gps_out_of_range"),
        (Reading(0, 0, "gps", lat=0, lon=0, accuracy_m=0), "gps_accuracy_invalid"),
        (Reading(0, 0, "motion"), "motion_empty"),
        (Reading(0, 0, "motion", gyro_z_dps=float("nan")), "gyro_out_of_range"),
        (Reading(0, 0, "motion", accel=(0, 0, 500)), "accel_out_of_range"),
        (Reading(0, 0, "motion", pwm=150), "pwm_out_of_range"),
    ],
)
def test_reading_problem(reading, problem):
    assert reading_problem(reading) == problem
