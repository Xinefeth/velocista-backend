"""Modelo ORM del modo/línea por robot. Tabla `robot_config` (esquema en inglés)."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from velocista.infrastructure.persistence.db import Base


class RobotConfigModel(Base):
    __tablename__ = "robot_config"
    __table_args__ = (
        CheckConstraint("mode IS NULL OR mode IN ('test', 'competition')", name="ck_config_mode"),
        CheckConstraint("line IS NULL OR line IN ('black', 'white')", name="ck_config_line"),
    )

    robot_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("robot.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[str | None] = mapped_column(String(20))
    line: Mapped[str | None] = mapped_column(String(20))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
