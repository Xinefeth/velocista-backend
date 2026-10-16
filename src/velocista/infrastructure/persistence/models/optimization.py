"""Controladores y setups inmutables."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from velocista.infrastructure.persistence.db import Base


class ControllerModel(Base):
    __tablename__ = "controller"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    short_name: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    parameters: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    presets: Mapped[dict[str, Any]] = mapped_column(JSONB)


class SetupModel(Base):
    __tablename__ = "setup"
    __table_args__ = (
        UniqueConstraint("id", "version_id", name="uq_setup_version"),
        CheckConstraint("btrim(name) <> ''", name="ck_setup_name"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("version.id", ondelete="RESTRICT"), index=True
    )
    controller_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("controller.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(120))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    controller_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
