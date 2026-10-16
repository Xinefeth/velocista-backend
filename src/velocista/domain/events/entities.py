"""Entidades del contexto `events` (bitácora del sistema). Núcleo puro."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class EventLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"  # antes "aviso"
    ERROR = "error"


@dataclass
class Event:
    """Una entrada de la bitácora."""

    system: str  # sistema que originó el evento
    level: EventLevel
    message: str
    id: int | None = None
    date: datetime | None = None
