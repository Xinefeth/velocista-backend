"""Generador de lecturas de celular para pruebas de `measurements` (EN-34, EN-35, SP-06, SP-07).

Simula a una persona que camina el borde de un polígono con el celular plano frente al pecho:
- acelerómetro: |a| = g + A·sin(2π·cadencia·t) mientras camina (un pico por paso);
- giroscopio: giro real en cada esquina (1 s) + sesgo fijo + ruido;
- al final se gira para mirar hacia donde empezó (giro total = 360°);
- una lectura `corner` en cada esquina, como si tocara "Marcar esquina".
Solo sirve para pruebas: ningún resultado final sale de aquí.
"""

from __future__ import annotations

import random
from math import atan2, cos, degrees, hypot, pi, radians, sin

from velocista.domain.measurements.entities import (
    XY,
    Calibration,
    Measurement,
    Reading,
    Reference,
)
from velocista.domain.measurements.gps import Fix
from velocista.domain.measurements.odometry import GRAVITY_MS2

RECT_10x6 = (XY(0, 0), XY(10, 0), XY(10, 6), XY(0, 6))
L_SHAPE = (XY(0, 0), XY(6, 0), XY(6, 2), XY(2, 2), XY(2, 8), XY(0, 8))
HZ = 50


def _turn(a: float, b: float) -> float:
    d = b - a
    while d > pi:
        d -= 2 * pi
    while d <= -pi:
        d += 2 * pi
    return d


def walk_readings(
    poly=RECT_10x6,
    step_m: float = 0.7,
    cadence_hz: float = 1.8,
    gyro_bias_dps: float = 0.0,
    gyro_noise_dps: float = 0.0,
    face_start: bool = True,
    mark_corners: bool = True,
    still_s: float = 1.0,
    seed: int = 1,
    step_accel: float = 3.0,  # fuerza del golpe de cada paso (m/s²); suave ~1, fuerte ~5
) -> list[Reading]:
    rng = random.Random(seed)
    out: list[Reading] = []
    t = 1_000_000.0  # ms
    dt = 1000 / HZ
    speed = step_m * cadence_hz
    phase = 0.0

    def emit(rate_dps: float, walking: bool) -> None:
        nonlocal t, phase
        if walking:
            phase += 2 * pi * cadence_hz * dt / 1000
        mag = GRAVITY_MS2 + (step_accel * sin(phase) if walking else 0.0) + rng.gauss(0, 0.05)
        gz = rate_dps + gyro_bias_dps + (rng.gauss(0, gyro_noise_dps) if gyro_noise_dps else 0.0)
        out.append(Reading(len(out), int(t), "motion", gyro_z_dps=gz, accel=(0.0, 0.0, mag)))
        t += dt

    def stand(seconds: float) -> None:
        for _ in range(int(seconds * HZ)):
            emit(0.0, False)

    def turn(angle_rad: float) -> None:
        for _ in range(HZ):
            emit(degrees(angle_rad), False)

    n = len(poly)
    headings = [
        atan2(poly[(i + 1) % n].y - poly[i].y, poly[(i + 1) % n].x - poly[i].x) for i in range(n)
    ]
    stand(still_s)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        samples = round(hypot(b.x - a.x, b.y - a.y) / speed * HZ)
        for _ in range(samples):
            emit(0.0, True)
        last = i == n - 1
        if not last or face_start:
            turn(_turn(headings[i], headings[(i + 1) % n]))
        if not last and mark_corners:
            out.append(Reading(len(out), int(t), "corner"))
    stand(still_s)
    return out


def measurement(
    method: str = "steps",
    step_length_m: float | None = 0.7,
    gyro_bias_dps: float = 0.0,
    reference=RECT_10x6,
    tape_side_m: float | None = None,
    mid: int | None = None,
    **kw,
) -> Measurement:
    return Measurement(
        method=method,
        source="phone",
        mount="robot" if method == "car" else "hand",
        place_name="aula",
        device_id="phone-1",
        reference=Reference(tuple(reference)) if reference else None,
        tape_side_m=tape_side_m,
        calibration=Calibration(gyro_bias_dps=gyro_bias_dps, step_length_m=step_length_m, **kw),
        id=mid,
    )


LAT0, LON0 = -8.1116, -79.0287  # Trujillo
M_PER_DEG = 111_195.0


def latlon(x: float, y: float) -> tuple[float, float]:
    return LAT0 + y / M_PER_DEG, LON0 + x / (M_PER_DEG * cos(radians(LAT0)))


def still_fixes(x, y, n=20, sigma=4.0, bias=(0.0, 0.0), seed=1, t0=0, bad_every=0) -> list[Fix]:
    """Lecturas GPS de una persona quieta en (x, y): ruido gaussiano + sesgo + algunas malas."""
    rng = random.Random(seed)
    fixes = []
    for i in range(n):
        s = sigma * (4 if bad_every and i % bad_every == bad_every - 1 else 1)
        lat, lon = latlon(x + bias[0] + rng.gauss(0, s), y + bias[1] + rng.gauss(0, s))
        fixes.append(Fix(t0 + i * 1000, lat, lon, s * 1.5))
    return fixes


def gps_walk_readings(poly, speed=1.2, sigma=3.0, seed=1) -> list[Reading]:
    """Recorrido GPS a 1 Hz por el borde del polígono, volviendo al inicio."""
    rng = random.Random(seed)
    out: list[Reading] = []
    t = 0
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        k = max(2, round(hypot(b.x - a.x, b.y - a.y) / speed))
        for s in range(k):
            f = s / k
            x = a.x + (b.x - a.x) * f + rng.gauss(0, sigma)
            y = a.y + (b.y - a.y) * f + rng.gauss(0, sigma)
            lat, lon = latlon(x, y)
            out.append(Reading(len(out), t, "gps", lat=lat, lon=lon, accuracy_m=sigma * 1.5))
            t += 1000
    lat, lon = latlon(poly[0].x + rng.gauss(0, sigma), poly[0].y + rng.gauss(0, sigma))
    out.append(Reading(len(out), t, "gps", lat=lat, lon=lon, accuracy_m=sigma * 1.5))
    return out


def gps_walk_with_corners(poly, speed=1.2, sigma=3.0, seed=1, skip=()) -> list[Reading]:
    """Como gps_walk_readings, pero marca una esquina en cada vértice (salvo el inicio).

    `skip`: índices de vértices donde la persona olvida marcar la esquina.
    """
    rng = random.Random(seed)
    out: list[Reading] = []
    t = 0
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if i > 0 and i not in skip:
            out.append(Reading(len(out), t, "corner"))
        k = max(2, round(hypot(b.x - a.x, b.y - a.y) / speed))
        for s in range(k):
            f = s / k
            x = a.x + (b.x - a.x) * f + rng.gauss(0, sigma)
            y = a.y + (b.y - a.y) * f + rng.gauss(0, sigma)
            lat, lon = latlon(x, y)
            out.append(Reading(len(out), t, "gps", lat=lat, lon=lon, accuracy_m=sigma * 1.5))
            t += 1000
    lat, lon = latlon(poly[0].x + rng.gauss(0, sigma), poly[0].y + rng.gauss(0, sigma))
    out.append(Reading(len(out), t, "gps", lat=lat, lon=lon, accuracy_m=sigma * 1.5))
    return out


def key_shape() -> tuple[XY, ...]:
    """Figura «llave»: octágono de 30 m, cuello de 4 m × 25 m y un pie en L (área ≈ 1006 m²)."""
    octagon = [
        XY(16.24 * cos(radians(a)), 45 + 16.24 * sin(radians(a)))
        for a in (292.5, 337.5, 22.5, 67.5, 112.5, 157.5, 202.5, 247.5)
    ]
    foot = [XY(-2, 30), XY(-2, 5), XY(-30, 5), XY(-30, 0), XY(2, 0), XY(2, 30)]
    return (*octagon, *foot)


def scaled(poly, k: float):
    return tuple(XY(p.x * k, p.y * k) for p in poly)


def true_path(poly) -> list[XY]:
    """Puntos del borde cada ~1 m (para comparar recorridos GPS)."""
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        k = max(2, round(hypot(b.x - a.x, b.y - a.y)))
        out += [XY(a.x + (b.x - a.x) * s / k, a.y + (b.y - a.y) * s / k) for s in range(k)]
    return out
