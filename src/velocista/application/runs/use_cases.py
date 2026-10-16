"""Casos de uso del contexto `runs`. Orquestan dominio + ports; sin I/O directo.

Ejemplo de referencia del patrón de application.
"""

from __future__ import annotations

from velocista.application.runs.dto import CloseLapInput, Page
from velocista.application.runs.ports import RunRepository
from velocista.domain.runs.entities import Lap, TimeSource
from velocista.domain.shared.errors import NotFound


class CloseLap:
    """Cierra una vuelta de una corrida existente."""

    def __init__(self, runs: RunRepository) -> None:
        self._runs = runs

    def execute(self, data: CloseLapInput) -> None:
        run = self._runs.get(data.run_id)
        if run is None:
            raise NotFound("run_not_found", f"corrida {data.run_id} no existe")
        lap = Lap(
            number=data.lap_number,
            time_s=data.time_s,
            accumulated_error=data.accumulated_error,
            time_source=TimeSource(data.time_source),
        )
        run.close_lap(lap)  # la regla de negocio vive en la entidad
        self._runs.save(run)


class ListRuns:
    """Lista corridas paginadas."""

    def __init__(self, runs: RunRepository) -> None:
        self._runs = runs

    def execute(self, *, limit: int, offset: int) -> Page:
        items, total = self._runs.list(limit=limit, offset=offset)
        return Page(items=items, total=total, limit=limit, offset=offset)
