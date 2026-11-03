"""Objetos de transporte del contexto `measurements` entre `application` e `interface`."""

from __future__ import annotations

from dataclasses import dataclass, field

from velocista.domain.measurements.entities import Measurement


@dataclass(frozen=True)
class MeasurementsPage:
    items: list[Measurement]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class IngestReport:
    """Resultado de recibir un lote de lecturas (EN-32)."""

    accepted: int
    duplicates: int
    discarded: dict[str, int] = field(default_factory=dict)  # motivo → cantidad
    total_readings: int = 0
