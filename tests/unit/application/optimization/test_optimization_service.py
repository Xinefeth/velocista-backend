"""Unit: optimization use cases with an in-memory double of the repository port."""

import pytest

from velocista.application.optimization.use_cases import OptimizationService
from velocista.domain.shared.errors import NotFound, Validation

CONTROLLER = {"id": "pid", "parameters": [{"key": "kp", "min": 0, "max": 10}], "presets": {}}


class FakeRepository:
    def __init__(self):
        self.created = []
        self.archived = []
        self.setups = {1: {"id": 1, "robot_id": "r1", "archived": False}}

    def list_controllers(self):
        return [CONTROLLER]

    def get_controller(self, controller_id):
        return CONTROLLER if controller_id == "pid" else None

    def version_robot(self, version_id):
        return "r1" if version_id == 10 else None

    def list_setups(self, robot_id, limit, offset, version_id=None):
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    def create_setup(self, robot_id, values, controller):
        self.created.append(values)
        return {"id": 2, **values}

    def get_setup(self, setup_id):
        return self.setups.get(setup_id)

    def archive_setup(self, setup_id):
        self.archived.append(setup_id)


@pytest.fixture
def service():
    return OptimizationService(FakeRepository())


class TestCreateSetup:
    def test_create_when_valid_normalizes_parameters_to_float(self, service):
        values = {"version_id": 10, "name": "A", "controller_id": "pid", "parameters": {"kp": 3}}
        assert service.create_setup("r1", values)["parameters"] == {"kp": 3.0}

    def test_create_when_version_is_from_another_robot_raises_not_found(self, service):
        values = {"version_id": 10, "name": "A", "controller_id": "pid", "parameters": {"kp": 1}}
        with pytest.raises(NotFound) as error:
            service.create_setup("other", values)
        assert error.value.reason == "version_not_found"

    def test_create_when_controller_unknown_raises_not_found(self, service):
        values = {"version_id": 10, "name": "A", "controller_id": "x", "parameters": {"kp": 1}}
        with pytest.raises(NotFound) as error:
            service.create_setup("r1", values)
        assert error.value.reason == "controller_not_found"

    def test_create_when_parameter_out_of_range_raises_validation(self, service):
        values = {"version_id": 10, "name": "A", "controller_id": "pid", "parameters": {"kp": 99}}
        with pytest.raises(Validation):
            service.create_setup("r1", values)


class TestGetAndArchive:
    def test_get_when_missing_raises_setup_not_found(self, service):
        with pytest.raises(NotFound) as error:
            service.get_setup(99)
        assert error.value.reason == "setup_not_found"

    def test_archive_when_exists_delegates_to_repository(self, service):
        service.archive_setup(1)
        assert service.repository.archived == [1]

    def test_archive_when_missing_raises_and_does_not_archive(self, service):
        with pytest.raises(NotFound):
            service.archive_setup(99)
        assert service.repository.archived == []
