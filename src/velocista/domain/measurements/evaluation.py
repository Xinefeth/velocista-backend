"""SP-07: evaluar si el modelo de precisión baja el error frente al algoritmo solo. Sin frameworks.

La evaluación responde lo que pide el spike:
1. Línea base (sin modelo): error de cierre (m y %) de cada medición con el algoritmo, es decir,
   con la calibración del paso y del giroscopio con la que se midió ESA medición.
2. Con modelo: el mismo error con los parámetros que ajustó `tune` (refuerzo simple).
3. Curva del error de cierre por intento, con y sin modelo, para el gráfico.
4. Tabla antes/después por medición y cuántas mediciones se usaron (ajuste y validación).
5. Comparación con el límite de calidad (verde: menos de 3 %) y un veredicto según el error de
   cierre medio de las mediciones de ajuste. Si no baja, se declara así y el modelo queda como
   trabajo futuro. (El modelo minimiza cierre + error frente al plano; `cost_improved` dice si
   bajó ese castigo aunque el cierre solo no baje.)

No guarda nada ni cambia el cálculo base: solo recalcula las mediciones con otros parámetros.
"""

from __future__ import annotations

from collections.abc import Sequence

from velocista.domain.measurements.compute import compute_result
from velocista.domain.measurements.quality import GREEN_MAX_PCT, quality_for
from velocista.domain.measurements.tuning import DEFAULT_ATTEMPTS, Sample, tune, with_params
from velocista.domain.shared.errors import DomainError

# Veredictos (la interfaz los traduce)
IMPROVES_GREEN = "improves_green"  # baja el error y queda bajo el límite verde
IMPROVES_NOT_GREEN = "improves_not_green"  # baja el error, pero no llega a verde
NO_IMPROVEMENT = "no_improvement"  # no baja: el modelo queda como trabajo futuro


def _errors(sample: Sample, params: dict[str, float] | None) -> dict | None:
    """Errores de una medición; con `params=None`, con la calibración propia de la medición."""
    m, readings = sample
    try:
        r = compute_result(m if params is None else with_params(m, params), readings)
    except DomainError:
        return None
    return {
        "closure_error_m": r.closure_error_m,
        "closure_error_pct": r.closure_error_pct,
        "perimeter_error_pct": r.perimeter_error_pct,
    }


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _summary(rows: Sequence[dict]) -> dict:
    """Media del error de un grupo de mediciones (ya calculadas)."""
    closure_m = _mean([r["closure_error_m"] for r in rows])
    closure_pct = _mean([r["closure_error_pct"] for r in rows])
    perimeter = [
        abs(r["perimeter_error_pct"]) for r in rows if r["perimeter_error_pct"] is not None
    ]
    return {
        "mean_closure_error_m": closure_m,
        "mean_closure_error_pct": closure_pct,
        "mean_abs_perimeter_error_pct": _mean(perimeter),
        "quality": None if closure_pct is None else quality_for(closure_pct),
    }


def _mean_closure(samples: Sequence[Sample], params: dict[str, float] | None) -> float | None:
    rows = [e for e in (_errors(s, params) for s in samples) if e is not None]
    return _mean([r["closure_error_pct"] for r in rows])


def evaluate(samples: Sequence[Sample], max_attempts: int = DEFAULT_ATTEMPTS) -> dict:
    """Compara el algoritmo solo (línea base) con el algoritmo + modelo en las mismas mediciones."""
    tuned = tune(samples, max_attempts=max_attempts)
    final = tuned["final_params"]
    holdout_id = tuned["holdout"]["measurement_id"] if tuned["holdout"] else None
    train = [s for s in samples if holdout_id is None or s[0].id != holdout_id]

    # Curva: tras cada intento, error de cierre medio con los mejores parámetros hasta ese momento
    without_model = _mean_closure(train, None)
    with_model = _mean_closure(train, tuned["initial_params"])
    curve = [{"attempt": 0, "without_model_pct": without_model, "with_model_pct": with_model}]
    for attempt in tuned["attempts"]:
        if attempt["accepted"]:
            with_model = _mean_closure(train, attempt["params"])
        curve.append(
            {
                "attempt": attempt["attempt"],
                "without_model_pct": without_model,
                "with_model_pct": with_model,
            }
        )

    rows, before_train, after_train = [], [], []
    for sample in samples:
        before, after = _errors(sample, None), _errors(sample, final)
        if before is None or after is None:
            continue
        role = "holdout" if sample[0].id == holdout_id else "train"
        rows.append(
            {"measurement_id": sample[0].id, "role": role, "before": before, "after": after}
        )
        if role == "train":
            before_train.append(before)
            after_train.append(after)

    baseline, model = _summary(before_train), _summary(after_train)
    base_pct, model_pct = baseline["mean_closure_error_pct"], model["mean_closure_error_pct"]
    improvement = None if base_pct is None or model_pct is None else base_pct - model_pct
    improved = improvement is not None and improvement > 0
    meets_green = model_pct is not None and model_pct < GREEN_MAX_PCT
    if not improved:
        verdict = NO_IMPROVEMENT
    elif meets_green:
        verdict = IMPROVES_GREEN
    else:
        verdict = IMPROVES_NOT_GREEN

    return {
        "method": tuned["method"],
        "measurement_count": len(rows),
        "train_count": len(before_train),
        "holdout_measurement_id": holdout_id,
        "green_limit_pct": GREEN_MAX_PCT,
        "initial_params": tuned["initial_params"],
        "final_params": final,
        "baseline": baseline,
        "model": model,
        "improvement_pct_points": improvement,
        "improved": improved,
        "cost_improved": bool(tuned["improved"]),
        "meets_green": meets_green,
        "generalizes": tuned["generalizes"],
        "verdict": verdict,
        "curve": curve,
        "measurements": rows,
    }
