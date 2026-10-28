"""Persistencia de pistas del trazador. Distancias en cm; `length_cm` lo calcula el frontend."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from velocista.infrastructure.persistence.db import Base


def _array_between(column: str, low: int, high: int) -> str:
    # CASE evita que jsonb_array_length falle si el valor no es un arreglo (AND no fija el orden).
    return (
        f"CASE WHEN jsonb_typeof({column}) = 'array' "
        f"THEN jsonb_array_length({column}) BETWEEN {low} AND {high} ELSE false END"
    )


class TrackModel(Base):
    __tablename__ = "track"
    # Los límites por elemento (coordenadas, radio, zonas) los aplican el dominio y los esquemas.
    __table_args__ = (
        CheckConstraint("char_length(btrim(name)) BETWEEN 1 AND 80", name="ck_track_name"),
        CheckConstraint(
            "board_width_cm BETWEEN 50 AND 2000 AND board_height_cm BETWEEN 50 AND 2000",
            name="ck_track_board",
        ),
        CheckConstraint(_array_between("points", 2, 500), name="ck_track_points"),
        CheckConstraint(_array_between("zones", 0, 100), name="ck_track_zones"),
        CheckConstraint("start_edge >= 0", name="ck_track_start_edge"),
        CheckConstraint("start_t BETWEEN 0 AND 1", name="ck_track_start_t"),
        CheckConstraint("length_cm > 0 AND length_cm <= 100000", name="ck_track_length"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80))
    board_width_cm: Mapped[float] = mapped_column(Float)
    board_height_cm: Mapped[float] = mapped_column(Float)
    closed: Mapped[bool] = mapped_column(Boolean)
    points: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    zones: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default="[]")
    start_edge: Mapped[int] = mapped_column(Integer)
    start_t: Mapped[float] = mapped_column(Float)
    profile_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("profile.id", ondelete="RESTRICT"), index=True
    )
    length_cm: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
