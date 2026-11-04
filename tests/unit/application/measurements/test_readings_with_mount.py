"""EN-32 criterion 2: the mount of the readings comes from one read of the measurement."""

from dataclasses import dataclass, field

import pytest

from velocista.application.measurements.use_cases import MeasurementsService
from velocista.domain.shared.errors import NotFound


@dataclass
class Measurement:
    id: int
    mount: str
    status: str = "recording"
    reading_count: int = 0


@dataclass
class CountingRepository:
    measurements: dict
    readings: list = field(default_factory=lambda: ["r1", "r2", "r3"])
    calls: list = field(default_factory=list)

    def get_measurement(self, measurement_id):
        self.calls.append("get_measurement")
        return self.measurements.get(measurement_id)

    def get_readings(self, measurement_id):
        self.calls.append("get_readings")
        return self.readings


def test_mount_and_readings_come_with_one_read_of_each():
    repo = CountingRepository({1: Measurement(1, "robot")})
    mount, readings = MeasurementsService(repo).readings_with_mount(1)
    assert mount == "robot"
    assert readings == ["r1", "r2", "r3"]
    assert repo.calls == ["get_measurement", "get_readings"]  # not one query per reading


def test_unknown_measurement_is_not_found():
    repo = CountingRepository({})
    with pytest.raises(NotFound):
        MeasurementsService(repo).readings_with_mount(7)
    assert repo.calls == ["get_measurement"]
