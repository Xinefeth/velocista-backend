from sqlalchemy import func, select

from velocista.domain.shared.errors import NotFound
from velocista.infrastructure.persistence.models.builder import RobotModel, VersionModel
from velocista.infrastructure.persistence.models.optimization import ControllerModel, SetupModel
from velocista.infrastructure.persistence.repositories.rules_repository import as_dict


class SqlAlchemyOptimizationRepository:
    def __init__(self, session):
        self.session = session

    def list_controllers(self):
        return [
            as_dict(row)
            for row in self.session.scalars(select(ControllerModel).order_by(ControllerModel.id))
        ]

    def get_controller(self, controller_id):
        row = self.session.get(ControllerModel, controller_id)
        return as_dict(row) if row else None

    def version_robot(self, version_id):
        return self.session.scalar(
            select(VersionModel.robot_id).where(VersionModel.id == version_id)
        )

    def list_setups(self, robot_id, limit, offset, version_id=None):
        if self.session.get(RobotModel, robot_id) is None:
            raise NotFound("robot_not_found", "Robot does not exist")
        query = (
            select(SetupModel)
            .join(VersionModel, VersionModel.id == SetupModel.version_id)
            .where(VersionModel.robot_id == robot_id, SetupModel.archived.is_(False))
        )
        if version_id is not None:
            query = query.where(SetupModel.version_id == version_id)
        total = self.session.scalar(select(func.count()).select_from(query.subquery()))
        return {
            "items": [
                {**as_dict(row), "robot_id": robot_id}
                for row in self.session.scalars(
                    query.order_by(SetupModel.id.desc()).limit(limit).offset(offset)
                )
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def create_setup(self, robot_id, values, controller):
        row = SetupModel(**values, controller_snapshot=controller)
        self.session.add(row)
        self.session.flush()
        result = {**as_dict(row), "robot_id": robot_id}
        self.session.commit()
        return result

    def get_setup(self, setup_id):
        row = self.session.get(SetupModel, setup_id)
        return {**as_dict(row), "robot_id": self.version_robot(row.version_id)} if row else None

    def archive_setup(self, setup_id):
        self.session.get(SetupModel, setup_id).archived = True
        self.session.commit()
