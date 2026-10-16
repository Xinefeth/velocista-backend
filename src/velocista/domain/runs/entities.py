"""Entidades del contexto `runs` (corridas y vueltas). Núcleo puro: sin ORM ni pydantic.

Ejemplo de referencia del patrón de dominio. Las invariantes se validan aquí, no en
los routers ni en la base de datos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from velocista.domain.shared.errors import Conflict, Validation


class Source(StrEnum):
    """De dónde salió la corrida."""

    SIM = "sim"
    ROBOT = "robot"


class Mode(StrEnum):
    TEST = "test"
    COMPETITION = "competition"


class Line(StrEnum):
    BLACK = "black"
    WHITE = "white"


class TimeSource(StrEnum):
    """Quién midió el tiempo oficial de la vuelta."""

    FINISH = "finish"  # línea de meta / cronómetro
    TELEMETRY = "telemetry"  # reloj interno del robot


@dataclass
class Lap:
    """Una vuelta dentro de una corrida."""

    number: int
    time_s: float | None
    accumulated_error: float
    time_source: TimeSource
    finished: bool = False

    def __post_init__(self) -> None:
        # Invariante: el error acumulado nunca es negativo.
        if self.accumulated_error < 0:
            raise Validation("invalid_accumulated_error", "accumulated_error no puede ser negativo")


@dataclass
class Run:
    """Una corrida: secuencia de vueltas en una configuración dada."""

    id: int | None
    number: int
    robot_id: str
    mode: Mode
    line: Line
    source: Source
    date: datetime
    laps: list[Lap] = field(default_factory=list)

    def close_lap(self, lap: Lap) -> None:
        """Cierra una vuelta aplicando las reglas de negocio.

        Ejemplo de regla: no se puede cerrar una vuelta con un número ya presente.
        """
        if any(existing.number == lap.number for existing in self.laps):
            raise Conflict("duplicate_lap", f"la vuelta {lap.number} ya está registrada")
        lap.finished = True
        self.laps.append(lap)
