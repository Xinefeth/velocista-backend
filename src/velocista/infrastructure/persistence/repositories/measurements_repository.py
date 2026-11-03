"""Repositorio SQLAlchemy de `measurements`. Implementa el port `MeasurementsRepository`."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from velocista.domain.measurements.entities import (
    XY,
    Calibration,
    CalibrationRecord,
    GpsTrial,
    Measurement,
    ModelRun,
    Reading,
    Reference,
    Result,
)
from velocista.domain.measurements.gps import Fix
from velocista.infrastructure.persistence.models.measurements import (
    GpsTrialModel,
    MeasurementModel,
    MeasurementReadingModel,
    PrecisionModelRunModel,
    SensorCalibrationModel,
)

PATHS = ("raw_path", "corrected_path", "polygon")


# ------------------------------------------------------------------ conversión entidad ↔ JSON


def _points(rows) -> tuple[XY, ...]:
    return tuple(XY(p["x"], p["y"]) for p in rows)


def result_to_json(r: Result) -> dict:
    data = asdict(r)
    data["warnings"] = list(r.warnings)
    return data


def result_from_json(data: dict | None) -> Result | None:
    if data is None:
        return None
    values = dict(data)
    for key in PATHS:
        values[key] = _points(values.get(key, []))
    values["warnings"] = tuple(values.get("warnings", []))
    return Result(**values)


def _reference_to_json(ref: Reference | None) -> dict | None:
    if ref is None:
        return None
    return {
        "points": [asdict(p) for p in ref.points],
        "scale_n": ref.scale_n,
        "name": ref.name,
    }


def _reference_from_json(data: dict | None) -> Reference | None:
    if data is None:
        return None
    return Reference(_points(data["points"]), data.get("scale_n", 1.0), data.get("name", ""))


def _measurement(row: MeasurementModel) -> Measurement:
    return Measurement(
        id=row.id,
        method=row.method,
        source=row.source,
        mount=row.mount,
        place_name=row.place_name,
        device_id=row.device_id,
        closed=row.closed,
        reference=_reference_from_json(row.reference),
        tape_side_m=row.tape_side_m,
        calibration=Calibration(**row.calibration),
        status=row.status,
        reading_count=row.reading_count,
        result=result_from_json(row.result),
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _reading(row: MeasurementReadingModel) -> Reading:
    accel = None
    if row.accel_x is not None:
        accel = (row.accel_x, row.accel_y or 0.0, row.accel_z or 0.0)
    return Reading(
        seq=row.seq,
        t_ms=row.t_ms,
        kind=row.kind,
        gyro_z_dps=row.gyro_z_dps,
        accel=accel,
        step=row.step,
        pwm=row.pwm,
        lat=row.lat,
        lon=row.lon,
        accuracy_m=row.accuracy_m,
    )


def _reading_row(measurement_id: int, r: Reading) -> dict:
    ax, ay, az = r.accel if r.accel is not None else (None, None, None)
    return {
        "measurement_id": measurement_id,
        "seq": r.seq,
        "t_ms": r.t_ms,
        "kind": r.kind,
        "gyro_z_dps": r.gyro_z_dps,
        "accel_x": ax,
        "accel_y": ay,
        "accel_z": az,
        "step": r.step,
        "pwm": r.pwm,
        "lat": r.lat,
        "lon": r.lon,
        "accuracy_m": r.accuracy_m,
    }


def _calibration(row: SensorCalibrationModel) -> CalibrationRecord:
    return CalibrationRecord(
        device_id=row.device_id,
        kind=row.kind,
        params=row.params,
        origin=row.origin,
        id=row.id,
        created_at=row.created_at,
    )


def _fixes_json(fixes) -> list[dict]:
    return [asdict(f) for f in fixes]


def _gps_trial(row: GpsTrialModel) -> GpsTrial:
    return GpsTrial(
        device_id=row.device_id,
        place_name=row.place_name,
        environment=row.environment,
        real_distance_m=row.real_distance_m,
        start_fixes=tuple(Fix(**f) for f in row.start_fixes),
        end_fixes=tuple(Fix(**f) for f in row.end_fixes),
        result=row.result,
        id=row.id,
        created_at=row.created_at,
    )


def _model_run(row: PrecisionModelRunModel) -> ModelRun:
    return ModelRun(
        device_id=row.device_id,
        measurement_ids=tuple(row.measurement_ids),
        result=row.result,
        applied=row.applied,
        id=row.id,
        created_at=row.created_at,
    )


# ------------------------------------------------------------------ repositorio


class SqlAlchemyMeasurementsRepository:
    def __init__(self, session):
        self.session = session

    # --- mediciones
    def add_measurement(self, m):
        row = MeasurementModel(
            device_id=m.device_id,
            method=m.method,
            source=m.source,
            mount=m.mount,
            place_name=m.place_name,
            closed=m.closed,
            reference=_reference_to_json(m.reference),
            tape_side_m=m.tape_side_m,
            calibration=asdict(m.calibration),
            status=m.status,
            reading_count=0,
            started_at=datetime.now(UTC),
        )
        self.session.add(row)
        self.session.commit()
        return _measurement(row)

    def get_measurement(self, measurement_id):
        row = self.session.get(MeasurementModel, measurement_id)
        return _measurement(row) if row else None

    def list_measurements(self, *, limit, offset, device_id, place_name):
        query = select(MeasurementModel)
        if device_id:
            query = query.where(MeasurementModel.device_id == device_id)
        if place_name:
            query = query.where(func.lower(MeasurementModel.place_name) == place_name.lower())
        total = self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.session.scalars(
            query.order_by(MeasurementModel.started_at.desc(), MeasurementModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_measurement(row) for row in rows], total

    def add_readings(self, measurement_id, readings):
        # RETURNING cuenta las filas guardadas: con varias filas y ON CONFLICT, `rowcount`
        # de psycopg 3 vale -1 y no sirve para saber cuántas lecturas eran nuevas.
        stmt = (
            insert(MeasurementReadingModel)
            .values([_reading_row(measurement_id, r) for r in readings])
            .on_conflict_do_nothing(index_elements=["measurement_id", "seq"])
            .returning(MeasurementReadingModel.id)
        )
        saved = len(self.session.execute(stmt).all())
        if saved:
            self.session.execute(
                update(MeasurementModel)
                .where(MeasurementModel.id == measurement_id)
                .values(reading_count=MeasurementModel.reading_count + saved)
            )
        self.session.commit()
        return saved

    def get_readings(self, measurement_id):
        rows = self.session.scalars(
            select(MeasurementReadingModel)
            .where(MeasurementReadingModel.measurement_id == measurement_id)
            .order_by(MeasurementReadingModel.t_ms, MeasurementReadingModel.seq)
        )
        return [_reading(row) for row in rows]

    def save_result(self, measurement_id, result, finished_at):
        row = self.session.get(MeasurementModel, measurement_id)
        row.result = result_to_json(result)
        row.perimeter_m = result.perimeter_m
        row.area_m2 = result.area_m2
        row.closure_error_pct = result.closure_error_pct
        row.quality = result.quality
        row.status = "finished"
        row.finished_at = finished_at
        self.session.commit()
        return _measurement(row)

    # --- calibraciones
    def add_calibration(self, record):
        row = SensorCalibrationModel(
            device_id=record.device_id,
            kind=record.kind,
            origin=record.origin,
            params=record.params,
            created_at=datetime.now(UTC),
        )
        self.session.add(row)
        self.session.commit()
        return _calibration(row)

    def latest_calibrations(self, device_id):
        latest: dict[str, CalibrationRecord] = {}
        for record in self.list_calibrations(device_id):
            latest.setdefault(record.kind, record)  # vienen de la más nueva a la más vieja
        return latest

    def list_calibrations(self, device_id):
        rows = self.session.scalars(
            select(SensorCalibrationModel)
            .where(SensorCalibrationModel.device_id == device_id)
            .order_by(
                SensorCalibrationModel.created_at.desc(),
                SensorCalibrationModel.id.desc(),
            )
        )
        return [_calibration(row) for row in rows]

    # --- error del GPS
    def add_gps_trial(self, trial):
        row = GpsTrialModel(
            device_id=trial.device_id,
            place_name=trial.place_name,
            environment=trial.environment,
            real_distance_m=trial.real_distance_m,
            start_fixes=_fixes_json(trial.start_fixes),
            end_fixes=_fixes_json(trial.end_fixes),
            result=trial.result,
            created_at=datetime.now(UTC),
        )
        self.session.add(row)
        self.session.commit()
        return _gps_trial(row)

    def list_gps_trials(self, device_id):
        query = select(GpsTrialModel)
        if device_id:
            query = query.where(GpsTrialModel.device_id == device_id)
        rows = self.session.scalars(
            query.order_by(GpsTrialModel.created_at.desc(), GpsTrialModel.id.desc())
        )
        return [_gps_trial(row) for row in rows]

    # --- modelo de precisión
    def add_model_run(self, run):
        row = PrecisionModelRunModel(
            device_id=run.device_id,
            measurement_ids=list(run.measurement_ids),
            result=run.result,
            applied=run.applied,
            created_at=datetime.now(UTC),
        )
        self.session.add(row)
        self.session.commit()
        return _model_run(row)

    def list_model_runs(self, device_id):
        query = select(PrecisionModelRunModel)
        if device_id:
            query = query.where(PrecisionModelRunModel.device_id == device_id)
        rows = self.session.scalars(
            query.order_by(
                PrecisionModelRunModel.created_at.desc(),
                PrecisionModelRunModel.id.desc(),
            )
        )
        return [_model_run(row) for row in rows]
