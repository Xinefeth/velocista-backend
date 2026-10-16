"""Implementación SQLAlchemy de `CatalogRepository` y del `ComponentProvider` de builder.

Porte fiel del service anterior (catalogo): validación de especificaciones contra el tipo,
búsqueda sin tildes, bloqueo optimista de inventario y demanda de la última versión de robots
activos (join a las tablas de builder). Comportamiento 1:1.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import String, cast, func, or_, select, update
from sqlalchemy.orm import Session

from velocista.domain.shared.errors import Conflict, NotFound, Validation
from velocista.infrastructure.persistence.models.builder import RobotModel, VersionPartModel
from velocista.infrastructure.persistence.models.catalog import (
    ComponentModel,
    ComponentTypeModel,
    InventoryModel,
)

_ACCENTS = ("áéíóúüñ", "aeiouun")


def _demand_subquery():
    """Demanda de la última versión de robots activos; excluye historia anterior."""
    return (
        select(
            VersionPartModel.component_id,
            func.sum(VersionPartModel.quantity).label("in_robots"),
        )
        .join(RobotModel, RobotModel.current_version_id == VersionPartModel.version_id)
        .where(RobotModel.archived.is_(False))
        .group_by(VersionPartModel.component_id)
        .subquery()
    )


def _validate_specs(session: Session, type_id: str, specs: dict, current_a) -> None:
    """Valida el estado completo, tanto para altas como para ediciones parciales."""
    type_row = session.get(ComponentTypeModel, type_id)
    if type_row is None:
        raise Validation("type_unavailable", "Carga los tipos de componente primero")
    fields = {field["key"]: field for field in type_row.fields}
    for key, value in specs.items():
        field = fields.get(key)
        if field is None:
            raise Validation("invalid_spec", f"Campo no permitido: {key}")
        valid = (
            isinstance(value, (int, float)) and value >= 0
            if field["type"] == "number"
            else isinstance(value, str) and len(value) <= 120
        )
        if not valid:
            raise Validation("invalid_spec", f"Valor inválido para {key}")
    for key, field in fields.items():
        if field.get("required") and key not in specs:
            raise Validation("invalid_spec", f"Falta el campo {key}")
    if (
        type_id == "linea"
        and current_a is not None
        and ("current_a" in specs or "i" in specs)
        and float(current_a) != specs.get("current_a", specs.get("i"))
    ):
        raise Validation("inconsistent_current", "current_a debe coincidir con i")


class SqlAlchemyCatalogRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_component(self, data: Any) -> dict[str, Any]:
        _validate_specs(self._session, data.type_id, data.specs, data.current_a)
        card = data.model_dump(exclude={"stock"})
        card.update(id=f"c_{uuid4().hex}", archived=False)
        result = {**card, "stock": data.stock}
        try:
            self._session.add(ComponentModel(**card))
            self._session.flush()
            self._session.add(InventoryModel(component_id=card["id"], stock=data.stock))
            self._session.flush()
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return result

    def get_component(self, component_id: str) -> dict[str, Any]:
        row = (
            self._session.execute(
                select(*ComponentModel.__table__.c, InventoryModel.stock)
                .join(InventoryModel, InventoryModel.component_id == ComponentModel.id)
                .where(ComponentModel.id == component_id)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise NotFound("component_not_found", "El componente no existe")
        return dict(row)

    def edit_component(self, component_id: str, data: Any) -> dict[str, Any]:
        try:
            component = self._session.get(ComponentModel, component_id, with_for_update=True)
            if component is None:
                raise NotFound("component_not_found", "El componente no existe")
            if component.archived:
                raise Conflict("component_archived", "No se puede editar un archivado")
            current = self.get_component(component_id)
            changes = data.model_dump(exclude_unset=True)
            combined = {**current, **changes}
            _validate_specs(
                self._session, combined["type_id"], combined["specs"], combined["current_a"]
            )
            for field, value in changes.items():
                setattr(component, field, value)
            self._session.flush()
            self._session.commit()
            return combined
        except Exception:
            self._session.rollback()
            raise

    def archive_component(self, component_id: str) -> None:
        try:
            component = self._session.get(ComponentModel, component_id, with_for_update=True)
            if component is None:
                raise NotFound("component_not_found", "El componente no existe")
            component.archived = True
            self._session.flush()
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    def list_component_types(self) -> list[ComponentTypeModel]:
        return list(
            self._session.scalars(select(ComponentTypeModel).order_by(ComponentTypeModel.id))
        )

    def list_inventory(self, *, limit: int, offset: int) -> dict[str, Any]:
        demand = _demand_subquery()
        assigned = func.coalesce(demand.c.in_robots, 0).label("in_robots")
        stmt = (
            select(
                InventoryModel.component_id, InventoryModel.stock, InventoryModel.revision, assigned
            )
            .join(ComponentModel, ComponentModel.id == InventoryModel.component_id)
            .outerjoin(demand, demand.c.component_id == InventoryModel.component_id)
            .where(or_(ComponentModel.archived.is_(False), InventoryModel.stock > 0, assigned > 0))
        )
        total = self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = self._session.execute(
            stmt.order_by(InventoryModel.component_id).limit(limit).offset(offset)
        ).all()
        return {
            "items": [
                {
                    "component_id": row.component_id,
                    "stock": row.stock,
                    "in_robots": row.in_robots,
                    "available": row.stock - row.in_robots,
                    "shortage": max(0, row.in_robots - row.stock),
                    "revision": row.revision,
                }
                for row in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def update_inventory(self, component_id: str, data: Any) -> dict[str, Any]:
        try:
            row = (
                self._session.execute(
                    update(InventoryModel)
                    .where(
                        InventoryModel.component_id == component_id,
                        InventoryModel.revision == data.revision,
                        InventoryModel.revision < 2147483647,
                    )
                    .values(stock=data.stock, revision=InventoryModel.revision + 1)
                    .returning(
                        InventoryModel.component_id, InventoryModel.stock, InventoryModel.revision
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                current = self._session.get(InventoryModel, component_id)
                if current is None:
                    raise NotFound("inventory_not_found", "El inventario no existe")
                if current.revision != data.revision:
                    raise Conflict(
                        "stale_revision", "Vuelve a consultar el inventario antes de guardar"
                    )
                raise Conflict("revision_exhausted", "Se alcanzó el límite de revisiones")
            demand = _demand_subquery()
            assigned = (
                self._session.scalar(
                    select(demand.c.in_robots).where(demand.c.component_id == component_id)
                )
                or 0
            )
            result = {
                **dict(row),
                "in_robots": assigned,
                "available": row["stock"] - assigned,
                "shortage": max(0, assigned - row["stock"]),
            }
            self._session.commit()
            return result
        except Exception:
            self._session.rollback()
            raise

    def list_components(
        self, *, limit: int, offset: int, q: str | None, type_id: str | None
    ) -> dict[str, Any]:
        stmt = (
            select(*ComponentModel.__table__.c, InventoryModel.stock)
            .join(InventoryModel, InventoryModel.component_id == ComponentModel.id)
            .join(ComponentTypeModel, ComponentTypeModel.id == ComponentModel.type_id)
            .where(ComponentModel.archived.is_(False))
        )
        if type_id is not None:
            stmt = stmt.where(ComponentModel.type_id == type_id)
        search = (q or "").strip().lower().translate(str.maketrans(*_ACCENTS))
        if search:
            targets = (
                ComponentModel.name,
                ComponentTypeModel.name,
                ComponentModel.store,
                cast(ComponentModel.specs, String),
            )
            stmt = stmt.where(
                or_(
                    *(
                        func.translate(func.lower(target), *_ACCENTS).contains(
                            search, autoescape=True
                        )
                        for target in targets
                    )
                )
            )
        total = self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (
            self._session.execute(
                stmt.order_by(func.lower(ComponentModel.name), ComponentModel.id)
                .limit(limit)
                .offset(offset)
            )
            .mappings()
            .all()
        )
        return {
            "items": [dict(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


class CatalogComponentProvider:
    """Implementa el port `ComponentProvider` de builder: ficha para congelar en una versión."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = SqlAlchemyCatalogRepository(session)

    def snapshot_for_version(self, component_id: str) -> dict[str, Any]:
        card = self._session.get(ComponentModel, component_id, with_for_update=True)
        if card is None:
            raise NotFound("component_not_found", "El componente no existe")
        if card.archived:
            raise Conflict("component_archived", "No se puede seleccionar un archivado")
        return self._repo.get_component(component_id)
