"""Persistencia del contexto `measurements` (EN-33). Distancias en metros, tiempos en ms.

Tablas:
- measurement            una medición (cabecera + resultado calculado)
- measurement_reading    cada lectura del celular (GPS, giroscopio/acelerómetro, esquina)
- sensor_calibration     calibraciones de cada celular (giroscopio, paso, velocidad del carro)
- gps_trial              pruebas del error del GPS frente a la cinta (SP-06)
- precision_model_run    corridas del modelo de precisión (SP-07)
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from velocista.infrastructure.persistence.db import Base


class MeasurementModel(Base):
    __tablename__ = "measurement"
    __table_args__ = (
        CheckConstraint("method IN ('steps', 'gps', 'car')", name="ck_measurement_method"),
        CheckConstraint("source IN ('phone', 'simulator', 'robot')", name="ck_measurement_source"),
        CheckConstraint("mount IN ('hand', 'robot')", name="ck_measurement_mount"),
        CheckConstraint("status IN ('recording', 'finished')", name="ck_measurement_status"),
        CheckConstraint(
            "char_length(btrim(place_name)) BETWEEN 1 AND 80",
            name="ck_measurement_place",
        ),
        CheckConstraint("reading_count >= 0", name="ck_measurement_reading_count"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    method: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(12))
    mount: Mapped[str] = mapped_column(String(8))
    place_name: Mapped[str] = mapped_column(String(80))
    closed: Mapped[bool] = mapped_column(Boolean, default=True)
    reference: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    tape_side_m: Mapped[float | None] = mapped_column(Float)
    calibration: Mapped[dict[str, Any]] = mapped_column(JSONB)  # copia fija al crearla
    status: Mapped[str] = mapped_column(String(12), default="recording")
    reading_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Copias del resultado en columnas para listar y filtrar sin abrir el JSON.
    perimeter_m: Mapped[float | None] = mapped_column(Float)
    area_m2: Mapped[float | None] = mapped_column(Float)
    closure_error_pct: Mapped[float | None] = mapped_column(Float)
    quality: Mapped[str | None] = mapped_column(String(8))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MeasurementReadingModel(Base):
    __tablename__ = "measurement_reading"
    __table_args__ = (
        UniqueConstraint("measurement_id", "seq", name="uq_measurement_reading_seq"),
        CheckConstraint("kind IN ('motion', 'gps', 'corner')", name="ck_measurement_reading_kind"),
        CheckConstraint("seq >= 0 AND t_ms >= 0", name="ck_measurement_reading_seq"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    measurement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("measurement.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    t_ms: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(8))
    gyro_z_dps: Mapped[float | None] = mapped_column(Float)
    accel_x: Mapped[float | None] = mapped_column(Float)
    accel_y: Mapped[float | None] = mapped_column(Float)
    accel_z: Mapped[float | None] = mapped_column(Float)
    step: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    pwm: Mapped[float | None] = mapped_column(Float)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)


class SensorCalibrationModel(Base):
    __tablename__ = "sensor_calibration"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('gyro_bias', 'step_length', 'car_speed')",
            name="ck_sensor_calibration_kind",
        ),
        CheckConstraint("origin IN ('manual', 'model')", name="ck_sensor_calibration_origin"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(12))
    origin: Mapped[str] = mapped_column(String(8), default="manual")
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GpsTrialModel(Base):
    __tablename__ = "gps_trial"
    __table_args__ = (
        CheckConstraint(
            "environment IN ('open', 'buildings', 'trees', 'indoor')",
            name="ck_gps_trial_env",
        ),
        CheckConstraint("real_distance_m >= 0", name="ck_gps_trial_distance"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    place_name: Mapped[str] = mapped_column(String(80))
    environment: Mapped[str] = mapped_column(String(12))
    real_distance_m: Mapped[float] = mapped_column(Float)
    start_fixes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    end_fixes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PrecisionModelRunModel(Base):
    __tablename__ = "precision_model_run"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    measurement_ids: Mapped[list[int]] = mapped_column(JSONB)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
