"""Análisis del error del GPS por entorno, distancia, espera y precisión (CU-4).

Responde «¿desde qué tamaño de espacio sirve el GPS?» con las pruebas guardadas (`gps_trial`):

- lado mínimo recomendado por cada entorno (abierto, edificios, árboles, interior);
- error frente a la distancia de la cinta (¿crece con la distancia?);
- umbral de precisión para esperar antes de medir y cuánto conviene quedarse quieto;
- precisión que informa el celular frente al error real;
- aviso cuando hay menos pruebas que el mínimo.

Todo se calcula con las lecturas guardadas de cada prueba, así que las pruebas viejas ganan el
análisis nuevo sin migración. Los umbrales NO están cableados: vienen de `GpsConfig`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil, hypot, sqrt

from velocista.domain.measurements import gps as gps_mod
from velocista.domain.measurements.entities import ENVIRONMENTS
from velocista.domain.measurements.gps import GPS_METHODS, MIN_FIXES, Fix

# El error «crece» con la distancia si la última banda con datos supera esto a la primera.
TREND_FACTOR = 1.5
TREND_MIN_GAP_M = 0.5


@dataclass(frozen=True)
class GpsConfig:
    """Parámetros del análisis (configurables por entorno del servidor y por consulta)."""

    target_pct: float = 10.0
    min_trials: int = 5
    accuracy_thresholds_m: tuple[float, ...] = (3.0, 5.0, 10.0, 20.0)
    wait_seconds: tuple[float, ...] = (5.0, 10.0, 20.0)
    distance_bands_m: tuple[float, ...] = (5.0, 20.0, 50.0)

    def to_dict(self) -> dict:
        return {
            "target_pct": self.target_pct,
            "min_trials": self.min_trials,
            "accuracy_thresholds_m": list(self.accuracy_thresholds_m),
            "wait_seconds": list(self.wait_seconds),
            "distance_bands_m": list(self.distance_bands_m),
        }


@dataclass(frozen=True)
class TrialRow:
    """Lo mínimo que el resumen necesita de una prueba."""

    environment: str
    real_distance_m: float
    result: dict


def _key(x: float) -> str:
    return f"{x:g}"


# ---------------------------------------------------------------- por prueba


def _mean_error(start: Sequence[Fix], end: Sequence[Fix], real_m: float) -> float | None:
    """Error de la distancia con el método `mean`; None si falta alguna lectura mínima."""
    if len(start) < MIN_FIXES or len(end) < MIN_FIXES:
        return None
    origin = (start[0].lat, start[0].lon)
    a = gps_mod.estimate_point(start, "mean", origin)
    b = gps_mod.estimate_point(end, "mean", origin)
    return abs(hypot(b.x - a.x, b.y - a.y) - real_m)


def _first_seconds(fixes: Sequence[Fix], seconds: float) -> list[Fix]:
    ordered = sorted(fixes, key=lambda f: f.t_ms)
    if not ordered:
        return []
    limit = ordered[0].t_ms + seconds * 1000
    return [f for f in ordered if f.t_ms <= limit]


def trial_analysis(start: Sequence[Fix], end: Sequence[Fix], real_m: float, cfg: GpsConfig) -> dict:
    """Resultado de una prueba: el de SP-06 más `by_wait` y `by_accuracy`.

    - `by_wait[s]`: error si solo se usan los primeros `s` segundos quietos en cada punto.
    - `by_accuracy[t]`: error si solo se usan lecturas con `accuracy_m` ≤ `t`.
    Ambos con el promedio de lecturas (`mean`). `usable` = quedan al menos 3 lecturas por punto.
    """
    result = gps_mod.trial_errors(start, end, real_m)

    by_wait = {}
    for s in cfg.wait_seconds:
        err = _mean_error(_first_seconds(start, s), _first_seconds(end, s), real_m)
        by_wait[_key(s)] = {"usable": err is not None, "error_m": err}

    by_accuracy = {}
    total = len(start) + len(end)
    for t in cfg.accuracy_thresholds_m:
        a = [f for f in start if f.accuracy_m <= t]
        b = [f for f in end if f.accuracy_m <= t]
        err = _mean_error(a, b, real_m)
        by_accuracy[_key(t)] = {
            "usable": err is not None,
            "kept": len(a) + len(b),
            "total": total,
            "error_m": err,
        }
    return {**result, "by_wait": by_wait, "by_accuracy": by_accuracy}


# ---------------------------------------------------------------- resumen


def _avg(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _bands(edges: Sequence[float]) -> list[tuple[float, float | None]]:
    lows = [0.0, *edges]
    highs: list[float | None] = [*edges, None]
    return list(zip(lows, highs, strict=True))


def _error_of(row: TrialRow, method: str) -> float:
    return row.result["methods"][method]["error_m"]


def _distance_bands(rows: Sequence[TrialRow], method: str | None, cfg: GpsConfig) -> list[dict]:
    out = []
    for low, high in _bands(cfg.distance_bands_m):
        inside = [
            r
            for r in rows
            if r.real_distance_m >= low and (high is None or r.real_distance_m < high)
        ]
        errs = [_error_of(r, method) for r in inside] if method else []
        pcts = [
            p
            for r in inside
            if method and (p := r.result["methods"][method]["error_pct"]) is not None
        ]
        out.append(
            {
                "from_m": low,
                "to_m": high,
                "trials": len(inside),
                "mean_error_m": _avg(errs),
                "max_error_m": max(errs) if errs else None,
                "mean_error_pct": _avg(pcts),
            }
        )
    return out


def _trend(bands: Sequence[dict]) -> str | None:
    filled = [b for b in bands if b["trials"] > 0]
    if len(filled) < 2:
        return None
    first, last = filled[0]["mean_error_m"], filled[-1]["mean_error_m"]
    if last > first * TREND_FACTOR and last - first > TREND_MIN_GAP_M:
        return "grows"
    return "flat"


def _by_accuracy(rows: Sequence[TrialRow], cfg: GpsConfig) -> tuple[list[dict], float | None]:
    out = []
    for t in cfg.accuracy_thresholds_m:
        used = [r.result["by_accuracy"][_key(t)] for r in rows]
        used = [u for u in used if u["usable"]]
        errs = [u["error_m"] for u in used]
        out.append(
            {
                "max_accuracy_m": t,
                "usable_trials": len(used),
                "mean_error_m": _avg(errs),
                "max_error_m": max(errs) if errs else None,
                "mean_kept_pct": _avg([u["kept"] / u["total"] * 100 for u in used]),
            }
        )
    # Recomendado: el de menor error medio entre los que sirven en al menos la mitad de las
    # pruebas (así no se recomienda un umbral que casi nunca se alcanza). Empate: el más laxo.
    enough = [o for o in out if o["usable_trials"] >= max(1, ceil(len(rows) / 2))]
    best = min(enough, key=lambda o: (o["mean_error_m"], -o["max_accuracy_m"]), default=None)
    return out, best["max_accuracy_m"] if best else None


def _by_wait(rows: Sequence[TrialRow], cfg: GpsConfig) -> list[dict]:
    out = []
    for s in cfg.wait_seconds:
        used = [r.result["by_wait"][_key(s)] for r in rows]
        errs = [u["error_m"] for u in used if u["usable"]]
        out.append(
            {
                "seconds": s,
                "usable_trials": len(errs),
                "mean_error_m": _avg(errs),
                "max_error_m": max(errs) if errs else None,
            }
        )
    return out


def _reported_vs_real(rows: Sequence[TrialRow]) -> dict | None:
    """Precisión que informa el celular frente al error real de una sola lectura.

    La precisión informada es el radio de UN punto; la distancia usa dos puntos, así que el error
    esperado de la distancia es √2 × precisión. `ratio` > 1 significa que el celular es optimista.
    """
    if not rows:
        return None
    reported = [r.result["reported_accuracy_m"] for r in rows]
    expected = [sqrt(2) * a for a in reported]
    real = [_error_of(r, "single") for r in rows]
    mean_expected = sum(expected) / len(expected)
    mean_real = sum(real) / len(real)
    ratio = mean_real / mean_expected if mean_expected > 0 else None
    return {
        "trials": len(rows),
        "mean_reported_accuracy_m": sum(reported) / len(reported),
        "mean_expected_error_m": mean_expected,
        "mean_real_error_m": mean_real,
        "ratio": ratio,
        "optimistic": ratio > 1 if ratio is not None else None,
    }


def _environment_entry(rows: Sequence[TrialRow], cfg: GpsConfig) -> dict:
    s = gps_mod.trials_summary([r.result for r in rows], cfg.target_pct)
    best = s["best_method"]
    methods = s["methods"]
    return {
        "trials": len(rows),
        "enough_data": len(rows) >= cfg.min_trials,
        "missing_trials": max(0, cfg.min_trials - len(rows)),
        "best_method": best,
        "mean_error_m": methods[best]["mean_error_m"],
        "max_error_m": methods[best]["max_error_m"],
        "min_side_m": s["min_side_m"],
        "methods": methods,
    }


def _conclusion(summary: dict, environments: dict[str, dict], cfg: GpsConfig) -> dict:
    """Conclusión en español. Solo da por buenos los entornos con pruebas suficientes."""
    n = summary["trials"]
    ready = [env for env in ENVIRONMENTS if environments.get(env, {}).get("enough_data")]
    base = {
        "best_method": summary["best_method"],
        "min_side_m": summary["min_side_m"],
        "trials": n,
        "ready_environments": ready,
    }
    if n == 0:
        text = (
            "Todavía no hay pruebas de GPS. Registra pruebas contra una distancia medida con "
            "cinta en lugares conocidos."
        )
        return {"code": "no_data", **base, "text": text}
    if not ready:
        text = (
            f"Hay {n} pruebas, pero ningún entorno llega a {cfg.min_trials}. Con estos datos el "
            f"mejor método es «{summary['best_method']}» y el lado mínimo provisional es "
            f"{summary['min_side_m']:.0f} m (error menor que {cfg.target_pct:g} %)."
        )
        return {"code": "insufficient_data", **base, "text": text}
    parts = [
        f"en «{env}» el GPS se equivoca menos de {cfg.target_pct:g} % desde "
        f"{environments[env]['min_side_m']:.0f} m de lado"
        for env in ready
    ]
    text = f"Con {n} pruebas: " + "; ".join(parts) + "."
    pending = [env for env in environments if env not in ready]
    if pending:
        text += " Faltan pruebas en: " + ", ".join(f"«{e}»" for e in pending) + "."
    return {"code": "ok", **base, "text": text}


def _warnings(summary_rows: Sequence[TrialRow], cfg: GpsConfig) -> list[dict]:
    out = []
    n = len(summary_rows)
    if n < cfg.min_trials:
        out.append(
            {
                "code": "gps_few_trials",
                "environment": None,
                "message": f"Hay {n} pruebas; se recomiendan al menos {cfg.min_trials}.",
            }
        )
    for env in ENVIRONMENTS:
        count = sum(1 for r in summary_rows if r.environment == env)
        if 0 < count < cfg.min_trials:
            out.append(
                {
                    "code": "gps_environment_few_trials",
                    "environment": env,
                    "message": (
                        f"En «{env}» hay {count} pruebas; se recomiendan al menos "
                        f"{cfg.min_trials} para fiarse del tamaño mínimo."
                    ),
                }
            )
    return out


def summarize(rows: Sequence[TrialRow], cfg: GpsConfig) -> dict:
    """Resumen completo: lo de SP-06 sin cambios más los campos de CU-4."""
    base = gps_mod.trials_summary([r.result for r in rows], cfg.target_pct)
    base.setdefault("improvement_pct", None)
    base.setdefault("mean_reported_accuracy_m", None)
    base.setdefault("target_pct", cfg.target_pct)

    by_env_rows: dict[str, list[TrialRow]] = {}
    for r in rows:
        by_env_rows.setdefault(r.environment, []).append(r)

    bands = _distance_bands(rows, base["best_method"], cfg)
    by_accuracy, recommended = _by_accuracy(rows, cfg)
    environments = {env: _environment_entry(g, cfg) for env, g in by_env_rows.items()}
    return {
        **base,
        "by_environment": {
            env: _environment_summary_methods(group, cfg) for env, group in by_env_rows.items()
        },
        "config": cfg.to_dict(),
        "environments": environments,
        "by_distance": bands,
        "error_trend": _trend(bands),
        "by_accuracy": by_accuracy,
        "recommended_accuracy_m": recommended,
        "by_wait": _by_wait(rows, cfg),
        "reported_vs_real": _reported_vs_real(rows),
        "warnings": _warnings(rows, cfg),
        "conclusion": _conclusion(base, environments, cfg),
    }


def _environment_summary_methods(rows: Sequence[TrialRow], cfg: GpsConfig) -> dict:
    """`by_environment` de SP-06: solo los errores por método (forma que ya usan los clientes)."""
    return gps_mod.trials_summary([r.result for r in rows], cfg.target_pct)["methods"]


__all__ = ["GPS_METHODS", "GpsConfig", "TrialRow", "summarize", "trial_analysis"]
