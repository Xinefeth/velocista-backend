from velocista.application.optimization.ports import OptimizationRepository
from velocista.domain.optimization.validation import validate_parameters
from velocista.domain.shared.errors import NotFound


class OptimizationService:
    def __init__(self, repository: OptimizationRepository):
        self.repository = repository

    def list_controllers(self):
        return self.repository.list_controllers()

    def list_setups(self, robot_id, limit, offset, version_id=None):
        return self.repository.list_setups(robot_id, limit, offset, version_id)

    def create_setup(self, robot_id, values):
        if self.repository.version_robot(values["version_id"]) != robot_id:
            raise NotFound("version_not_found", "Version does not belong to this robot")
        controller = self.repository.get_controller(values["controller_id"])
        if controller is None:
            raise NotFound("controller_not_found", "Controller does not exist")
        values = {
            **values,
            "parameters": validate_parameters(controller["parameters"], values["parameters"]),
        }
        return self.repository.create_setup(robot_id, values, controller)

    def get_setup(self, setup_id):
        setup = self.repository.get_setup(setup_id)
        if setup is None:
            raise NotFound("setup_not_found", "Setup does not exist")
        return setup

    def archive_setup(self, setup_id):
        self.get_setup(setup_id)
        self.repository.archive_setup(setup_id)
