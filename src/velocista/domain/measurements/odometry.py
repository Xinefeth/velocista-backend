"""Odometría con el celular: pasos o motor del carro para la distancia, giroscopio para el giro.

El recorrido se arma como una lista de tramos (tiempo, largo, rumbo) y luego se suman:
    x += largo · cos(rumbo)    y += largo · sin(rumbo)
Separar tramos de posiciones permite corregir el rumbo (deriva del giroscopio) y volver a sumar.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import cos, hypot, pi, radians, sin

from velocista.domain.measurements.entities import XY, Calibration, Reading

GRAVITY_MS2 = 9.80665
MAX_GAP_MS = 1000  # un hueco mayor en las lecturas del giroscopio se integra como máximo 1 s


@dataclass(frozen=True)
class Segment:
    t_ms: int
    length_m: float
    heading_rad: float


def motion_readings(readings: Sequence[Reading]) -> list[Reading]:
    return sorted((r for r in readings if r.kind == "motion"), key=lambda r: (r.t_ms, r.seq))


def heading_series(motion: Sequence[Reading], bias_dps: float) -> list[tuple[int, float]]:
    """Integra el giro restando el sesgo calibrado. Rumbo inicial 0.

    Cada lectura cubre el intervalo desde la anterior (giro = velocidad × su intervalo). No se usa
    la regla del trapecio: el celular envía el giro como cambio de orientación ÷ intervalo, con
    intervalos irregulares (1 a 100 ms), y promediar lecturas vecinas sumaba hasta 35° de más
    por vuelta.
    """
    out: list[tuple[int, float]] = []
    heading = 0.0
    prev_t: int | None = None
    for r in motion:
        if r.gyro_z_dps is None:
            continue
        rate = r.gyro_z_dps - bias_dps
        if prev_t is not None:
            dt = min(r.t_ms - prev_t, MAX_GAP_MS) / 1000
            heading += radians(rate) * dt
        out.append((r.t_ms, heading))
        prev_t = r.t_ms
    return out


def heading_at(series: Sequence[tuple[int, float]], t_ms: int) -> float:
    """Rumbo interpolado en el instante t (búsqueda binaria)."""
    if not series:
        return 0.0
    if t_ms <= series[0][0]:
        return series[0][1]
    if t_ms >= series[-1][0]:
        return series[-1][1]
    lo, hi = 0, len(series) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if series[mid][0] <= t_ms:
            lo = mid
        else:
            hi = mid
    (t0, h0), (t1, h1) = series[lo], series[hi]
    return h0 if t1 == t0 else h0 + (h1 - h0) * (t_ms - t0) / (t1 - t0)


def detect_steps(motion: Sequence[Reading], cal: Calibration) -> list[int]:
    """Instantes (ms) de cada paso.

    Si el celular ya marcó los pasos (`step=True`) se usan esos. Si no, se buscan picos del
    acelerómetro: |a| − g suavizado sube por encima del umbral, con un tiempo mínimo entre pasos,
    y se vuelve a armar cuando baja de −umbral/2 (histéresis). Rearmar en 0 no sirve: estando
    quieto en una esquina el ruido cruza 0 todo el rato y al reanudar se contaba un paso doble.
    """
    if any(r.step for r in motion):
        return [r.t_ms for r in motion if r.step]
    samples = [(r.t_ms, hypot(*r.accel) - GRAVITY_MS2) for r in motion if r.accel is not None]
    steps: list[int] = []
    armed = True
    last = -(10**12)
    window: list[float] = []
    for t, value in samples:
        window.append(value)
        if len(window) > 3:
            window.pop(0)
        smooth = sum(window) / len(window)
        if armed and smooth > cal.step_threshold_ms2 and t - last >= cal.step_min_interval_ms:
            steps.append(t)
            last = t
            armed = False
        elif smooth < -cal.step_threshold_ms2 / 2:
            armed = True
    return steps


# Umbral que se adapta a cómo pisa cada persona (se aprende al calibrar el paso).
THRESHOLD_RANGE = (0.5, 3.0)  # nunca tan bajo que cuente el temblor, ni tan alto que pierda pasos
THRESHOLD_SHARE = 0.5  # el umbral es la mitad del golpe típico de un paso
MIN_PEAK_MS2 = 0.3  # golpes más chicos son temblor de la mano, no pasos
MIN_PEAKS = 6


def step_peaks(motion: Sequence[Reading], min_gap_ms: int = 300) -> list[float]:
    """Altura de cada golpe de paso (|a| − g suavizado), uno por cada 300 ms como máximo."""
    samples = [(r.t_ms, hypot(*r.accel) - GRAVITY_MS2) for r in motion if r.accel is not None]
    smooth: list[tuple[int, float]] = []
    window: list[float] = []
    for t, value in samples:
        window.append(value)
        if len(window) > 3:
            window.pop(0)
        smooth.append((t, sum(window) / len(window)))
    peaks: list[tuple[int, float]] = []
    for i in range(1, len(smooth) - 1):
        t, v = smooth[i]
        if v < MIN_PEAK_MS2 or not (v >= smooth[i - 1][1] and v > smooth[i + 1][1]):
            continue
        if peaks and t - peaks[-1][0] < min_gap_ms:
            if v > peaks[-1][1]:  # dos picos del mismo paso: se queda el más alto
                peaks[-1] = (t, v)
            continue
        peaks.append((t, v))
    return [v for _, v in peaks]


def adaptive_threshold(walks: Sequence[Sequence[Reading]]) -> float | None:
    """Umbral de paso a la medida de la persona: la mitad de su golpe típico (mediana).

    Quien pisa suave tiene golpes bajos y con el umbral fijo (1,2) se perdían pasos; quien pisa
    fuerte lo sube y no cuenta el temblor. None si hay muy pocos pasos para aprender.
    """
    peaks = sorted(v for walk in walks for v in step_peaks(motion_readings(walk)))
    if len(peaks) < MIN_PEAKS:
        return None
    typical = peaks[len(peaks) // 2]
    low, high = THRESHOLD_RANGE
    return min(high, max(low, typical * THRESHOLD_SHARE))


def step_segments(motion: Sequence[Reading], cal: Calibration) -> list[Segment]:
    """Un tramo por paso: largo del paso calibrado y rumbo del giroscopio en ese instante."""
    length = cal.step_length_m or 0.0
    series = heading_series(motion, cal.gyro_bias_dps)
    return [Segment(t, length, heading_at(series, t)) for t in detect_steps(motion, cal)]


def car_segments(motion: Sequence[Reading], cal: Calibration) -> list[Segment]:
    """Carro sin encoders: velocidad estimada con el motor, v = k·PWM + c, por el tiempo."""
    k = cal.speed_k or 0.0
    series = heading_series(motion, cal.gyro_bias_dps)
    out: list[Segment] = []
    for a, b in zip(motion, motion[1:], strict=False):
        if a.pwm is None:
            continue
        dt = min(b.t_ms - a.t_ms, MAX_GAP_MS) / 1000
        speed = max(0.0, k * a.pwm + cal.speed_c) if a.pwm > 0 else 0.0
        mid = (a.t_ms + b.t_ms) // 2
        if speed * dt > 0:
            out.append(Segment(mid, speed * dt, heading_at(series, mid)))
    return out


def build_path(segments: Sequence[Segment]) -> list[XY]:
    """Suma los tramos desde el origen (0, 0)."""
    x = y = 0.0
    points = [XY(0.0, 0.0)]
    for s in segments:
        x += s.length_m * cos(s.heading_rad)
        y += s.length_m * sin(s.heading_rad)
        points.append(XY(x, y))
    return points


def total_turn(motion: Sequence[Reading], bias_dps: float) -> tuple[float, int, int]:
    """Giro total (rad) entre la primera y la última lectura, y sus instantes."""
    series = heading_series(motion, bias_dps)
    if len(series) < 2:
        return 0.0, 0, 0
    return series[-1][1] - series[0][1], series[0][0], series[-1][0]


TURN_TOLERANCE_RAD = radians(45)


def correct_heading_drift(
    segments: Sequence[Segment], turn_rad: float, t0: int, t1: int
) -> tuple[list[Segment], float | None]:
    """Quita la deriva del giroscopio en un recorrido cerrado.

    Al volver al inicio mirando hacia donde se empezó, el giro total debe ser un múltiplo de 360°.
    Lo que sobra es deriva; como el sesgo del giroscopio crece con el tiempo, se reparte en
    proporción al tiempo. Si el giro total no está cerca de un múltiplo de 360° (la persona no se
    volvió a orientar al final), no se corrige y se devuelve None.
    """
    turns = round(turn_rad / (2 * pi))
    if turns == 0 or t1 <= t0:
        return list(segments), None
    excess = turn_rad - turns * 2 * pi
    if abs(excess) > TURN_TOLERANCE_RAD:
        return list(segments), None
    rate = excess / (t1 - t0)
    fixed = [Segment(s.t_ms, s.length_m, s.heading_rad - rate * (s.t_ms - t0)) for s in segments]
    return fixed, excess


def distribute_closure(points: Sequence[XY]) -> list[XY]:
    """Regla de Bowditch (topografía): reparte el error de cierre en proporción a lo caminado."""
    if len(points) < 2:
        return list(points)
    cum = [0.0]
    for a, b in zip(points, points[1:], strict=False):
        cum.append(cum[-1] + hypot(b.x - a.x, b.y - a.y))
    total = cum[-1]
    if total == 0:
        return list(points)
    ex = points[-1].x - points[0].x
    ey = points[-1].y - points[0].y
    return [
        XY(p.x - ex * c / total, p.y - ey * c / total) for p, c in zip(points, cum, strict=True)
    ]
