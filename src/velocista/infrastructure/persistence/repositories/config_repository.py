"""Implementación SQLAlchemy de `ConfigRepository` (upsert por robot)."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from velocista.domain.config.entities import RobotConfig
from velocista.infrastructure.persistence.models.config import RobotConfigModel


class SqlAlchemyConfigRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, robot_id: str) -> RobotConfig | None:
        row = self._session.get(RobotConfigModel, robot_id)
        if row is None:
            return None
        return RobotConfig(mode=row.mode, line=row.line, updated_at=row.updated_at)

    def upsert(self, robot_id: str, *, column: str, value: str) -> None:
        try:
            self._session.execute(
                insert(RobotConfigModel)
                .values(robot_id=robot_id, **{column: value})
                .on_conflict_do_update(
                    index_elements=[RobotConfigModel.robot_id],
                    set_={column: value, "updated_at": func.now()},
                )
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
