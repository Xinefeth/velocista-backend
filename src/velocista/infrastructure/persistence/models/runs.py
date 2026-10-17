"""Corridas y medidas historicas con integridad referencial."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from velocista.infrastructure.persistence.db import Base


class RunModel(Base):
    __tablename__ = "run"
    __table_args__ = (
        ForeignKeyConstraint(
            ["setup_id", "version_id"],
            ["setup.id", "setup.version_id"],
            name="fk_run_setup_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["version_id", "robot_id"],
            ["version.id", "version.robot_id"],
            name="fk_run_version_robot",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "source", "external_session_id", "external_run_id", name="uq_run_external"
        ),
        UniqueConstraint("ingestion_id", name="uq_run_ingestion_id"),
        CheckConstraint(
            "source IN ('sim','robot') AND mode IN ('test','competition') "
            "AND line IN ('black','white')",
            name="ck_run_context",
        ),
        CheckConstraint("turbine_power_pct BETWEEN 0 AND 100", name="ck_run_turbine"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, Identity(), unique=True)
    robot_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("robot.id", ondelete="RESTRICT"), index=True
    )
    version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("version.id", ondelete="RESTRICT"), index=True
    )
    setup_id: Mapped[int] = mapped_column(BigInteger, index=True)
    profile_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("profile.id", ondelete="RESTRICT")
    )
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(10))
    mode: Mapped[str | None] = mapped_column(String(20))
    line: Mapped[str | None] = mapped_column(String(10))
    battery_compensation: Mapped[bool | None] = mapped_column(Boolean)
    turbine_power_pct: Mapped[float | None] = mapped_column(Float)
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    note: Mapped[str] = mapped_column(Text, default="", server_default="")
    external_session_id: Mapped[str | None] = mapped_column(ForeignKey("external_session.id"))
    external_run_id: Mapped[str | None] = mapped_column(String(160))
    closure_status: Mapped[str | None] = mapped_column(String(20))
    ingestion_id: Mapped[str | None] = mapped_column(String(120), nullable=True)


class LapModel(Base):
    __tablename__ = "lap"
    __table_args__ = (
        UniqueConstraint("run_id", "number", name="uq_lap_number"),
        CheckConstraint(
            "number > 0 AND duration_s >= 0 AND accumulated_error >= 0 "
            "AND battery_v >= 0 AND lost_lines >= 0",
            name="ck_lap_measurements",
        ),
        CheckConstraint(
            "(finished AND time_s IS NOT NULL AND time_s >= 0) "
            "OR (NOT finished AND time_s IS NULL)",
            name="ck_lap_finish",
        ),
        CheckConstraint("time_source IN ('finish','telemetry')", name="ck_lap_time_source"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("run.id", ondelete="RESTRICT"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    time_s: Mapped[float | None] = mapped_column(Float)
    duration_s: Mapped[float] = mapped_column(Float)
    internal_time_ms: Mapped[int | None] = mapped_column(BigInteger)
    accumulated_error: Mapped[float | None] = mapped_column(Float)
    lost_lines: Mapped[int | None] = mapped_column(Integer)
    battery_v: Mapped[float | None] = mapped_column(Float)
    finished: Mapped[bool] = mapped_column(Boolean)
    time_source: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")


class LapSectorModel(Base):
    __tablename__ = "lap_sector"
    __table_args__ = (CheckConstraint("number > 0 AND time_s >= 0", name="ck_lap_sector_values"),)
    lap_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("lap.id", ondelete="RESTRICT"), primary_key=True
    )
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    time_s: Mapped[float] = mapped_column(Float)


class LapSegmentModel(Base):
    __tablename__ = "lap_segment"
    __table_args__ = (
        CheckConstraint(
            "number > 0 AND duration_s >= 0 AND accumulated_error >= 0",
            name="ck_lap_segment_values",
        ),
    )
    lap_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("lap.id", ondelete="RESTRICT"), primary_key=True
    )
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(30))
    duration_s: Mapped[float] = mapped_column(Float)
    angle_degrees: Mapped[float] = mapped_column(Float)
    accumulated_error: Mapped[float | None] = mapped_column(Float)
