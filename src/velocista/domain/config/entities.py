"""Dominio del contexto `config`: modo de funcionamiento y color de línea por robot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Mode(StrEnum):
    TEST = "test"  # antes "prueba"
    COMPETITION = "competition"  # antes "competencia"


class Line(StrEnum):
    BLACK = "black"  # antes "negra"
    WHITE = "white"  # antes "blanca"


@dataclass
class RobotConfig:
    """Modo y color de línea guardados; None cuando aún no se fijó alguno."""

    mode: str | None
    line: str | None
    updated_at: datetime | None
