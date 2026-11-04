"""Esquemas HTTP del contexto `measurements`. Claves JSON en inglés y snake_case; distancias en m.

Las lecturas (`ReadingIn`) solo validan TIPOS: un valor fuera de rango no rechaza todo el lote,
esa lectura se descarta y se informa en `discarded` (EN-32).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from velocista.domain.measurements import validation as limits
from velocista.domain.measurements.entities import (
    XY,
    CalibrationRecord,
    GpsTrial,
    Measurement,
    ModelRun,
    Reading,
    Reference,
    Result,
)
from velocista.domain.measurements.gps import Fix

Method = Literal["steps", "gps", "car"]
Source = Literal["phone", "simulator", "robot"]
Mount = Literal["hand", "robot"]
Environment = Literal["open", "buildings", "trees", "indoor"]


def _device_id():
    return Field(min_length=1, max_length=limits.DEVICE_MAX, description="Phone id (UUID)")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class MetrePointIO(_Strict):
    x: float
    y: float


class ReferenceIO(_Strict):
    points: list[MetrePointIO] = Field(
        min_length=3,
        max_length=limits.REFERENCE_MAX_POINTS,
        description="Plan polygon in metres as drawn",
    )
    scale_n: float = Field(
        default=1,
        gt=0,
        le=limits.SCALE_MAX,
        description="Plan scale 1:N (real = drawn × N)",
    )
    name: str = Field(default="", max_length=80)

    def to_entity(self) -> Reference:
        return Reference(tuple(XY(p.x, p.y) for p in self.points), self.scale_n, self.name)


class MeasurementIn(_Strict):
    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "method": "steps",
                "source": "phone",
                "mount": "hand",
                "place_name": "Aula 204",
                "device_id": "3f0c2a9e-phone",
                "closed": True,
                "reference": {
                    "points": [
                        {"x": 0, "y": 0},
                        {"x": 10, "y": 0},
                        {"x": 10, "y": 6},
                        {"x": 0, "y": 6},
                    ]
                },
                "tape_side_m": 10,
            }
        },
    )

    method: Method
    source: Source = "phone"
    mount: Mount = "hand"
    place_name: str = Field(min_length=1, max_length=limits.PLACE_MAX)
    device_id: str = _device_id()
    closed: bool = Field(default=True, description="True when the walk returns to the start")
    reference: ReferenceIO | None = None
    tape_side_m: float | None = Field(
        default=None,
        gt=0,
        le=limits.TAPE_SIDE_MAX_M,
        description="First side measured with tape (start → first marked corner), metres",
    )

    def to_entity(self) -> Measurement:
        return Measurement(
            method=self.method,
            source=self.source,
            mount=self.mount,
            place_name=self.place_name,
            device_id=self.device_id,
            closed=self.closed,
            reference=self.reference.to_entity() if self.reference else None,
            tape_side_m=self.tape_side_m,
        )


class ReadingIn(BaseModel):
    """Una lectura del celular. `kind`: motion | gps | corner."""

    model_config = ConfigDict(extra="ignore")

    seq: int = Field(description="Sequence number from the phone; repeated seq is ignored")
    t_ms: int = Field(description="Phone time in epoch milliseconds")
    kind: str
    gyro_z_dps: float | None = Field(
        default=None,
        description="Rotation rate around the screen axis (°/s), CCW positive",
    )
    accel: list[float] | None = Field(
        default=None, description="Acceleration including gravity [x, y, z] in m/s²"
    )
    step: bool = Field(default=False, description="True if the phone already detected a step")
    pwm: float | None = Field(default=None, description="Motor PWM % when on the car")
    lat: float | None = None
    lon: float | None = None
    accuracy_m: float | None = Field(default=None, description="Accuracy reported by the phone")

    def to_entity(self) -> Reading:
        return Reading(
            seq=self.seq,
            t_ms=self.t_ms,
            kind=self.kind,
            gyro_z_dps=self.gyro_z_dps,
            accel=tuple(self.accel) if self.accel is not None else None,
            step=self.step,
            pwm=self.pwm,
            lat=self.lat,
            lon=self.lon,
            accuracy_m=self.accuracy_m,
        )


class ReadingOut(BaseModel):
    seq: int
    t_ms: int
    kind: str
    gyro_z_dps: float | None
    accel: list[float] | None
    step: bool
    pwm: float | None
    lat: float | None
    lon: float | None
    accuracy_m: float | None

    @classmethod
    def from_entity(cls, r: Reading) -> ReadingOut:
        return cls(
            seq=r.seq,
            t_ms=r.t_ms,
            kind=r.kind,
            gyro_z_dps=r.gyro_z_dps,
            accel=list(r.accel) if r.accel is not None else None,
            step=r.step,
            pwm=r.pwm,
            lat=r.lat,
            lon=r.lon,
            accuracy_m=r.accuracy_m,
        )


class ReadingsBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    readings: list[ReadingIn] = Field(min_length=1, max_length=limits.BATCH_MAX)


class IngestReportOut(BaseModel):
    accepted: int = Field(description="Readings stored")
    duplicates: int = Field(description="Readings ignored because their seq was already stored")
    discarded: dict[str, int] = Field(description="Invalid readings by reason (not stored)")
    total_readings: int


class CalibrationOut(BaseModel):
    gyro_bias_dps: float
    gyro_calibrated: bool
    step_length_m: float | None
    speed_k: float | None
    speed_c: float
    step_threshold_ms2: float
    step_min_interval_ms: int


class ResultOut(BaseModel):
    method: str
    reading_count: int
    step_count: int
    distance_m: float
    closure_error_m: float
    closure_error_pct: float
    heading_drift_deg: float | None
    raw_perimeter_m: float
    raw_area_m2: float
    perimeter_m: float
    area_m2: float
    scale_factor: float | None
    corners: int
    concave: bool
    self_crossing: bool
    quality: Literal["green", "yellow", "red"]
    reference_perimeter_m: float | None
    reference_area_m2: float | None
    perimeter_error_pct: float | None
    area_error_pct: float | None
    min_gps_size_m: float | None
    turn_total_deg: float | None = Field(
        default=None,
        description=(
            "Accumulated turn of the whole walk, in degrees, positive to the left "
            "(counterclockwise): about -360 for a closed lap walked clockwise and +360 "
            "counterclockwise. `null` for GPS measurements and for results saved before this "
            "field existed. `heading_drift_deg` is what is left over from a multiple of 360"
        ),
        examples=[-358.4],
    )
    warnings: list[str]
    raw_path: list[MetrePointIO]
    corrected_path: list[MetrePointIO]
    polygon: list[MetrePointIO]

    @classmethod
    def from_entity(cls, r: Result, paths: bool = True) -> ResultOut:
        data: dict[str, Any] = {k: getattr(r, k) for k in cls.model_fields}
        data["warnings"] = list(r.warnings)
        for key in ("raw_path", "corrected_path", "polygon"):
            data[key] = [MetrePointIO(x=p.x, y=p.y) for p in getattr(r, key)] if paths else []
        return cls(**data)


class MeasurementOut(BaseModel):
    id: int
    device_id: str
    method: str
    source: str
    mount: str
    place_name: str
    closed: bool
    reference: ReferenceIO | None
    tape_side_m: float | None
    calibration: CalibrationOut
    status: Literal["recording", "finished"]
    reading_count: int
    started_at: AwareDatetime
    finished_at: AwareDatetime | None
    result: ResultOut | None

    @classmethod
    def from_entity(cls, m: Measurement, paths: bool = True) -> MeasurementOut:
        ref = None
        if m.reference is not None:
            ref = ReferenceIO(
                points=[MetrePointIO(x=p.x, y=p.y) for p in m.reference.points],
                scale_n=m.reference.scale_n,
                name=m.reference.name,
            )
        c = m.calibration
        return cls(
            id=m.id,
            device_id=m.device_id,
            method=m.method,
            source=m.source,
            mount=m.mount,
            place_name=m.place_name,
            closed=m.closed,
            reference=ref,
            tape_side_m=m.tape_side_m,
            calibration=CalibrationOut(
                gyro_bias_dps=c.gyro_bias_dps,
                gyro_calibrated=c.gyro_calibrated,
                step_length_m=c.step_length_m,
                speed_k=c.speed_k,
                speed_c=c.speed_c,
                step_threshold_ms2=c.step_threshold_ms2,
                step_min_interval_ms=c.step_min_interval_ms,
            ),
            status=m.status,
            reading_count=m.reading_count,
            started_at=m.started_at,
            finished_at=m.finished_at,
            result=ResultOut.from_entity(m.result, paths) if m.result else None,
        )


class MeasurementsPage(BaseModel):
    items: list[MeasurementOut]
    total: int
    limit: int
    offset: int


# ------------------------------------------------------------------ calibración (EN-35)


class GyroSampleIn(_Strict):
    t_ms: int = Field(ge=0)
    gyro_z_dps: float = Field(ge=-limits.GYRO_MAX_DPS, le=limits.GYRO_MAX_DPS)


class GyroCalibrationIn(_Strict):
    samples: list[GyroSampleIn] = Field(
        min_length=1, max_length=5000, description="Phone lying still for ~5 s"
    )


class StepTrialIn(_Strict):
    distance_m: float = Field(gt=0, le=200, description="Distance measured with tape")
    step_count: int | None = Field(
        default=None, gt=0, le=1000, description="Steps counted (or send `readings`)"
    )
    readings: list[ReadingIn] | None = Field(
        default=None,
        max_length=20000,
        description="Accelerometer readings of the walk; the backend counts the steps",
    )


class StepCalibrationIn(_Strict):
    trials: list[StepTrialIn] = Field(min_length=1, max_length=10)


class CarTrialIn(_Strict):
    pwm: float = Field(gt=0, le=100)
    distance_m: float = Field(gt=0, le=100)
    seconds: float = Field(gt=0, le=600)


class CarCalibrationIn(_Strict):
    trials: list[CarTrialIn] = Field(min_length=1, max_length=20)


class CalibrationRecordOut(BaseModel):
    id: int
    device_id: str
    kind: str
    origin: str
    params: dict[str, Any]
    created_at: AwareDatetime

    @classmethod
    def from_entity(cls, r: CalibrationRecord) -> CalibrationRecordOut:
        return cls(
            id=r.id,
            device_id=r.device_id,
            kind=r.kind,
            origin=r.origin,
            params=r.params,
            created_at=r.created_at,
        )


class CalibrationStateOut(BaseModel):
    device_id: str
    calibration: CalibrationOut
    ready: dict[str, bool] = Field(description="Which methods can start a measurement")
    records: dict[str, CalibrationRecordOut]


# ------------------------------------------------------------------ error del GPS (SP-06)


class FixIO(_Strict):
    t_ms: int = Field(ge=0)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(gt=0, le=limits.ACCURACY_MAX_M)

    def to_entity(self) -> Fix:
        return Fix(self.t_ms, self.lat, self.lon, self.accuracy_m)


class GpsTrialRenameIn(_Strict):
    place_name: str = Field(min_length=1, max_length=limits.PLACE_MAX, examples=["Calle Bolívar"])


class GpsTrialIn(_Strict):
    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "device_id": "3f0c2a9e-phone",
                "place_name": "Cancha de fútbol",
                "environment": "open",
                "real_distance_m": 50,
                "start_fixes": [
                    {
                        "t_ms": 1730592000000,
                        "lat": -8.1116,
                        "lon": -79.0287,
                        "accuracy_m": 5.0,
                    },
                    {
                        "t_ms": 1730592001000,
                        "lat": -8.11161,
                        "lon": -79.0287,
                        "accuracy_m": 4.0,
                    },
                    {
                        "t_ms": 1730592002000,
                        "lat": -8.1116,
                        "lon": -79.02871,
                        "accuracy_m": 4.5,
                    },
                ],
                "end_fixes": [
                    {
                        "t_ms": 1730592060000,
                        "lat": -8.1116,
                        "lon": -79.02825,
                        "accuracy_m": 6.0,
                    },
                    {
                        "t_ms": 1730592061000,
                        "lat": -8.11159,
                        "lon": -79.02825,
                        "accuracy_m": 5.0,
                    },
                    {
                        "t_ms": 1730592062000,
                        "lat": -8.1116,
                        "lon": -79.02824,
                        "accuracy_m": 5.5,
                    },
                ],
            }
        },
    )

    device_id: str = _device_id()
    place_name: str = Field(min_length=1, max_length=limits.PLACE_MAX)
    environment: Environment
    real_distance_m: float = Field(
        ge=0,
        le=10000,
        description="Tape distance between the two points; 0 = same point",
    )
    start_fixes: list[FixIO] = Field(min_length=3, max_length=600)
    end_fixes: list[FixIO] = Field(min_length=3, max_length=600)

    def to_entity(self) -> GpsTrial:
        return GpsTrial(
            device_id=self.device_id,
            place_name=self.place_name,
            environment=self.environment,
            real_distance_m=self.real_distance_m,
            start_fixes=tuple(f.to_entity() for f in self.start_fixes),
            end_fixes=tuple(f.to_entity() for f in self.end_fixes),
        )


class GpsTrialOut(BaseModel):
    id: int
    device_id: str
    place_name: str
    environment: str
    real_distance_m: float
    fix_count: int
    result: dict[str, Any] = Field(
        description="Error per method: single reading, mean, filtered (weighted by accuracy)"
    )
    created_at: AwareDatetime

    @classmethod
    def from_entity(cls, t: GpsTrial) -> GpsTrialOut:
        return cls(
            id=t.id,
            device_id=t.device_id,
            place_name=t.place_name,
            environment=t.environment,
            real_distance_m=t.real_distance_m,
            fix_count=len(t.start_fixes) + len(t.end_fixes),
            result=t.result,
            created_at=t.created_at,
        )


# ------------------------------------------------------------------ modelo de precisión (SP-07)


class ModelRunIn(_Strict):
    measurement_ids: list[int] = Field(
        min_length=2,
        max_length=30,
        description="Repeated measurements of the SAME place; the last one is kept for checking",
    )
    max_attempts: int = Field(default=40, ge=1, le=200)
    apply: bool = Field(
        default=False,
        description="Save the tuned parameters as the phone calibration if they improve",
    )


class ModelRunOut(BaseModel):
    id: int
    device_id: str
    measurement_ids: list[int]
    applied: bool
    result: dict[str, Any]
    created_at: AwareDatetime

    @classmethod
    def from_entity(cls, r: ModelRun) -> ModelRunOut:
        return cls(
            id=r.id,
            device_id=r.device_id,
            measurement_ids=list(r.measurement_ids),
            applied=r.applied,
            result=r.result,
            created_at=r.created_at,
        )


class ModelEvaluationIn(_Strict):
    measurement_ids: list[int] = Field(
        min_length=2,
        max_length=30,
        description="Repeated measurements of the SAME place; the last one is kept for checking",
    )
    max_attempts: int = Field(default=40, ge=1, le=200)


class ErrorSummaryOut(BaseModel):
    mean_closure_error_m: float | None
    mean_closure_error_pct: float | None
    mean_abs_perimeter_error_pct: float | None = Field(
        description="Only when the measurements have a plan or a tape side"
    )
    quality: str | None = Field(description="green | yellow | red for the mean closure error")


class MeasurementErrorsOut(BaseModel):
    closure_error_m: float
    closure_error_pct: float
    perimeter_error_pct: float | None


class EvaluationRowOut(BaseModel):
    measurement_id: int
    role: str = Field(description="train (used to tune) | holdout (kept out to check)")
    before: MeasurementErrorsOut
    after: MeasurementErrorsOut


class CurvePointOut(BaseModel):
    attempt: int = Field(description="0 is the algorithm alone, before the first attempt")
    without_model_pct: float | None
    with_model_pct: float | None


class ModelEvaluationOut(BaseModel):
    method: str
    measurement_count: int
    train_count: int
    holdout_measurement_id: int | None
    green_limit_pct: float
    initial_params: dict[str, float]
    final_params: dict[str, float]
    baseline: ErrorSummaryOut = Field(description="Algorithm alone (calibration + closure)")
    model: ErrorSummaryOut = Field(description="Same algorithm with the tuned parameters")
    improvement_pct_points: float | None
    improved: bool = Field(description="The mean closure error went down with the model")
    cost_improved: bool = Field(description="The model penalty (closure + plan error) went down")
    meets_green: bool
    generalizes: bool | None
    verdict: str = Field(description="improves_green | improves_not_green | no_improvement")
    curve: list[CurvePointOut]
    measurements: list[EvaluationRowOut]
