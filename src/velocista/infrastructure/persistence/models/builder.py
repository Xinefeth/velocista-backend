"""Modelos ORM del contexto builder: robot, slot, version, version_part (esquema en inglés)."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from velocista.infrastructure.persistence.db import Base


class RobotModel(Base):
    __tablename__ = "robot"
    __table_args__ = (
        CheckConstraint("btrim(id) <> ''", name="ck_robot_id_not_empty"),
        CheckConstraint("btrim(name) <> ''", name="ck_robot_name_not_empty"),
        CheckConstraint("btrim(short_code) <> ''", name="ck_robot_short_code_not_empty"),
        CheckConstraint("type IN ('racer', 'minisumo')", name="ck_robot_type"),
        ForeignKeyConstraint(
            ["current_version_id", "id"],
            ["version.id", "version.robot_id"],
            name="fk_robot_current_version",
            use_alter=True,
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    short_code: Mapped[str] = mapped_column(String(12), unique=True)
    type: Mapped[str] = mapped_column(String(20))
    firmware: Mapped[str | None] = mapped_column(String(20))
    current_version_id: Mapped[int | None] = mapped_column(BigInteger)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class SlotModel(Base):
    __tablename__ = "slot"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    type_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("component_type.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(120))
    required: Mapped[bool] = mapped_column(Boolean)
    quantity_editable: Mapped[bool] = mapped_column(Boolean)
    rules_dependent: Mapped[bool] = mapped_column(Boolean)


class VersionModel(Base):
    __tablename__ = "version"
    __table_args__ = (
        UniqueConstraint("robot_id", "ordinal", name="uq_version_ordinal"),
        UniqueConstraint("id", "robot_id", name="uq_version_ownership"),
        CheckConstraint("id BETWEEN 1 AND 9007199254740991", name="ck_version_id"),
        CheckConstraint("ordinal >= 0", name="ck_version_ordinal"),
        CheckConstraint("char_length(note) <= 1000", name="ck_version_note"),
        CheckConstraint(
            "status IN ('current','previous','discarded','concept','draft')",
            name="ck_version_status",
        ),
        Index(
            "uq_version_current",
            "robot_id",
            unique=True,
            postgresql_where=text("status = 'current'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    robot_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("robot.id", ondelete="RESTRICT"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))


class VersionPartModel(Base):
    __tablename__ = "version_part"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_version_part_quantity"),
        CheckConstraint(
            "jsonb_typeof(component_snapshot) = 'object'", name="ck_version_part_snapshot"
        ),
    )

    version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("version.id", ondelete="RESTRICT"), primary_key=True
    )
    slot_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("slot.id", ondelete="RESTRICT"), primary_key=True
    )
    component_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("component.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[int] = mapped_column(Integer)
    component_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
