"""Casos de uso del contexto `measurements`. Orquestan dominio y ports; no conocen HTTP ni SQL.

- MeasurementsService: crear una medición, recibir lecturas (ingesta), terminar y calcular.
- CalibrationService: calibrar giroscopio, paso y velocidad del carro de cada celular.
- GpsErrorService: pruebas del error del GPS frente a la cinta (SP-06).
- PrecisionModelService: modelo que reajusta los parámetros con mediciones repetidas (SP-07).
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime

from velocista.application.measurements.dto import IngestReport, MeasurementsPage
from velocista.application.measurements.ports import MeasurementsRepository
from velocista.domain.measurements import calibration as cal_mod
from velocista.domain.measurements import gps as gps_mod
from velocista.domain.measurements.compute import compute_result
from velocista.domain.measurements.entities import (
    ENVIRONMENTS,
    Calibration,
    CalibrationRecord,
    GpsTrial,
    Measurement,
    ModelRun,
    Reading,
)
from velocista.domain.measurements.odometry import (
    adaptive_threshold,
    detect_steps,
    motion_readings,
)
from velocista.domain.measurements.tuning import DEFAULT_ATTEMPTS, tune
from velocista.domain.measurements.validation import (
    PLACE_MAX,
    READINGS_MAX,
    reading_problem,
    validate_measurement,
)
from velocista.domain.shared.errors import Conflict, NotFound, Validation

log = logging.getLogger("velocista.measurements")


def snapshot(records: dict[str, CalibrationRecord]) -> Calibration:
    """Calibración vigente de un celular, armada con la más reciente de cada tipo."""
    c = Calibration()
    if g := records.get("gyro_bias"):
        c = replace(c, gyro_bias_dps=g.params["bias_dps"], gyro_calibrated=True)
    if s := records.get("step_length"):
        c = replace(c, step_length_m=s.params["step_length_m"])
        if s.params.get("step_threshold_ms2"):
            c = replace(c, step_threshold_ms2=s.params["step_threshold_ms2"])
    if v := records.get("car_speed"):
        c = replace(c, speed_k=v.params["k"], speed_c=v.params["c"])
    return c


class MeasurementsService:
    def __init__(self, repository: MeasurementsRepository):
        self.repository = repository

    def start(self, m: Measurement) -> Measurement:
        """Crea una medición con la calibración vigente del celular (copia fija)."""
        m = replace(m, place_name=m.place_name.strip())
        validate_measurement(m)
        cal = snapshot(self.repository.latest_calibrations(m.device_id))
        # Por pasos se puede medir sin calibrar el paso: se usa uno promedio y se avisa.
        if m.method == "car" and cal.speed_k is None:
            raise Validation("measurement_not_calibrated", "Calibrate the car speed first")
        m = replace(m, calibration=cal, status="recording", result=None)
        return self.repository.add_measurement(m)

    def get(self, measurement_id: int) -> Measurement:
        m = self.repository.get_measurement(measurement_id)
        if m is None:
            raise NotFound("measurement_not_found", "Measurement does not exist")
        return m

    def list(
        self,
        *,
        limit: int,
        offset: int,
        device_id: str | None = None,
        place_name: str | None = None,
    ) -> MeasurementsPage:
        items, total = self.repository.list_measurements(
            limit=limit, offset=offset, device_id=device_id, place_name=place_name
        )
        return MeasurementsPage(items=items, total=total, limit=limit, offset=offset)

    def ingest(self, measurement_id: int, readings: Sequence[Reading]) -> IngestReport:
        """EN-32: guarda las lecturas válidas; las inválidas se descartan y quedan en el log."""
        m = self.get(measurement_id)
        if m.status != "recording":
            raise Conflict("measurement_finished", "The measurement is finished; start a new one")
        problems: Counter[str] = Counter()
        valid: list[Reading] = []
        for r in readings:
            problem = reading_problem(r)
            if problem:
                problems[problem] += 1
            else:
                valid.append(r)
        if problems:
            log.warning("measurement %s: discarded readings %s", measurement_id, dict(problems))
        if m.reading_count + len(valid) > READINGS_MAX:
            raise Conflict(
                "measurement_too_many_readings",
                f"A measurement allows {READINGS_MAX} readings",
            )
        saved = self.repository.add_readings(measurement_id, valid) if valid else 0
        return IngestReport(
            accepted=saved,
            duplicates=len(valid) - saved,
            discarded=dict(problems),
            total_readings=m.reading_count + saved,
        )

    def readings(self, measurement_id: int) -> list[Reading]:
        self.get(measurement_id)
        return self.repository.get_readings(measurement_id)

    def finish(self, measurement_id: int) -> Measurement:
        """Calcula y guarda el resultado. Se puede llamar otra vez: recalcula."""
        m = self.get(measurement_id)
        result = compute_result(m, self.repository.get_readings(measurement_id))
        return self.repository.save_result(measurement_id, result, datetime.now(UTC))

    def delete(self, measurement_id: int) -> None:
        """Borra una medición equivocada o cancelada, con todas sus lecturas."""
        if not self.repository.delete_measurement(measurement_id):
            raise NotFound("measurement_not_found", "Measurement does not exist")


class CalibrationService:
    def __init__(self, repository: MeasurementsRepository):
        self.repository = repository

    def current(self, device_id: str) -> tuple[Calibration, dict[str, CalibrationRecord]]:
        records = self.repository.latest_calibrations(device_id)
        return snapshot(records), records

    def history(self, device_id: str) -> list[CalibrationRecord]:
        return self.repository.list_calibrations(device_id)

    def gyro(self, device_id: str, samples: Sequence[tuple[int, float]]) -> CalibrationRecord:
        c = cal_mod.gyro_bias(sorted(samples))
        params = {
            "bias_dps": c.bias_dps,
            "noise_dps": c.noise_dps,
            "samples": c.samples,
            "duration_ms": c.duration_ms,
        }
        return self.repository.add_calibration(CalibrationRecord(device_id, "gyro_bias", params))

    def step(
        self,
        device_id: str,
        trials: Sequence[tuple[float, int | None, Sequence[Reading] | None]],
    ) -> CalibrationRecord:
        """Cada intento trae los pasos contados o las lecturas del acelerómetro.

        Con lecturas, el backend cuenta los pasos con el MISMO detector que usará al medir: así
        un error del detector se compensa en el largo del paso.
        """
        # Con lecturas se aprende también el umbral de paso de esta persona (cómo pisa).
        walks = [readings for _, steps, readings in trials if steps is None and readings]
        threshold = adaptive_threshold(walks) if walks else None
        detector = Calibration(step_threshold_ms2=threshold) if threshold else Calibration()
        counted = []
        for distance, steps, readings in trials:
            if steps is None:
                steps = len(detect_steps(motion_readings(readings or []), detector))
            counted.append((distance, steps))
        c = cal_mod.step_length(counted)
        params = {
            "step_length_m": c.step_length_m,
            "lengths_m": list(c.lengths_m),
            "steps": [s for _, s in counted],
            "spread_m": c.spread_m,
            "warnings": list(c.warnings),
        }
        if threshold:
            params["step_threshold_ms2"] = threshold
        return self.repository.add_calibration(CalibrationRecord(device_id, "step_length", params))

    def car(
        self, device_id: str, trials: Sequence[tuple[float, float, float]]
    ) -> CalibrationRecord:
        c = cal_mod.car_speed(trials)
        params = {"k": c.k, "c": c.c, "r2": c.r2, "trials": c.trials}
        return self.repository.add_calibration(CalibrationRecord(device_id, "car_speed", params))


class GpsErrorService:
    def __init__(self, repository: MeasurementsRepository):
        self.repository = repository

    def add_trial(self, trial: GpsTrial) -> GpsTrial:
        if trial.environment not in ENVIRONMENTS:
            raise Validation("gps_trial_environment", f"environment must be one of {ENVIRONMENTS}")
        if not 1 <= len(trial.place_name.strip()) <= PLACE_MAX:
            raise Validation("gps_trial_place", f"place_name needs 1 to {PLACE_MAX} characters")
        if not 0 <= trial.real_distance_m <= 10_000:
            raise Validation("gps_trial_distance", "real_distance_m must be 0 to 10000 m")
        result = gps_mod.trial_errors(trial.start_fixes, trial.end_fixes, trial.real_distance_m)
        return self.repository.add_gps_trial(replace(trial, result=result))

    def list(self, device_id: str | None = None) -> list[GpsTrial]:
        return self.repository.list_gps_trials(device_id)

    def rename(self, trial_id: int, place_name: str) -> GpsTrial:
        """Corrige el nombre del lugar; las lecturas y el resultado no cambian."""
        place_name = place_name.strip()
        if not 1 <= len(place_name) <= PLACE_MAX:
            raise Validation("gps_trial_place", f"place_name needs 1 to {PLACE_MAX} characters")
        trial = self.repository.rename_gps_trial(trial_id, place_name)
        if trial is None:
            raise NotFound("gps_trial_not_found", "GPS trial does not exist")
        return trial

    def delete(self, trial_id: int) -> None:
        """Borra una prueba equivocada; el resumen deja de contarla."""
        if not self.repository.delete_gps_trial(trial_id):
            raise NotFound("gps_trial_not_found", "GPS trial does not exist")

    def summary(self, device_id: str | None = None, target_pct: float = 10.0) -> dict:
        trials = self.repository.list_gps_trials(device_id)
        out = gps_mod.trials_summary([t.result for t in trials], target_pct)
        by_env: dict[str, list[dict]] = {}
        for t in trials:
            by_env.setdefault(t.environment, []).append(t.result)
        out["by_environment"] = {
            env: gps_mod.trials_summary(rows, target_pct)["methods"] for env, rows in by_env.items()
        }
        return out


class PrecisionModelService:
    def __init__(self, repository: MeasurementsRepository):
        self.repository = repository

    def run(
        self,
        measurement_ids: Sequence[int],
        max_attempts: int = DEFAULT_ATTEMPTS,
        apply: bool = False,
    ) -> ModelRun:
        """Ajusta los parámetros con mediciones repetidas del MISMO lugar (la última valida).

        Con `apply`, los parámetros ajustados se guardan como la calibración vigente del celular
        (origen `model`), pero solo si el modelo mejoró y generaliza.
        """
        if len(set(measurement_ids)) != len(measurement_ids):
            raise Validation("model_repeated_ids", "Measurement ids must not repeat")
        samples = []
        for mid in measurement_ids:
            m = self.repository.get_measurement(mid)
            if m is None:
                raise NotFound("measurement_not_found", f"Measurement {mid} does not exist")
            samples.append((m, self.repository.get_readings(mid)))
        devices = {m.device_id for m, _ in samples}
        if len(devices) != 1:
            raise Validation("model_mixed_devices", "All measurements must come from one phone")
        result = tune(samples, max_attempts=max_attempts)
        device_id = devices.pop()
        applied = bool(apply and result["improved"] and result["generalizes"] is not False)
        if applied:
            params = result["final_params"]
            self.repository.add_calibration(
                CalibrationRecord(
                    device_id,
                    "gyro_bias",
                    {"bias_dps": params["gyro_bias_dps"]},
                    origin="model",
                )
            )
            if "step_length_m" in params:
                self.repository.add_calibration(
                    CalibrationRecord(
                        device_id,
                        "step_length",
                        {
                            "step_length_m": params["step_length_m"],
                            # el modelo ajusta el largo; se conserva el umbral aprendido
                            "step_threshold_ms2": samples[0][0].calibration.step_threshold_ms2,
                        },
                        origin="model",
                    )
                )
            if "speed_k" in params:
                c = samples[0][0].calibration.speed_c
                self.repository.add_calibration(
                    CalibrationRecord(
                        device_id,
                        "car_speed",
                        {"k": params["speed_k"], "c": c},
                        origin="model",
                    )
                )
        return self.repository.add_model_run(
            ModelRun(device_id, tuple(measurement_ids), result, applied=applied)
        )

    def list(self, device_id: str | None = None) -> list[ModelRun]:
        return self.repository.list_model_runs(device_id)
