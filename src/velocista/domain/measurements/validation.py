"""Reglas puras de validación de mediciones y lecturas (EN-32, EN-33). Sin frameworks ni HTTP.

SUPUESTO PENDIENTE DEL PO: los límites son propuestas. Los esquemas REST los importan.
"""

from __future__ import annotations

from math import isfinite

from velocista.domain.measurements.entities import (
    METHODS,
    MOUNTS,
    READING_KINDS,
    SOURCES,
    Measurement,
    Reading,
)
from velocista.domain.shared.errors import Validation

PLACE_MAX = 80
DEVICE_MAX = 64
TAPE_SIDE_MAX_M = 1000
REFERENCE_MAX_POINTS = 200
REFERENCE_COORD_MAX = 10000
SCALE_MAX = 10000
BATCH_MAX = 1000  # lecturas por envío
READINGS_MAX = 200_000  # lecturas por medición (≈ 1 h a 50 Hz)
GYRO_MAX_DPS = 2000
ACCEL_MAX_MS2 = 160  # ±16 g
ACCURACY_MAX_M = 1000
T_MAX_MS = 4_102_444_800_000  # año 2100


def validate_measurement(m: Measurement) -> None:
    if m.method not in METHODS:
        raise Validation("measurement_method_invalid", f"method must be one of {METHODS}")
    if m.source not in SOURCES:
        raise Validation("measurement_source_invalid", f"source must be one of {SOURCES}")
    if m.mount not in MOUNTS:
        raise Validation("measurement_mount_invalid", f"mount must be one of {MOUNTS}")
    if m.method == "car" and m.mount != "robot":
        raise Validation("measurement_mount_invalid", "The car method needs mount 'robot'")
    if not 1 <= len(m.place_name.strip()) <= PLACE_MAX:
        raise Validation("measurement_place_invalid", f"place_name needs 1 to {PLACE_MAX} chars")
    if not 1 <= len(m.device_id) <= DEVICE_MAX:
        raise Validation("measurement_device_invalid", f"device_id needs 1 to {DEVICE_MAX} chars")
    if m.tape_side_m is not None and not 0 < m.tape_side_m <= TAPE_SIDE_MAX_M:
        raise Validation("measurement_tape_invalid", f"tape_side_m must be 0-{TAPE_SIDE_MAX_M} m")
    ref = m.reference
    if ref is not None:
        if not 3 <= len(ref.points) <= REFERENCE_MAX_POINTS:
            raise Validation(
                "measurement_reference_invalid",
                f"The reference plan needs 3 to {REFERENCE_MAX_POINTS} points",
            )
        if not 0 < ref.scale_n <= SCALE_MAX:
            raise Validation("measurement_reference_invalid", f"scale_n must be 0-{SCALE_MAX}")
        if any(
            not (isfinite(p.x) and isfinite(p.y))
            or abs(p.x) > REFERENCE_COORD_MAX
            or abs(p.y) > REFERENCE_COORD_MAX
            for p in ref.points
        ):
            raise Validation("measurement_reference_invalid", "Reference coordinates out of range")


def _bad(value: float | None, limit: float) -> bool:
    return value is not None and (not isfinite(value) or abs(value) > limit)


def reading_problem(r: Reading) -> str | None:
    """Motivo por el que una lectura no sirve, o None. No lanza: se descarta y se anota."""
    if r.kind not in READING_KINDS:
        return "kind_unknown"
    if r.seq < 0 or not 0 <= r.t_ms <= T_MAX_MS:
        return "seq_or_time_invalid"
    if r.kind == "gps":
        if r.lat is None or r.lon is None or r.accuracy_m is None:
            return "gps_incomplete"
        if not (isfinite(r.lat) and isfinite(r.lon)) or abs(r.lat) > 90 or abs(r.lon) > 180:
            return "gps_out_of_range"
        if not isfinite(r.accuracy_m) or not 0 < r.accuracy_m <= ACCURACY_MAX_M:
            return "gps_accuracy_invalid"
    if r.kind == "motion":
        if r.gyro_z_dps is None and r.accel is None and not r.step and r.pwm is None:
            return "motion_empty"
        if _bad(r.gyro_z_dps, GYRO_MAX_DPS):
            return "gyro_out_of_range"
        if r.accel is not None and (
            len(r.accel) != 3 or any(_bad(a, ACCEL_MAX_MS2) for a in r.accel)
        ):
            return "accel_out_of_range"
        if r.pwm is not None and (not isfinite(r.pwm) or not -100 <= r.pwm <= 100):
            return "pwm_out_of_range"
    return None
