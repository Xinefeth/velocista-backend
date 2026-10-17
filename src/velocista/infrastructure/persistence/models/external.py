"""External acquisition sessions and immutable sampled frames."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from velocista.infrastructure.persistence.db import Base


class ExternalSessionModel(Base):
    __tablename__ = "external_session"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    source: Mapped[str] = mapped_column(String(10))
    external_id: Mapped[str] = mapped_column(String(160))
    external_robot_id: Mapped[str] = mapped_column(String(160))
    robot_id: Mapped[str | None] = mapped_column(ForeignKey("robot.id"))
    state: Mapped[str] = mapped_column(String(30))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hello: Mapped[dict] = mapped_column(JSONB)
    config: Mapped[dict | None] = mapped_column(JSONB)
    lost_samples: Mapped[int] = mapped_column(Integer, default=0)
    diagnostics: Mapped[dict] = mapped_column(JSONB, default=dict)


class ExternalTelemetryModel(Base):
    __tablename__ = "external_telemetry"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_external_sample"),)
    session_id: Mapped[str] = mapped_column(ForeignKey("external_session.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("run.id"), index=True)
    t_ms: Mapped[int] = mapped_column(BigInteger)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB)
