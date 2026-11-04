"""EN-32 (tarea 7.5): comprueba que las lecturas de una medición vienen de un celular real.

Script de apoyo FUERA del código de la API: solo lee `GET /api/measurements/{id}/readings`
(y `GET /api/measurements/{id}` para los datos de la medición). No escribe nada y solo usa la
biblioteca estándar.

Uso (el token va en una variable de entorno, nunca en un archivo ni en la línea de comandos):
    python scripts/check_phone_readings.py http://127.0.0.1:8000 42 --step rest
    python scripts/check_phone_readings.py https://mi-api.onrender.com 42 --login admin --step turn
    python scripts/check_phone_readings.py --file lecturas.json --step general

Pasos de la guía (`--step`): general (solo integridad y señales de dato falso), rest (reposo),
turn (giro de 360°), shake (agitar), gps (caminar 20 m), continuity (60 s), cut (corte de red).
Cada paso se mide con su propia medición, o con una parte de ella usando `--window INICIO FIN`
(segundos desde la primera lectura).

Salida: informe legible; con `--json`, el mismo informe en JSON. Código de salida: 0 todo bien
(o solo avisos), 1 alguna comprobación falló, 2 error de uso o de red.
"""

from __future__ import annotations

import argparse
import getpass
import json
import math
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from urllib import error, parse, request

TOKEN_ENV = "VELOCISTA_TOKEN"
GRAVITY = 9.80665  # m/s²
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
EARTH_RADIUS_M = 6_371_000
STEPS = ("general", "rest", "turn", "shake", "gps", "continuity", "cut")
DESKTOP_MARKS = ("windows nt", "macintosh", "x11", "cros", "linux x86_64")
MOBILE_MARKS = ("mobile", "android", "iphone", "ipad")

# Tolerancias de la guía (requirements.md, requisito 9). Son propuestas del equipo.
REST_MAG_TOL = 0.5  # m/s² alrededor de 9,8
REST_MAG_STD_MAX = 0.5  # m/s²
REST_GYRO_MEAN_MAX = 2.0  # °/s
REST_GYRO_STD_MAX = 1.5  # °/s
REST_MIN_SECONDS = 8.0
TURN_TOLERANCE = 0.10  # ±10 % de 360°
SHAKE_MIN_MAX_MS2 = 1.5 * GRAVITY
SHAKE_MIN_STD = 2.0
GPS_MIN_EXTENT_M = 10.0
GPS_MAX_EXTENT_M = 40.0
GPS_ACCURACY_MAX_M = 100.0
CONTINUITY_MIN_SECONDS = 55.0
GAP_S = 2.0  # hueco de tiempo que se considera pérdida de datos
INTEGRATION_MAX_DT_S = 1.0  # no se integra el giro a través de huecos mayores


@dataclass
class Finding:
    level: str  # OK | AVISO | FALLA | INFO
    name: str
    detail: str


# ---------------------------------------------------------------- cálculos (puros)


def _num(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def ordered(readings: list[dict]) -> list[dict]:
    """Lecturas ordenadas por seq (orden de envío del celular)."""
    return sorted(readings, key=lambda r: (r.get("seq", 0), r.get("t_ms", 0)))


def of_kind(readings: list[dict], kind: str) -> list[dict]:
    return [r for r in readings if r.get("kind") == kind]


def accel_magnitudes(readings: list[dict]) -> list[float]:
    out = []
    for r in readings:
        a = r.get("accel")
        if isinstance(a, list) and len(a) == 3:
            parts = [_num(v) for v in a]
            if all(p is not None for p in parts):
                out.append(math.sqrt(sum(p * p for p in parts)))
    return out


def gyro_values(readings: list[dict]) -> list[float]:
    return [g for r in readings if (g := _num(r.get("gyro_z_dps"))) is not None]


def integrate_gyro(readings: list[dict], bias_dps: float = 0.0) -> dict:
    """Ángulo acumulado (°) integrando gyro_z_dps - sesgo sobre t_ms con la regla del trapecio."""
    samples = sorted(
        (r["t_ms"], g)
        for r in of_kind(readings, "motion")
        if (g := _num(r.get("gyro_z_dps"))) is not None and _num(r.get("t_ms")) is not None
    )
    total = 0.0
    max_abs = 0.0
    skipped = 0
    for (t0, g0), (t1, g1) in zip(samples, samples[1:], strict=False):
        dt = (t1 - t0) / 1000.0
        if dt <= 0:
            continue
        if dt > INTEGRATION_MAX_DT_S:
            skipped += 1
            continue
        total += ((g0 - bias_dps) + (g1 - bias_dps)) / 2.0 * dt
        max_abs = max(max_abs, abs(total))
    return {
        "samples": len(samples),
        "total_deg": total,
        "max_abs_deg": max_abs,
        "skipped_intervals": skipped,
    }


def seq_report(readings: list[dict]) -> dict:
    seqs = [r["seq"] for r in readings if isinstance(r.get("seq"), int)]
    unique = sorted(set(seqs))
    if not unique:
        return {"count": 0, "first": None, "last": None, "missing": 0, "ranges": [], "repeated": 0}
    missing_ranges = []
    for a, b in zip(unique, unique[1:], strict=False):
        if b - a > 1:
            missing_ranges.append((a + 1, b - 1))
    return {
        "count": len(seqs),
        "first": unique[0],
        "last": unique[-1],
        "missing": sum(b - a + 1 for a, b in missing_ranges),
        "ranges": missing_ranges[:10],
        "repeated": len(seqs) - len(unique),
    }


def time_report(readings: list[dict]) -> dict:
    """Orden y huecos de t_ms siguiendo el orden de seq."""
    times = [r["t_ms"] for r in ordered(readings) if _num(r.get("t_ms")) is not None]
    decreasing = sum(1 for a, b in zip(times, times[1:], strict=False) if b < a)
    equal = sum(1 for a, b in zip(times, times[1:], strict=False) if b == a)
    gaps = [(b - a) / 1000.0 for a, b in zip(times, times[1:], strict=False) if b > a]
    return {
        "count": len(times),
        "first_ms": times[0] if times else None,
        "last_ms": times[-1] if times else None,
        "duration_s": (max(times) - min(times)) / 1000.0 if times else 0.0,
        "decreasing": decreasing,
        "equal": equal,
        "max_gap_s": max(gaps) if gaps else 0.0,
        "gaps_over_limit": sum(1 for g in gaps if g > GAP_S),
    }


def sampling_report(readings: list[dict], kind: str) -> dict:
    times = sorted(r["t_ms"] for r in of_kind(readings, kind) if _num(r.get("t_ms")) is not None)
    dts = [(b - a) / 1000.0 for a, b in zip(times, times[1:], strict=False) if b > a]
    if not dts:
        return {"kind": kind, "count": len(times), "median_dt_s": None, "hz": None, "cv": None}
    median = statistics.median(dts)
    mean = statistics.fmean(dts)
    cv = statistics.pstdev(dts) / mean if mean > 0 else None
    span = (times[-1] - times[0]) / 1000.0
    return {
        "kind": kind,
        "count": len(times),
        "median_dt_s": median,
        "hz": (len(times) - 1) / span if span > 0 else None,
        "cv": cv,
        "dt_constant": len(dts) >= 50 and len(set(dts)) == 1,
    }


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia aproximada (plano local) entre dos puntos, en metros."""
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return EARTH_RADIUS_M * math.hypot(x, y)


def gps_report(readings: list[dict]) -> dict:
    fixes = []
    for r in of_kind(readings, "gps"):
        lat, lon, acc = _num(r.get("lat")), _num(r.get("lon")), _num(r.get("accuracy_m"))
        if lat is not None and lon is not None:
            fixes.append((r["t_ms"], lat, lon, acc))
    if not fixes:
        return {"count": 0}
    lats = [f[1] for f in fixes]
    lons = [f[2] for f in fixes]
    accs = [f[3] for f in fixes if f[3] is not None]
    extent = distance_m(min(lats), min(lons), max(lats), max(lons))
    path = sum(distance_m(a[1], a[2], b[1], b[2]) for a, b in zip(fixes, fixes[1:], strict=False))
    return {
        "count": len(fixes),
        "lat_range_deg": max(lats) - min(lats),
        "lon_range_deg": max(lons) - min(lons),
        "extent_m": extent,
        "path_m": path,
        "unique_positions": len(set(zip(lats, lons, strict=True))),
        "acc_min": min(accs) if accs else None,
        "acc_max": max(accs) if accs else None,
        "acc_median": statistics.median(accs) if accs else None,
        "acc_unique": len(set(accs)),
    }


def select_window(readings: list[dict], start_s: float | None, end_s: float | None) -> list[dict]:
    """Lecturas entre start_s y end_s segundos desde la primera lectura (por t_ms)."""
    if start_s is None and end_s is None:
        return readings
    times = [r["t_ms"] for r in readings if _num(r.get("t_ms")) is not None]
    if not times:
        return []
    t0 = min(times)
    lo = t0 + (start_s or 0) * 1000
    hi = t0 + end_s * 1000 if end_s is not None else float("inf")
    return [r for r in readings if _num(r.get("t_ms")) is not None and lo <= r["t_ms"] <= hi]


def is_desktop_agent(user_agent: str) -> bool:
    ua = user_agent.lower()
    return any(m in ua for m in DESKTOP_MARKS) and not any(m in ua for m in MOBILE_MARKS)


# ---------------------------------------------------------------- señales de dato falso


def fake_data_findings(
    readings: list[dict], user_agent: str | None = None, meta: dict | None = None
) -> list[Finding]:
    out: list[Finding] = []
    if not readings:
        return [Finding("FALLA", "Datos", "La medición no tiene lecturas")]

    motion = of_kind(readings, "motion")
    mags = accel_magnitudes(motion)
    gyro = gyro_values(motion)
    if motion:
        if not mags and not gyro:
            out.append(
                Finding(
                    "FALLA",
                    "Sin datos de movimiento",
                    "Todas las lecturas motion traen giro y aceleración en null "
                    "(típico de un navegador de escritorio)",
                )
            )
        else:
            zero_accel = bool(mags) and all(m < 1e-9 for m in mags)
            zero_gyro = bool(gyro) and all(abs(g) < 1e-12 for g in gyro)
            if zero_accel and (zero_gyro or not gyro):
                out.append(Finding("FALLA", "Todo ceros", "Aceleración y giro valen siempre 0"))
            accel_const = len(mags) >= 20 and len(set(round(m, 9) for m in mags)) == 1
            gyro_const = len(gyro) >= 20 and len(set(gyro)) == 1
            if accel_const and not zero_accel:
                out.append(
                    Finding(
                        "FALLA",
                        "Aceleración constante",
                        f"{len(mags)} lecturas con el mismo módulo ({mags[0]:.3f} m/s²)",
                    )
                )
            if gyro_const and not zero_gyro:
                level = "FALLA" if accel_const else "AVISO"
                out.append(
                    Finding(
                        level,
                        "Giro constante",
                        f"{len(gyro)} lecturas con el mismo gyro_z_dps ({gyro[0]:.3f} °/s)",
                    )
                )
            null_accel = sum(1 for r in motion if not isinstance(r.get("accel"), list))
            if motion and null_accel / len(motion) > 0.5 and mags:
                out.append(
                    Finding(
                        "AVISO",
                        "Aceleración ausente",
                        f"{null_accel} de {len(motion)} lecturas motion sin accel",
                    )
                )
            if mags:
                mean_mag = statistics.fmean(mags)
                if 0.9 <= mean_mag <= 1.1:
                    out.append(
                        Finding(
                            "AVISO",
                            "Unidades de la aceleración",
                            f"Módulo medio {mean_mag:.2f}: parece estar en g, no en m/s²",
                        )
                    )
                elif 0 < mean_mag < 3.0 and not zero_accel:
                    out.append(
                        Finding(
                            "AVISO",
                            "Aceleración sin gravedad",
                            f"Módulo medio {mean_mag:.2f} m/s²: se espera ~9,8 con "
                            "accelerationIncludingGravity",
                        )
                    )
    else:
        out.append(Finding("INFO", "Movimiento", "No hay lecturas motion"))

    # Tiempo: seq perfecto sin variación de t_ms, fechas imposibles, reloj sintético
    seq = seq_report(readings)
    tim = time_report(readings)
    n = len(readings)
    if n >= 50 and seq["missing"] == 0 and tim["duration_s"] < 1.0:
        out.append(
            Finding(
                "FALLA",
                "Tiempo sin variación",
                f"{n} lecturas con seq perfecto pero t_ms abarca solo {tim['duration_s']:.3f} s",
            )
        )
    elif n >= 2 and tim["equal"] == n - 1:
        out.append(
            Finding("FALLA", "Tiempo sin variación", "Todas las lecturas tienen el mismo t_ms")
        )
    rate = sampling_report(readings, "motion")
    if rate.get("dt_constant"):
        out.append(
            Finding(
                "AVISO",
                "Reloj demasiado perfecto",
                "El intervalo entre lecturas motion es idéntico en todas (un sensor real "
                "tiene variación)",
            )
        )
    if tim["first_ms"] is not None:
        now_ms = time.time() * 1000
        if not 1_577_836_800_000 <= tim["first_ms"] <= now_ms + 86_400_000:
            out.append(Finding("AVISO", "Fecha improbable", f"Primer t_ms = {tim['first_ms']}"))

    # GPS constante
    gps = gps_report(readings)
    if gps["count"] >= 5:
        if gps["unique_positions"] == 1:
            out.append(
                Finding(
                    "AVISO",
                    "GPS sin variación",
                    f"{gps['count']} fixes en la misma posición (quieto o dato inventado)",
                )
            )
        if gps["acc_unique"] == 1:
            out.append(
                Finding(
                    "AVISO",
                    "Precisión constante",
                    f"accuracy_m vale siempre {gps['acc_min']} en {gps['count']} fixes",
                )
            )

    # Origen
    if meta and meta.get("source") not in (None, "phone"):
        out.append(Finding("AVISO", "Fuente", f"La medición dice source={meta['source']!r}"))
    if user_agent:
        if is_desktop_agent(user_agent):
            out.append(
                Finding("FALLA", "Agente de escritorio", "El user-agent no es de un celular")
            )
        else:
            out.append(Finding("OK", "Agente", "El user-agent parece de un celular"))
    else:
        out.append(
            Finding(
                "INFO",
                "Agente",
                "La API no guarda el user-agent; pásalo con --user-agent "
                "(navigator.userAgent en el celular) para descartar un navegador de escritorio",
            )
        )
    if not any(f.level in ("FALLA", "AVISO") for f in out):
        out.append(Finding("OK", "Datos", "Sin señales de dato falso"))
    return out


# ---------------------------------------------------------------- integridad


def integrity_findings(readings: list[dict], meta: dict | None = None) -> list[Finding]:
    out: list[Finding] = []
    seq = seq_report(readings)
    tim = time_report(readings)
    if seq["count"]:
        if seq["missing"]:
            out.append(
                Finding(
                    "FALLA",
                    "Huecos de seq",
                    f"Faltan {seq['missing']} números entre {seq['first']} y {seq['last']}; "
                    f"primeros huecos: {seq['ranges']}",
                )
            )
        else:
            out.append(
                Finding(
                    "OK", "seq", f"Sin huecos de {seq['first']} a {seq['last']} ({seq['count']})"
                )
            )
        if seq["repeated"]:
            out.append(Finding("FALLA", "seq repetido", f"{seq['repeated']} lecturas repiten seq"))
        if seq["first"] not in (0, None):
            out.append(
                Finding(
                    "AVISO", "Inicio de seq", f"La primera lectura tiene seq {seq['first']}, no 0"
                )
            )
    if tim["count"]:
        if tim["decreasing"]:
            out.append(
                Finding(
                    "FALLA",
                    "Orden de t_ms",
                    f"t_ms retrocede {tim['decreasing']} veces siguiendo seq",
                )
            )
        else:
            out.append(Finding("OK", "Orden de t_ms", "t_ms no retrocede"))
        if tim["gaps_over_limit"]:
            out.append(
                Finding(
                    "AVISO",
                    "Huecos de tiempo",
                    f"{tim['gaps_over_limit']} saltos de más de {GAP_S:.0f} s "
                    f"(el mayor: {tim['max_gap_s']:.1f} s)",
                )
            )
    if (
        meta
        and isinstance(meta.get("reading_count"), int)
        and meta["reading_count"] != len(readings)
    ):
        out.append(
            Finding(
                "AVISO",
                "Conteo",
                f"La medición dice {meta['reading_count']} lecturas y llegaron {len(readings)}",
            )
        )
    return out


# ---------------------------------------------------------------- pasos de la guía


def step_rest(readings: list[dict], bias_dps: float = 0.0) -> list[Finding]:
    motion = of_kind(readings, "motion")
    mags = accel_magnitudes(motion)
    gyro = [g - bias_dps for g in gyro_values(motion)]
    out: list[Finding] = []
    if len(mags) < 10:
        return [Finding("FALLA", "Reposo", f"Solo {len(mags)} lecturas con aceleración")]
    seconds = time_report(motion)["duration_s"]
    if seconds < REST_MIN_SECONDS:
        out.append(
            Finding("AVISO", "Duración", f"{seconds:.1f} s de datos; la guía pide 10 s de reposo")
        )
    mean_mag, std_mag = statistics.fmean(mags), statistics.pstdev(mags)
    ok_mag = abs(mean_mag - GRAVITY) <= REST_MAG_TOL
    out.append(
        Finding(
            "OK" if ok_mag else "FALLA",
            "Módulo de aceleración",
            f"media {mean_mag:.2f} m/s² (esperado {GRAVITY:.2f} ± {REST_MAG_TOL})",
        )
    )
    out.append(
        Finding(
            "OK" if std_mag <= REST_MAG_STD_MAX else "AVISO",
            "Estabilidad de la aceleración",
            f"desviación {std_mag:.3f} m/s² (máx. {REST_MAG_STD_MAX}; más indica que se movía)",
        )
    )
    if gyro:
        mean_g, std_g = statistics.fmean(gyro), statistics.pstdev(gyro)
        ok_g = abs(mean_g) <= REST_GYRO_MEAN_MAX and std_g <= REST_GYRO_STD_MAX
        out.append(
            Finding(
                "OK" if ok_g else "FALLA",
                "Giro en reposo",
                f"media {mean_g:.3f} °/s, desviación {std_g:.3f} °/s "
                f"(esperado cerca de 0; sesgo restado {bias_dps} °/s)",
            )
        )
    else:
        out.append(Finding("FALLA", "Giro en reposo", "Sin lecturas de giroscopio"))
    return out


def step_turn(readings: list[dict], bias_dps: float = 0.0) -> list[Finding]:
    res = integrate_gyro(readings, bias_dps)
    if res["samples"] < 10:
        return [Finding("FALLA", "Giro", f"Solo {res['samples']} lecturas de giroscopio")]
    total = res["total_deg"]
    low, high = 360 * (1 - TURN_TOLERANCE), 360 * (1 + TURN_TOLERANCE)
    ok = low <= abs(total) <= high
    detail = (
        f"ángulo acumulado {total:+.1f}° (esperado ±360° dentro de ±10 %: {low:.0f} a {high:.0f}); "
        f"máximo recorrido {res['max_abs_deg']:.1f}°"
    )
    out = [Finding("OK" if ok else "FALLA", "Giro de 360°", detail)]
    if not ok and 6.28 * (1 - TURN_TOLERANCE) <= abs(total) <= 6.28 * (1 + TURN_TOLERANCE):
        out.append(
            Finding("FALLA", "Unidades del giro", "El resultado es ~2π: el navegador manda rad/s")
        )
    elif not ok and abs(total) > 0 and abs(total) < 360 * (1 - TURN_TOLERANCE):
        out.append(
            Finding(
                "INFO",
                "Ayuda",
                f"Faltan {360 - abs(total):.0f}°: ¿giro incompleto, ventana mal elegida o sesgo "
                "sin restar (--bias)?",
            )
        )
    if res["skipped_intervals"]:
        out.append(
            Finding(
                "AVISO",
                "Huecos al integrar",
                f"{res['skipped_intervals']} intervalos de más de {INTEGRATION_MAX_DT_S:.0f} s "
                "no se integraron",
            )
        )
    return out


def step_shake(readings: list[dict]) -> list[Finding]:
    mags = accel_magnitudes(of_kind(readings, "motion"))
    if len(mags) < 10:
        return [Finding("FALLA", "Agitar", f"Solo {len(mags)} lecturas con aceleración")]
    peak, std = max(mags), statistics.pstdev(mags)
    ok = peak >= SHAKE_MIN_MAX_MS2 and std >= SHAKE_MIN_STD
    return [
        Finding(
            "OK" if ok else "FALLA",
            "Agitar",
            f"máximo {peak:.1f} m/s² (esperado ≥ {SHAKE_MIN_MAX_MS2:.1f}), "
            f"desviación {std:.2f} (esperado ≥ {SHAKE_MIN_STD})",
        )
    ]


def step_gps(readings: list[dict]) -> list[Finding]:
    gps = gps_report(readings)
    if gps["count"] < 3:
        return [Finding("FALLA", "GPS", f"Solo {gps['count']} fixes con posición")]
    out: list[Finding] = []
    extent = gps["extent_m"]
    if gps["unique_positions"] == 1:
        out.append(Finding("FALLA", "Variación de lat/lon", "Todas las posiciones son iguales"))
    elif extent < GPS_MIN_EXTENT_M:
        out.append(
            Finding(
                "FALLA",
                "Variación de lat/lon",
                f"Recorre solo {extent:.1f} m "
                f"(la guía camina 20 m; mínimo {GPS_MIN_EXTENT_M:.0f} m)",
            )
        )
    elif extent > GPS_MAX_EXTENT_M:
        out.append(
            Finding(
                "AVISO",
                "Variación de lat/lon",
                f"Abarca {extent:.1f} m, bastante más que los 20 m de la guía",
            )
        )
    else:
        out.append(
            Finding(
                "OK",
                "Variación de lat/lon",
                f"Abarca {extent:.1f} m (camino {gps['path_m']:.1f} m) en {gps['count']} fixes",
            )
        )
    acc = gps["acc_median"]
    if acc is None:
        out.append(Finding("FALLA", "accuracy_m", "Los fixes no traen accuracy_m"))
    else:
        plausible = 0 < gps["acc_min"] and gps["acc_max"] <= GPS_ACCURACY_MAX_M
        level = "OK" if plausible and gps["acc_unique"] > 1 else "AVISO"
        out.append(
            Finding(
                level,
                "accuracy_m",
                f"de {gps['acc_min']:.1f} a {gps['acc_max']:.1f} m, mediana {acc:.1f} m, "
                f"{gps['acc_unique']} valores distintos",
            )
        )
    return out


def step_continuity(readings: list[dict]) -> list[Finding]:
    tim, seq = time_report(readings), seq_report(readings)
    out = [
        Finding(
            "OK" if tim["duration_s"] >= CONTINUITY_MIN_SECONDS else "FALLA",
            "Duración",
            f"{tim['duration_s']:.1f} s (la guía pide 60 s; mínimo {CONTINUITY_MIN_SECONDS:.0f} s)",
        ),
        Finding(
            "OK" if seq["missing"] == 0 and seq["repeated"] == 0 else "FALLA",
            "seq sin huecos",
            f"{seq['missing']} faltan, {seq['repeated']} repetidos",
        ),
        Finding(
            "OK" if tim["decreasing"] == 0 else "FALLA",
            "t_ms creciente",
            f"{tim['decreasing']} retrocesos",
        ),
        Finding(
            "OK" if tim["gaps_over_limit"] == 0 else "FALLA",
            "Sin huecos de tiempo",
            f"{tim['gaps_over_limit']} saltos de más de {GAP_S:.0f} s",
        ),
    ]
    rate = sampling_report(readings, "motion")
    if rate["hz"]:
        out.append(
            Finding(
                "INFO",
                "Frecuencia",
                f"motion: {rate['hz']:.1f} Hz (mediana {rate['median_dt_s'] * 1000:.0f} ms entre "
                f"lecturas, variación {rate['cv']:.2f})",
            )
        )
    return out


def step_cut(readings: list[dict]) -> list[Finding]:
    tim, seq = time_report(readings), seq_report(readings)
    return [
        Finding(
            "OK" if seq["missing"] == 0 else "FALLA",
            "Sin pérdidas tras el corte",
            f"{seq['missing']} lecturas faltan en seq",
        ),
        Finding(
            "OK" if seq["repeated"] == 0 else "FALLA",
            "Sin duplicados",
            f"{seq['repeated']} lecturas repiten seq",
        ),
        Finding(
            "OK" if tim["decreasing"] == 0 else "FALLA",
            "t_ms creciente",
            f"{tim['decreasing']} retrocesos",
        ),
        Finding(
            "OK" if tim["max_gap_s"] < 8 else "AVISO",
            "Muestreo durante el corte",
            f"mayor salto de tiempo {tim['max_gap_s']:.1f} s (el celular debe seguir "
            "muestreando aunque no haya red)",
        ),
    ]


def run_step(step: str, readings: list[dict], bias_dps: float = 0.0) -> list[Finding]:
    if step == "rest":
        return step_rest(readings, bias_dps)
    if step == "turn":
        return step_turn(readings, bias_dps)
    if step == "shake":
        return step_shake(readings)
    if step == "gps":
        return step_gps(readings)
    if step == "continuity":
        return step_continuity(readings)
    if step == "cut":
        return step_cut(readings)
    return []


# ---------------------------------------------------------------- informe


def analyse(
    readings: list[dict],
    step: str = "general",
    *,
    meta: dict | None = None,
    user_agent: str | None = None,
    bias_dps: float = 0.0,
    window: tuple[float | None, float | None] = (None, None),
) -> dict:
    readings = ordered(readings)
    windowed = select_window(readings, *window)
    kinds: dict[str, int] = {}
    for r in readings:
        kinds[str(r.get("kind"))] = kinds.get(str(r.get("kind")), 0) + 1
    mags = accel_magnitudes(of_kind(windowed, "motion"))
    sections = {
        "integridad": integrity_findings(readings, meta),
        "datos_falsos": fake_data_findings(readings, user_agent, meta),
        "paso": run_step(step, windowed, bias_dps),
    }
    summary = {
        "readings": len(readings),
        "kinds": kinds,
        "window_readings": len(windowed),
        "accel_mean_ms2": statistics.fmean(mags) if mags else None,
        "gyro_integral": integrate_gyro(windowed, bias_dps),
        "seq": seq_report(readings),
        "time": time_report(readings),
        "motion_rate": sampling_report(readings, "motion"),
        "gps_rate": sampling_report(readings, "gps"),
        "gps": gps_report(windowed),
    }
    levels = [f.level for fs in sections.values() for f in fs]
    verdict = "NO APTO" if "FALLA" in levels else "APTO CON AVISOS" if "AVISO" in levels else "APTO"
    return {"step": step, "verdict": verdict, "summary": summary, "sections": sections}


def _f(value, digits=2, unit=""):
    return "—" if value is None else f"{value:.{digits}f}{unit}"


def render(result: dict, meta: dict | None = None) -> str:
    s = result["summary"]
    lines = ["INFORME DE LECTURAS DEL CELULAR", "=" * 34]
    if meta:
        lines.append(
            f"Medición {meta.get('id')}: método {meta.get('method')}, fuente {meta.get('source')}, "
            f"montaje {meta.get('mount')}, estado {meta.get('status')}"
        )
    lines.append(f"Paso de la guía: {result['step']}")
    kinds = ", ".join(f"{k} {v}" for k, v in sorted(s["kinds"].items())) or "ninguna"
    lines.append(
        f"Lecturas: {s['readings']} ({kinds}); en la ventana analizada: {s['window_readings']}"
    )
    seq, tim = s["seq"], s["time"]
    lines.append(
        f"seq: de {seq['first']} a {seq['last']}, faltan {seq['missing']}, "
        f"repetidos {seq['repeated']}"
    )
    lines.append(
        f"Tiempo: {_f(tim['duration_s'], 1)} s, retrocesos {tim['decreasing']}, "
        f"mayor salto {_f(tim['max_gap_s'], 2)} s"
    )
    mr, gr = s["motion_rate"], s["gps_rate"]
    lines.append(f"Frecuencia de muestreo: motion {_f(mr['hz'], 1)} Hz, gps {_f(gr['hz'], 2)} Hz")
    lines.append(f"Módulo medio de aceleración: {_f(s['accel_mean_ms2'], 2)} m/s²")
    g = s["gyro_integral"]
    lines.append(f"Ángulo acumulado del giro: {_f(g['total_deg'], 1)}° ({g['samples']} muestras)")
    gps = s["gps"]
    if gps["count"]:
        lines.append(
            f"GPS: {gps['count']} fixes, abarca {_f(gps['extent_m'], 1)} m, "
            f"precisión {_f(gps['acc_min'], 1)} a {_f(gps['acc_max'], 1)} m"
        )
    titles = {
        "integridad": "Integridad",
        "datos_falsos": "Señales de dato falso",
        "paso": "Veredicto del paso",
    }
    for key, findings in result["sections"].items():
        if not findings:
            continue
        lines.append("")
        lines.append(titles[key])
        for f in findings:
            lines.append(f"  [{f.level}] {f.name}: {f.detail}")
    lines.append("")
    lines.append(f"RESULTADO: {result['verdict']}")
    return "\n".join(lines)


def to_json(result: dict) -> str:
    data = dict(result)
    data["sections"] = {k: [asdict(f) for f in v] for k, v in result["sections"].items()}
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


# ---------------------------------------------------------------- red


class ApiError(Exception):
    pass


def _check_base_url(base_url: str, allow_insecure: bool) -> str:
    parts = parse.urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ApiError("La URL base debe empezar por http:// o https://")
    if parts.scheme == "http" and parts.hostname not in LOCAL_HOSTS and not allow_insecure:
        raise ApiError(
            "Con http fuera de localhost el token viajaría sin cifrar; usa https "
            "(o --allow-insecure bajo tu responsabilidad)"
        )
    return base_url.rstrip("/")


def api_request(method: str, url: str, token: str | None, body: dict | None = None):
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=60) as resp:  # noqa: S310 (esquema comprobado antes)
            return json.loads(resp.read().decode())
    except error.HTTPError as exc:
        reason = ""
        try:
            detail = json.loads(exc.read().decode()).get("detail")
            reason = detail.get("reason", "") if isinstance(detail, dict) else ""
        except (ValueError, AttributeError):
            pass
        hint = f" ({reason})" if reason else ""
        if exc.code == 401:
            raise ApiError(
                f"401 sin autorización{hint}: define {TOKEN_ENV} o usa --login USUARIO"
            ) from None
        if exc.code == 404:
            raise ApiError(f"404 no existe{hint}") from None
        raise ApiError(f"Error HTTP {exc.code}{hint}") from None
    except error.URLError as exc:
        raise ApiError(f"No se pudo conectar: {exc.reason}") from None


def login(base_url: str, username: str) -> str:
    """Pide la clave por teclado (sin eco), pide el token y descarta la clave. Nada se guarda."""
    password = getpass.getpass(f"Clave de {username}: ")
    data = api_request(
        "POST", f"{base_url}/api/auth/login", None, {"username": username, "password": password}
    )
    del password
    token = data.get("access_token") if isinstance(data, dict) else None
    if not token:
        raise ApiError("El login no devolvió un token")
    return token


def load_readings_file(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("readings", [])
    if not isinstance(data, list):
        raise ApiError('El archivo debe ser una lista de lecturas o {"readings": [...]}')
    return data


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Comprueba que las lecturas de una medición del celular son reales.",
        epilog=f"El token se lee de la variable de entorno {TOKEN_ENV}; nunca se imprime.",
    )
    p.add_argument(
        "base_url", nargs="?", help="URL base de la API, por ejemplo http://127.0.0.1:8000"
    )
    p.add_argument("measurement_id", nargs="?", type=int, help="id de la medición")
    p.add_argument("--file", help="JSON local con las lecturas (sin red ni token)")
    p.add_argument("--step", choices=STEPS, default="general", help="paso de la guía a evaluar")
    p.add_argument(
        "--window",
        nargs=2,
        type=float,
        metavar=("INICIO_S", "FIN_S"),
        help="analiza solo ese tramo (segundos desde la primera lectura)",
    )
    p.add_argument("--bias", type=float, default=0.0, help="sesgo del giroscopio a restar (°/s)")
    p.add_argument(
        "--user-agent", help="navigator.userAgent del celular, para descartar escritorio"
    )
    p.add_argument(
        "--login",
        metavar="USUARIO",
        help="pide la clave por teclado y usa el token solo en memoria",
    )
    p.add_argument("--allow-insecure", action="store_true", help="permite http fuera de localhost")
    p.add_argument("--json", action="store_true", help="imprime el informe en JSON")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    meta = None
    try:
        if args.file:
            readings = load_readings_file(args.file)
        else:
            if not args.base_url or args.measurement_id is None:
                raise ApiError("Indica BASE_URL y MEASUREMENT_ID, o usa --file")
            base = _check_base_url(args.base_url, args.allow_insecure)
            token = login(base, args.login) if args.login else os.environ.get(TOKEN_ENV)
            mid = args.measurement_id
            meta = api_request("GET", f"{base}/api/measurements/{mid}", token)
            readings = api_request("GET", f"{base}/api/measurements/{mid}/readings", token)
    except (ApiError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    window = (args.window[0], args.window[1]) if args.window else (None, None)
    result = analyse(
        readings,
        args.step,
        meta=meta,
        user_agent=args.user_agent,
        bias_dps=args.bias,
        window=window,
    )
    print(to_json(result) if args.json else render(result, meta))
    return 1 if result["verdict"] == "NO APTO" else 0


if __name__ == "__main__":
    sys.exit(main())
