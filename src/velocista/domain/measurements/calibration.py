"""Calibración de los sensores antes de medir (EN-35). Sin frameworks.

- Giroscopio: celular quieto ~5 s. El promedio de lo que marca es su sesgo; se resta a cada lectura.
- Paso: caminar una distancia medida con cinta (p. ej. 20 m) tres veces; paso = distancia / pasos.
- Carro sin encoders: recorrer distancias conocidas con distinto PWM y ajustar v = k·PWM + c.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import sqrt

from velocista.domain.shared.errors import Validation

GYRO_MIN_SAMPLES = 30
GYRO_MIN_DURATION_MS = 3000
GYRO_MAX_STD_DPS = 1.0  # si el ruido es mayor, el celular se movió durante la calibración
STEP_MIN_TRIALS = 3
STEP_EVEN_PACE_M = 0.02  # variación aceptable del paso entre intentos
STEP_LENGTH_RANGE = (0.3, 1.2)
CAR_MIN_TRIALS = 2


@dataclass(frozen=True)
class GyroCalibration:
    bias_dps: float
    noise_dps: float
    samples: int
    duration_ms: int


@dataclass(frozen=True)
class StepCalibration:
    step_length_m: float
    lengths_m: tuple[float, ...]
    spread_m: float
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SpeedCalibration:
    k: float
    c: float
    r2: float | None
    trials: int


def gyro_bias(samples: Sequence[tuple[int, float]]) -> GyroCalibration:
    """`samples`: (t_ms, giro °/s) con el celular quieto sobre una superficie."""
    if len(samples) < GYRO_MIN_SAMPLES:
        raise Validation(
            "calibration_few_samples",
            f"Need at least {GYRO_MIN_SAMPLES} gyroscope samples",
        )
    duration = samples[-1][0] - samples[0][0]
    if duration < GYRO_MIN_DURATION_MS:
        raise Validation(
            "calibration_too_short",
            f"Keep the phone still for at least {GYRO_MIN_DURATION_MS} ms",
        )
    values = [v for _, v in samples]
    mean = sum(values) / len(values)
    std = sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    if std > GYRO_MAX_STD_DPS:
        raise Validation(
            "calibration_phone_moved",
            "The phone moved during calibration; keep it still",
        )
    return GyroCalibration(mean, std, len(values), duration)


def step_length(trials: Sequence[tuple[float, int]]) -> StepCalibration:
    """`trials`: (distancia con cinta en m, pasos contados). Se usa el promedio de los intentos."""
    if len(trials) < STEP_MIN_TRIALS:
        raise Validation(
            "calibration_few_trials",
            f"Walk the known distance at least {STEP_MIN_TRIALS} times",
        )
    lengths = []
    for distance, steps in trials:
        if distance <= 0 or steps <= 0:
            raise Validation("calibration_invalid_trial", "Distance and steps must be above 0")
        lengths.append(distance / steps)
    mean = sum(lengths) / len(lengths)
    low, high = STEP_LENGTH_RANGE
    if not low <= mean <= high:
        raise Validation(
            "calibration_step_out_of_range",
            f"Step length {mean:.2f} m is outside {low}-{high} m; check the step count",
        )
    spread = max(lengths) - min(lengths)
    warnings = ("uneven_pace",) if spread > STEP_EVEN_PACE_M else ()
    return StepCalibration(mean, tuple(lengths), spread, warnings)


def car_speed(trials: Sequence[tuple[float, float, float]]) -> SpeedCalibration:
    """`trials`: (PWM %, distancia m, segundos). Mínimos cuadrados de v = k·PWM + c."""
    if len(trials) < CAR_MIN_TRIALS:
        raise Validation("calibration_few_trials", f"Run the car at least {CAR_MIN_TRIALS} times")
    pts = []
    for pwm, distance, seconds in trials:
        if pwm <= 0 or distance <= 0 or seconds <= 0:
            raise Validation("calibration_invalid_trial", "PWM, distance and time must be above 0")
        pts.append((pwm, distance / seconds))
    n = len(pts)
    mx = sum(p for p, _ in pts) / n
    my = sum(v for _, v in pts) / n
    sxx = sum((p - mx) ** 2 for p, _ in pts)
    if sxx == 0:  # un solo PWM: recta por el origen
        return SpeedCalibration(my / mx, 0.0, None, n)
    k = sum((p - mx) * (v - my) for p, v in pts) / sxx
    c = my - k * mx
    ss_tot = sum((v - my) ** 2 for _, v in pts)
    ss_res = sum((v - (k * p + c)) ** 2 for p, v in pts)
    return SpeedCalibration(k, c, 1 - ss_res / ss_tot if ss_tot > 0 else None, n)
