"""Implementación SQLAlchemy de `BuilderRepository`.

Porte fiel de la lógica del service anterior (armador): reglas de versión, snapshots de pieza,
orden estable de bloqueos y guarda de actividad. Mantiene el comportamiento 1:1.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from velocista.application.builder.dto import VersionCreateInput
from velocista.application.builder.ports import ComponentProvider, RobotActivity
from velocista.domain.builder.entities import Robot, RobotType, Slot, version_label
from velocista.domain.shared.errors import Conflict, NotFound, Validation
from velocista.infrastructure.persistence.models.builder import (
    RobotModel,
    SlotModel,
    VersionModel,
    VersionPartModel,
)


def _to_robot(row: RobotModel) -> Robot:
    return Robot(
        id=row.id,
        name=row.name,
        short_code=row.short_code,
        type=RobotType(row.type),
        firmware=row.firmware,
        current_version_id=row.current_version_id,
        archived=row.archived,
    )


def _to_slot(row: SlotModel) -> Slot:
    return Slot(
        id=row.id,
        type_id=row.type_id,
        name=row.name,
        required=row.required,
        quantity_editable=row.quantity_editable,
        rules_dependent=row.rules_dependent,
    )


class SqlAlchemyBuilderRepository:
    def __init__(
        self, session: Session, components: ComponentProvider, activity: RobotActivity
    ) -> None:
        self._session = session
        self._components = components
        self._activity = activity

    # ---------- Robots ----------

    def create_robot(self, *, name: str, short_code: str, type: str, firmware: str | None) -> Robot:
        robot = RobotModel(
            id=f"r_{uuid4().hex}",
            name=name,
            short_code=short_code,
            type=type,
            firmware=firmware,
            current_version_id=None,
            archived=False,
        )
        try:
            self._session.add(robot)
            self._session.flush()
            result = _to_robot(robot)
            self._session.commit()
            return result
        except Exception:
            self._session.rollback()
            raise

    def list_robots(self, *, limit: int, offset: int) -> dict[str, Any]:
        stmt = select(RobotModel).where(RobotModel.archived.is_(False))
        total = self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = self._session.scalars(
            stmt.order_by(RobotModel.short_code, RobotModel.id).limit(limit).offset(offset)
        ).all()
        return {
            "items": [_to_robot(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_robot(self, robot_id: str) -> Robot:
        robot = self._session.get(RobotModel, robot_id)
        if robot is None:
            raise NotFound("robot_not_found", "El robot no existe")
        return _to_robot(robot)

    def _robot_for_write(self, robot_id: str) -> RobotModel:
        robot = self._session.get(RobotModel, robot_id, with_for_update=True)
        if robot is None:
            raise NotFound("robot_not_found", "El robot no existe")
        if robot.archived:
            raise Conflict("robot_archived", "El robot está archivado")
        return robot

    def _ensure_stopped(self, robot_id: str) -> None:
        if self._activity.is_running(robot_id):
            raise Conflict(
                "run_in_progress", "Detén y cierra la corrida antes de modificar el armado"
            )

    def update_robot(self, robot_id: str, changes: dict[str, Any]) -> Robot:
        try:
            robot = self._robot_for_write(robot_id)
            for key, value in changes.items():
                setattr(robot, key, value)
            self._session.flush()
            result = _to_robot(robot)
            self._session.commit()
            return result
        except Exception:
            self._session.rollback()
            raise

    def archive_robot(self, robot_id: str) -> None:
        try:
            robot = self._session.get(RobotModel, robot_id, with_for_update=True)
            if robot is None:
                raise NotFound("robot_not_found", "El robot no existe")
            if not robot.archived:
                self._ensure_stopped(robot_id)
                robot.archived = True
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    # ---------- Ranuras y versiones ----------

    def list_slots(self) -> list[Slot]:
        return [
            _to_slot(s) for s in self._session.scalars(select(SlotModel).order_by(SlotModel.id))
        ]

    def _serialize_versions(self, versions: list[VersionModel]) -> list[dict[str, Any]]:
        parts: dict[int, dict[str, Any]] = {v.id: {} for v in versions}
        if versions:
            rows = self._session.scalars(
                select(VersionPartModel)
                .where(VersionPartModel.version_id.in_(parts))
                .order_by(VersionPartModel.slot_id)
            )
            for part in rows:
                parts[part.version_id][part.slot_id] = {
                    "component_id": part.component_id,
                    "quantity": part.quantity,
                    "component_snapshot": part.component_snapshot,
                }
        return [
            {
                "id": v.id,
                "robot_id": v.robot_id,
                "label": version_label(v.ordinal),
                "date": v.date,
                "note": v.note,
                "status": v.status,
                "parts": parts[v.id],
            }
            for v in versions
        ]

    def list_versions(self, robot_id: str, *, limit: int, offset: int) -> dict[str, Any]:
        self.get_robot(robot_id)  # 404 si no existe
        stmt = select(VersionModel).where(VersionModel.robot_id == robot_id)
        total = self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        versions = self._session.scalars(
            stmt.order_by(VersionModel.ordinal).limit(limit).offset(offset)
        ).all()
        return {
            "items": self._serialize_versions(versions),
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_version(self, robot_id: str, version_id: int) -> dict[str, Any]:
        version = self._session.scalar(
            select(VersionModel).where(
                VersionModel.id == version_id, VersionModel.robot_id == robot_id
            )
        )
        if version is None:
            raise NotFound("version_not_found", "La versión no existe para ese robot")
        return self._serialize_versions([version])[0]

    def create_version(self, robot_id: str, data: VersionCreateInput) -> dict[str, Any]:
        try:
            robot = self._robot_for_write(robot_id)
            self._ensure_stopped(robot_id)
            if robot.current_version_id != data.base_version_id:
                raise Conflict("version_stale", "Consulta la última versión antes de guardar")
            slots = {s.id: s for s in self.list_slots()}
            if not slots:
                raise Validation("no_slots", "Carga las semillas de ranuras primero")
            missing = {s.id for s in slots.values() if s.required} - data.parts.keys()
            if data.status == "current" and missing:
                raise Validation("required_slots_missing", "Faltan: " + ", ".join(sorted(missing)))
            prepared: list[tuple[str, Any, dict[str, Any]]] = []
            # Orden estable de bloqueos para tomar fichas coherentes frente a edición/archivado.
            for slot_id, part in sorted(data.parts.items(), key=lambda kv: kv[1].component_id):
                slot = slots.get(slot_id)
                if slot is None:
                    raise Validation("unknown_slot", f"Ranura desconocida: {slot_id}")
                card = self._components.snapshot_for_version(part.component_id)
                if card["type_id"] != slot.type_id:
                    raise Validation("incompatible_type", f"Tipo incompatible en {slot_id}")
                if not slot.quantity_editable and part.quantity != 1:
                    raise Validation("invalid_quantity", f"La cantidad de {slot_id} debe ser 1")
                snapshot = {k: v for k, v in card.items() if k not in {"stock", "archived"}}
                for field in ("price", "mass_g", "current_a"):
                    if snapshot[field] is not None:
                        snapshot[field] = float(snapshot[field])
                prepared.append((slot_id, part, snapshot))
            ordinal = self._session.scalar(
                select(func.max(VersionModel.ordinal)).where(VersionModel.robot_id == robot_id)
            )
            if data.status == "current":
                self._session.execute(
                    update(VersionModel)
                    .where(VersionModel.robot_id == robot_id, VersionModel.status == "current")
                    .values(status="previous")
                )
            version = VersionModel(
                robot_id=robot_id,
                ordinal=0 if ordinal is None else ordinal + 1,
                date=datetime.now(UTC),
                note=data.note,
                status=data.status,
            )
            self._session.add(version)
            self._session.flush()
            for slot_id, part, snapshot in prepared:
                self._session.add(
                    VersionPartModel(
                        version_id=version.id,
                        slot_id=slot_id,
                        component_id=part.component_id,
                        quantity=part.quantity,
                        component_snapshot=snapshot,
                    )
                )
            robot.current_version_id = version.id
            self._session.flush()
            result = self.get_version(robot_id, version.id)
            self._session.commit()
            return result
        except Exception:
            self._session.rollback()
            raise
