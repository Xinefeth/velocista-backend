"""Cálculo de una medición (EN-34): lecturas → recorrido → perímetro, área y error de cierre.

Pasos del cálculo (todos en metros):
1. Recorrido crudo: pasos × largo del paso (o motor del carro) con el rumbo del giroscopio;
   o las lecturas GPS filtradas y suavizadas.
2. Error de cierre: distancia entre el final y el inicio. Es la medida de calidad (semáforo).
3. Corrección: se quita la deriva del giroscopio (giro total ≠ 360°) y se reparte lo que queda
   del cierre con la regla de Bowditch.
4. Polígono: si se marcaron esquinas, los vértices son el inicio y las esquinas (más exacto que
   todo el trazo); si no, el trazo completo. Área con la fórmula de Gauss (sirve para cóncavas).
5. Escala: si se midió el primer lado con cinta, se ajusta todo el polígono a esa medida.
6. Comparación con el plano de referencia (llevado a tamaño real con la escala 1:N).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from math import degrees
from statistics import median

from velocista.domain.measurements import gps as gps_mod
from velocista.domain.measurements import odometry as odo
from velocista.domain.measurements.entities import XY, Measurement, Reading, Result
from velocista.domain.measurements.geometry import (
    area,
    dist,
    is_concave,
    path_length,
    pct_diff,
    self_crossing,
)
from velocista.domain.measurements.quality import quality_for
from velocista.domain.shared.errors import Validation

MIN_SEGMENTS = 4
DEFAULT_STEP_M = 0.70  # paso promedio de un adulto, si el celular no calibró el suyo
MAX_PATH_POINTS = 1000
GPS_TARGET_PCT = 10.0  # error del GPS aceptable frente al tamaño del lugar


def _thin(points: Sequence[XY], limit: int = MAX_PATH_POINTS) -> tuple[XY, ...]:
    if len(points) <= limit:
        return tuple(points)
    step = (len(points) - 1) / (limit - 1)
    return tuple(points[round(i * step)] for i in range(limit))


def _index_at(times: Sequence[int], t_ms: int) -> int:
    """Índice del punto del recorrido en el instante t (puntos[0] es el inicio)."""
    return sum(1 for t in times if t <= t_ms)


def _polygon(path: Sequence[XY], corner_idx: Sequence[int], closed: bool) -> list[XY]:
    last = len(path) - 1
    inner = sorted({i for i in corner_idx if 0 < i < last})
    if len(inner) >= 2:
        return [path[0], *(path[i] for i in inner)]
    return list(path[:-1]) if closed and len(path) > 2 else list(path)


def _scale_about(points: Sequence[XY], origin: XY, f: float) -> list[XY]:
    return [XY(origin.x + (p.x - origin.x) * f, origin.y + (p.y - origin.y) * f) for p in points]


def _odometry_paths(m: Measurement, readings: Sequence[Reading]):
    motion = odo.motion_readings(readings)
    cal = m.calibration
    default_step = False
    if m.method == "steps":
        if not cal.step_length_m:
            # Sin calibrar se usa un paso promedio; el lado medido o el modelo (SP-07) lo corrigen.
            cal = replace(cal, step_length_m=DEFAULT_STEP_M)
            default_step = True
        segments = odo.step_segments(motion, cal)
    else:
        if cal.speed_k is None:
            raise Validation("measurement_not_calibrated", "Calibrate the car speed first")
        segments = odo.car_segments(motion, cal)
    if len(segments) < MIN_SEGMENTS:
        raise Validation(
            "measurement_too_short",
            f"Need at least {MIN_SEGMENTS} steps or car movements",
        )
    raw = odo.build_path(segments)
    times = [s.t_ms for s in segments]
    warnings: list[str] = ["step_not_calibrated"] if default_step else []
    drift_deg = None
    corrected = raw
    turn, t0, t1 = odo.total_turn(
        motion, cal.gyro_bias_dps
    )  # rad; también si el recorrido es abierto
    turn_deg = degrees(turn)
    if m.closed:
        fixed, excess = odo.correct_heading_drift(segments, turn, t0, t1)
        if excess is None:
            warnings.append("end_heading_unknown")
        else:
            drift_deg = degrees(excess)
            corrected = odo.build_path(fixed)
        corrected = odo.distribute_closure(corrected)
    return (
        raw,
        corrected,
        times,
        len(segments) if m.method == "steps" else 0,
        drift_deg,
        turn_deg,
        warnings,
    )


def _gps_paths(m: Measurement, readings: Sequence[Reading]):
    fixes = [
        gps_mod.Fix(r.t_ms, r.lat, r.lon, r.accuracy_m)
        for r in sorted(readings, key=lambda r: (r.t_ms, r.seq))
        if r.kind == "gps"
    ]
    kept = gps_mod.filter_fixes(fixes)
    if len(kept) < MIN_SEGMENTS:
        raise Validation(
            "measurement_too_short",
            f"Need at least {MIN_SEGMENTS} GPS readings with good accuracy",
        )
    raw = gps_mod.local_points(kept)
    smooth = gps_mod.smooth_track(kept)
    corrected = odo.distribute_closure(smooth) if m.closed else smooth
    warnings = ["gps_low_accuracy_dropped"] if len(kept) < len(fixes) else []
    typical = median(f.accuracy_m for f in kept)
    return raw, smooth, corrected, [f.t_ms for f in kept[1:]], typical, warnings


def compute_result(m: Measurement, readings: Sequence[Reading]) -> Result:
    corners_t = [r.t_ms for r in readings if r.kind == "corner"]
    min_gps = None
    if m.method == "gps":
        raw, measured, corrected, times, typical, warnings = _gps_paths(m, readings)
        drift_deg, turn_deg, steps = None, None, 0
        min_gps = gps_mod.min_size_for(typical, GPS_TARGET_PCT)
    else:
        raw, corrected, times, steps, drift_deg, turn_deg, warnings = _odometry_paths(m, readings)
        measured = raw

    distance = path_length(measured)
    closure = dist(measured[0], measured[-1])
    closure_pct = closure / distance * 100 if distance > 0 else 0.0
    corner_idx = [_index_at(times, t) for t in corners_t]

    raw_poly = _polygon(measured, corner_idx, m.closed)
    poly = _polygon(corrected, corner_idx, m.closed)
    scale = None
    if m.tape_side_m:
        inner = sorted({i for i in corner_idx if 0 < i < len(corrected) - 1})
        if inner:
            side = dist(corrected[0], corrected[inner[0]])
            if side > 0:
                scale = m.tape_side_m / side
                poly = _scale_about(poly, corrected[0], scale)
                corrected = _scale_about(corrected, corrected[0], scale)
        else:
            warnings.append("scale_needs_corner")

    perimeter = path_length(poly, closed=m.closed)
    surface = area(poly) if m.closed else 0.0
    if min_gps is not None and m.closed and perimeter / 4 < min_gps:
        warnings.append("gps_space_too_small")

    ref_p = ref_a = None
    if m.reference is not None:
        ref = m.reference.real_points()
        ref_p, ref_a = path_length(ref, closed=True), area(ref)

    return Result(
        method=m.method,
        reading_count=len(readings),
        step_count=steps,
        distance_m=distance,
        closure_error_m=closure,
        closure_error_pct=closure_pct,
        heading_drift_deg=drift_deg,
        raw_perimeter_m=path_length(raw_poly, closed=m.closed),
        raw_area_m2=area(raw_poly) if m.closed else 0.0,
        perimeter_m=perimeter,
        area_m2=surface,
        scale_factor=scale,
        corners=len({i for i in corner_idx if 0 < i < len(corrected) - 1}),
        concave=is_concave(poly),
        self_crossing=self_crossing(poly) if len(poly) <= 300 else False,
        quality=quality_for(closure_pct),
        reference_perimeter_m=ref_p,
        reference_area_m2=ref_a,
        perimeter_error_pct=pct_diff(perimeter, ref_p) if ref_p else None,
        area_error_pct=pct_diff(surface, ref_a) if ref_a else None,
        min_gps_size_m=min_gps,
        turn_total_deg=turn_deg,
        warnings=tuple(warnings),
        raw_path=_thin(raw),
        corrected_path=_thin(corrected),
        polygon=_thin(poly),
    )
