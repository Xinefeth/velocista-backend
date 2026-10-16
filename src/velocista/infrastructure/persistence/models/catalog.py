"""Modelos ORM del catálogo y existencias: component_type, component, inventory (esquema EN)."""

from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from velocista.infrastructure.persistence.db import Base


class ComponentTypeModel(Base):
    __tablename__ = "component_type"
    __table_args__ = (
        CheckConstraint("btrim(id) <> ''", name="ck_type_id_not_empty"),
        CheckConstraint("btrim(name) <> ''", name="ck_type_name_not_empty"),
        CheckConstraint("color ~ '^#[0-9A-Fa-f]{6}$'", name="ck_type_color"),
        CheckConstraint("jsonb_typeof(fields) = 'array'", name="ck_type_fields_array"),
        CheckConstraint("jsonb_typeof(capabilities) = 'array'", name="ck_type_capabilities_array"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    color: Mapped[str] = mapped_column(String(7))
    fields: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    capabilities: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )


class ComponentModel(Base):
    __tablename__ = "component"
    __table_args__ = (
        CheckConstraint("btrim(id) <> ''", name="ck_component_id_not_empty"),
        CheckConstraint("btrim(name) <> ''", name="ck_component_name_not_empty"),
        CheckConstraint("price > 0 AND price <> 'NaN'::numeric", name="ck_component_price"),
        CheckConstraint("mass_g >= 0 AND mass_g <> 'NaN'::numeric", name="ck_component_mass"),
        CheckConstraint(
            "current_a IS NULL OR (current_a >= 0 AND current_a <> 'NaN'::numeric)",
            name="ck_component_current",
        ),
        CheckConstraint("jsonb_typeof(specs) = 'object'", name="ck_component_specs_object"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    type_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("component_type.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    mass_g: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    store: Mapped[str] = mapped_column(String(200), default="", server_default="")
    current_a: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    specs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class InventoryModel(Base):
    """Stock total, no disponible. La demanda de robots se calcula al consultar."""

    __tablename__ = "inventory"
    __table_args__ = (
        CheckConstraint("stock >= 0", name="ck_inventory_stock"),
        CheckConstraint("revision >= 1", name="ck_inventory_revision"),
    )

    component_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("component.id", ondelete="RESTRICT"), primary_key=True
    )
    stock: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
