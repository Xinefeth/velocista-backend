"""Entidades del contexto `builder` (armador): robots, versiones, ranuras y piezas. Núcleo puro."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RobotType(StrEnum):
    RACER = "racer"  # antes "velocista"
    MINISUMO = "minisumo"


class VersionStatus(StrEnum):
    CURRENT = "current"  # Actual
    PREVIOUS = "previous"  # Anterior
    DISCARDED = "discarded"  # Descartada
    CONCEPT = "concept"  # Concepto
    DRAFT = "draft"  # Borrador


@dataclass
class Robot:
    id: str
    name: str
    short_code: str
    type: RobotType
    firmware: str | None = None
    current_version_id: int | None = None
    archived: bool = False


@dataclass
class Slot:
    """Posición de pieza que puede ocupar una versión del robot."""

    id: str
    type_id: str
    name: str
    required: bool
    quantity_editable: bool
    rules_dependent: bool


@dataclass
class Part:
    """Una pieza colocada en una ranura de una versión."""

    component_id: str
    quantity: int


@dataclass
class Version:
    id: int
    robot_id: str
    ordinal: int
    date: datetime
    note: str
    status: VersionStatus


def version_label(ordinal: int) -> str:
    """Etiqueta visible derivada del ordinal: v0, v1, v2, …"""
    return f"v{ordinal}"
