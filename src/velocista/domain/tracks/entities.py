"""Entidades del contexto `tracks` (pistas del trazador). Sin frameworks.

Todas las distancias están en centímetros. Las coordenadas parten de la esquina inferior izquierda
del tablero, con `y` hacia arriba (mismo sistema que el prototipo del trazador).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Point:
    """Vértice de la poligonal. `radius` 0 = esquina viva; `gap` = corte en el tramo que sale."""

    x: float
    y: float
    radius: float = 0.0
    gap: bool = False


@dataclass(frozen=True)
class Zone:
    """Rectángulo marcado en el tablero (logo, poste del cronómetro, rampa...)."""

    x: float
    y: float
    width: float
    height: float
    name: str = ""


@dataclass(frozen=True)
class Board:
    width_cm: float
    height_cm: float


@dataclass(frozen=True)
class Start:
    """Salida: índice de tramo (`edge`) y posición relativa `t` dentro del tramo (0..1)."""

    edge: int = 0
    t: float = 0.5


@dataclass(frozen=True)
class Track:
    """Pista guardada. `length_cm` lo calcula el frontend; el backend no recalcula geometría."""

    name: str
    board: Board
    closed: bool
    points: tuple[Point, ...]
    zones: tuple[Zone, ...]
    start: Start
    profile_id: str | None
    length_cm: float
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
