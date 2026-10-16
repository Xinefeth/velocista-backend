"""Modelo ORM de la bitácora. Tabla `event` (esquema en inglés)."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from velocista.infrastructure.persistence.db import Base


class EventModel(Base):
    __tablename__ = "event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    system: Mapped[str] = mapped_column(String(40))
    level: Mapped[str] = mapped_column(String(10), server_default="info")
    message: Mapped[str] = mapped_column(Text)
