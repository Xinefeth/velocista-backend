"""GPS del celular: filtrar lecturas, suavizar el recorrido y medir su error (SP-06).

Cómo se mejora la precisión desde el celular (lo que pidió el profesor):
1. Descartar lecturas con mala precisión informada (`accuracy_m` alta, típica cerca de edificios).
2. Quedarse quieto unos segundos en cada punto y promediar: el ruido se cancela.
3. Promedio ponderado por 1/precisión²: las lecturas más precisas pesan más.
4. En un recorrido, filtro de Kalman con suavizado (RTS): usa que una persona no salta 10 m.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import hypot
from statistics import median

from velocista.domain.measurements.entities import XY
from velocista.domain.measurements.geometry import to_local
from velocista.domain.shared.errors import Validation

MAX_ACCURACY_M = 25.0  # peor precisión aceptada en un recorrido
WALK_ACCEL_STD = 1.0  # m/s²: cuánto puede cambiar la velocidad de una persona (ruido del modelo)
GPS_METHODS = ("single", "mean", "filtered")


@dataclass(frozen=True)
class Fix:
    t_ms: int
    lat: float
    lon: float
    accuracy_m: float


def filter_fixes(fixes: Sequence[Fix], max_accuracy_m: float = MAX_ACCURACY_M) -> list[Fix]:
    """Quita lecturas con precisión peor que el límite o que 3 veces la mediana."""
    if not fixes:
        return []
    limit = min(max_accuracy_m, 3 * median(f.accuracy_m for f in fixes))
    return [f for f in fixes if f.accuracy_m <= limit]


def _kalman_axis(times: Sequence[float], values: Sequence[float], var: Sequence[float]):
    """Kalman de velocidad constante en un eje + suavizado RTS. Devuelve las posiciones."""
    n = len(values)
    q = WALK_ACCEL_STD**2
    xs, ps, xp, pp = [], [], [], []
    x = [values[0], 0.0]
    p = [[var[0], 0.0], [0.0, 4.0]]
    for i in range(n):
        if i > 0:
            dt = max(times[i] - times[i - 1], 1e-3)
            x = [x[0] + dt * x[1], x[1]]
            p = [
                [
                    p[0][0] + dt * (p[1][0] + p[0][1]) + dt * dt * p[1][1] + q * dt**4 / 4,
                    p[0][1] + dt * p[1][1] + q * dt**3 / 2,
                ],
                [p[1][0] + dt * p[1][1] + q * dt**3 / 2, p[1][1] + q * dt * dt],
            ]
        xp.append(x)
        pp.append(p)
        s = p[0][0] + var[i]
        k0, k1 = p[0][0] / s, p[1][0] / s
        innov = values[i] - x[0]
        x = [x[0] + k0 * innov, x[1] + k1 * innov]
        p = [
            [(1 - k0) * p[0][0], (1 - k0) * p[0][1]],
            [p[1][0] - k1 * p[0][0], p[1][1] - k1 * p[0][1]],
        ]
        xs.append(x)
        ps.append(p)
    smooth = [xs[-1]]
    for i in range(n - 2, -1, -1):
        dt = max(times[i + 1] - times[i], 1e-3)
        pf, pn = ps[i], pp[i + 1]
        det = pn[0][0] * pn[1][1] - pn[0][1] * pn[1][0]
        if abs(det) < 1e-12:
            smooth.append(xs[i])
            continue
        inv = [[pn[1][1] / det, -pn[0][1] / det], [-pn[1][0] / det, pn[0][0] / det]]
        # C = P_f · Fᵀ · P_pred⁻¹, con F = [[1, dt], [0, 1]]
        pft = [
            [pf[0][0] + dt * pf[0][1], pf[0][1]],
            [pf[1][0] + dt * pf[1][1], pf[1][1]],
        ]
        c = [
            [
                pft[0][0] * inv[0][0] + pft[0][1] * inv[1][0],
                pft[0][0] * inv[0][1] + pft[0][1] * inv[1][1],
            ],
            [
                pft[1][0] * inv[0][0] + pft[1][1] * inv[1][0],
                pft[1][0] * inv[0][1] + pft[1][1] * inv[1][1],
            ],
        ]
        nxt, pred = smooth[-1], xp[i + 1]
        d0, d1 = nxt[0] - pred[0], nxt[1] - pred[1]
        smooth.append(
            [
                xs[i][0] + c[0][0] * d0 + c[0][1] * d1,
                xs[i][1] + c[1][0] * d0 + c[1][1] * d1,
            ]
        )
    smooth.reverse()
    return [s[0] for s in smooth]


def local_points(fixes: Sequence[Fix]) -> list[XY]:
    lat0, lon0 = fixes[0].lat, fixes[0].lon
    return [to_local(f.lat, f.lon, lat0, lon0) for f in fixes]


def smooth_track(fixes: Sequence[Fix]) -> list[XY]:
    """Recorrido GPS suavizado en metros (origen en la primera lectura)."""
    if len(fixes) < 3:
        return local_points(fixes)
    pts = local_points(fixes)
    times = [f.t_ms / 1000 for f in fixes]
    # La precisión informada es un radio (~68 %); por eje la varianza es la mitad.
    var = [max(f.accuracy_m, 0.5) ** 2 / 2 for f in fixes]
    xs = _kalman_axis(times, [p.x for p in pts], var)
    ys = _kalman_axis(times, [p.y for p in pts], var)
    return [XY(x, y) for x, y in zip(xs, ys, strict=True)]


# ---------------------------------------------------------------- SP-06: error frente a la cinta


def estimate_point(fixes: Sequence[Fix], method: str, origin: tuple[float, float]) -> XY:
    """Posición de un punto donde la persona se quedó quieta, según el método."""
    pts = [to_local(f.lat, f.lon, *origin) for f in fixes]
    if method == "single":  # lo que da una app que toma una sola lectura
        return pts[0]
    if method == "mean":
        return XY(sum(p.x for p in pts) / len(pts), sum(p.y for p in pts) / len(pts))
    # filtered: descarta lecturas peores que la mediana y pondera por 1/precisión²
    cut = median(f.accuracy_m for f in fixes)
    chosen = [(p, f) for p, f in zip(pts, fixes, strict=True) if f.accuracy_m <= cut]
    w = [1 / max(f.accuracy_m, 0.5) ** 2 for _, f in chosen]
    return XY(
        sum(p.x * wi for (p, _), wi in zip(chosen, w, strict=True)) / sum(w),
        sum(p.y * wi for (p, _), wi in zip(chosen, w, strict=True)) / sum(w),
    )


def spread(fixes: Sequence[Fix]) -> dict[str, float]:
    """Cuánto 'salta' el GPS estando quieto: radio que contiene el 50 % y el 95 % de lecturas."""
    pts = local_points(fixes)
    cx = sum(p.x for p in pts) / len(pts)
    cy = sum(p.y for p in pts) / len(pts)
    r = sorted(hypot(p.x - cx, p.y - cy) for p in pts)

    def pick(q: float) -> float:
        return r[min(len(r) - 1, int(round(q * (len(r) - 1))))]

    return {"cep50_m": pick(0.5), "cep95_m": pick(0.95)}


MIN_FIXES = 3


def trial_errors(start: Sequence[Fix], end: Sequence[Fix], real_distance_m: float) -> dict:
    """Error de la distancia GPS frente a la cinta, con cada método.

    `real_distance_m` 0 = se volvió al mismo punto: el error es la distancia que marca el GPS.
    """
    if len(start) < MIN_FIXES or len(end) < MIN_FIXES:
        raise Validation(
            "gps_trial_few_fixes", f"Each point needs at least {MIN_FIXES} GPS readings"
        )
    origin = (start[0].lat, start[0].lon)
    methods = {}
    for method in GPS_METHODS:
        a = estimate_point(start, method, origin)
        b = estimate_point(end, method, origin)
        d = hypot(b.x - a.x, b.y - a.y)
        err = abs(d - real_distance_m)
        methods[method] = {
            "gps_distance_m": d,
            "error_m": err,
            "error_pct": err / real_distance_m * 100 if real_distance_m > 0 else None,
        }
    return {
        "methods": methods,
        "reported_accuracy_m": median([f.accuracy_m for f in (*start, *end)]),
        "start_spread": spread(start),
        "end_spread": spread(end),
        "fix_count": len(start) + len(end),
    }


def min_size_for(error_m: float, target_pct: float) -> float:
    """Lado mínimo para que el error del GPS sea menor que `target_pct` % de lo medido."""
    return error_m / (target_pct / 100)


def trials_summary(results: Sequence[dict], target_pct: float = 10.0) -> dict:
    """Resumen de varias pruebas: error medio y máximo por método y tamaño mínimo de terreno.

    El tamaño mínimo usa el error MÁXIMO del mejor método (criterio conservador con pocas pruebas).
    """
    if not results:
        return {"trials": 0, "methods": {}, "best_method": None, "min_side_m": None}
    by_method = {}
    for method in GPS_METHODS:
        errs = [r["methods"][method]["error_m"] for r in results]
        pcts = [r["methods"][method]["error_pct"] for r in results]
        pcts = [p for p in pcts if p is not None]
        by_method[method] = {
            "mean_error_m": sum(errs) / len(errs),
            "max_error_m": max(errs),
            "mean_error_pct": sum(pcts) / len(pcts) if pcts else None,
        }
    best = min(GPS_METHODS, key=lambda m: by_method[m]["mean_error_m"])
    single, chosen = (
        by_method["single"]["mean_error_m"],
        by_method[best]["mean_error_m"],
    )
    return {
        "trials": len(results),
        "methods": by_method,
        "best_method": best,
        "improvement_pct": (single - chosen) / single * 100 if single > 0 else None,
        "mean_reported_accuracy_m": sum(r["reported_accuracy_m"] for r in results) / len(results),
        "target_pct": target_pct,
        "min_side_m": min_size_for(by_method[best]["max_error_m"], target_pct),
    }
