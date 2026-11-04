"""Ports del contexto `measurements`: `infrastructure` los implementa con SQLAlchemy."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from velocista.domain.measurements.entities import (
    CalibrationRecord,
    GpsTrial,
    Measurement,
    ModelRun,
    Reading,
    Result,
)


class MeasurementsRepository(Protocol):
    # --- mediciones (EN-33)
    def add_measurement(self, measurement: Measurement) -> Measurement: ...

    def get_measurement(self, measurement_id: int) -> Measurement | None: ...

    def list_measurements(
        self, *, limit: int, offset: int, device_id: str | None, place_name: str | None
    ) -> tuple[list[Measurement], int]:
        """De la más reciente a la más antigua, y el total."""
        ...

    def add_readings(self, measurement_id: int, readings: Sequence[Reading]) -> int:
        """Guarda las lecturas; ignora las que repiten `seq`. Devuelve cuántas se guardaron."""
        ...

    def get_readings(self, measurement_id: int) -> list[Reading]: ...

    def save_result(
        self, measurement_id: int, result: Result, finished_at: datetime
    ) -> Measurement: ...

    def delete_measurement(self, measurement_id: int) -> bool:
        """Borra la medición y sus lecturas. False si no existía."""
        ...

    # --- calibraciones (EN-35)
    def add_calibration(self, record: CalibrationRecord) -> CalibrationRecord: ...

    def latest_calibrations(self, device_id: str) -> dict[str, CalibrationRecord]:
        """La calibración más reciente de cada tipo para el celular."""
        ...

    def list_calibrations(self, device_id: str) -> list[CalibrationRecord]: ...

    # --- error del GPS (SP-06)
    def add_gps_trial(self, trial: GpsTrial) -> GpsTrial: ...

    def list_gps_trials(self, device_id: str | None) -> list[GpsTrial]: ...

    # --- modelo de precisión (SP-07)
    def add_model_run(self, run: ModelRun) -> ModelRun: ...

    def list_model_runs(self, device_id: str | None) -> list[ModelRun]: ...
