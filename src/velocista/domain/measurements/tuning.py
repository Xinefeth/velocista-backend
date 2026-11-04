"""SP-07: modelo que reajusta la precisión con mediciones repetidas. Sin frameworks.

Es un ajuste por refuerzo simple (prueba y error con castigo), del tipo Twiddle:
- Acción: mover un parámetro un poco hacia arriba o hacia abajo.
- Castigo (costo): error de cierre (%) + |error del perímetro frente al plano| (%), promedio de
  todas las mediciones del mismo lugar recalculadas con los parámetros nuevos.
- Si el costo baja, se queda con el cambio y se atreve a pasos más grandes; si sube, prueba la
  dirección contraria; si tampoco mejora, achica el paso.

El modelo NO cambia el cálculo base (compute.py): solo reajusta sus parámetros.
Parámetros que ajusta y por qué:
- `gyro_bias_dps` mueve el rumbo → cambia el ERROR DE CIERRE.
- `step_length_m` (o `speed_k` del carro) estira el recorrido → cambia el ERROR FRENTE AL PLANO.
  Ojo: el largo del paso no cambia el error de cierre en %, porque estira por igual el recorrido y
  la distancia entre el final y el inicio. Por eso el costo necesita un plano o un lado con cinta.

Para no engañarse, la última medición se aparta (validación): no se usa para ajustar y se informa
su error antes y después. Si ahí no mejora, el modelo no generaliza y se declara así.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace

from velocista.domain.measurements.compute import compute_result
from velocista.domain.measurements.entities import Measurement, Reading
from velocista.domain.measurements.quality import GREEN_MAX_PCT
from velocista.domain.shared.errors import DomainError, Validation

MIN_MEASUREMENTS = 2
DEFAULT_ATTEMPTS = 40
STEP_RANGE = (0.3, 1.2)
FAILED_COST = 1e6

Sample = tuple[Measurement, Sequence[Reading]]


def _params_of(m: Measurement) -> dict[str, float]:
    cal = m.calibration
    params = {"gyro_bias_dps": cal.gyro_bias_dps}
    if m.method == "steps":
        params["step_length_m"] = cal.step_length_m or 0.7
    elif m.method == "car":
        params["speed_k"] = cal.speed_k or 0.0
    return params


def with_params(m: Measurement, params: dict[str, float]) -> Measurement:
    cal = replace(m.calibration, gyro_bias_dps=params["gyro_bias_dps"])
    if "step_length_m" in params:
        low, high = STEP_RANGE
        cal = replace(cal, step_length_m=min(high, max(low, params["step_length_m"])))
    if "speed_k" in params:
        cal = replace(cal, speed_k=max(0.0, params["speed_k"]))
    return replace(m, calibration=cal)


def _metrics(m: Measurement, readings: Sequence[Reading], params: dict[str, float]) -> dict:
    r = compute_result(with_params(m, params), readings)
    return {
        "closure_error_pct": r.closure_error_pct,
        "perimeter_error_pct": r.perimeter_error_pct,
    }


def _cost_of(metrics: dict) -> float:
    return metrics["closure_error_pct"] + abs(metrics["perimeter_error_pct"] or 0.0)


def cost(samples: Sequence[Sample], params: dict[str, float]) -> float:
    """Costo medio de las mediciones con estos parámetros (más bajo = mejor)."""
    total = 0.0
    for m, readings in samples:
        try:
            total += _cost_of(_metrics(m, readings, params))
        except DomainError:
            total += FAILED_COST
    return total / len(samples)


def tune(
    samples: Sequence[Sample],
    max_attempts: int = DEFAULT_ATTEMPTS,
    on_attempt: Callable[[dict], None] | None = None,
) -> dict:
    if len(samples) < MIN_MEASUREMENTS:
        raise Validation(
            "model_few_measurements",
            f"Need at least {MIN_MEASUREMENTS} repeated measurements",
        )
    if len({m.method for m, _ in samples}) != 1:
        raise Validation("model_mixed_methods", "All measurements must use the same method")
    if samples[0][0].method == "gps":
        raise Validation("model_gps_unsupported", "The model tunes steps or car measurements")
    holdout = samples[-1] if len(samples) >= 3 else None
    train = list(samples[:-1]) if holdout else list(samples)

    params = _params_of(samples[0][0])
    initial = dict(params)
    deltas = {
        k: (0.2 if k == "gyro_bias_dps" else 0.02 if k == "step_length_m" else 0.0005)
        for k in params
    }
    best = cost(train, params)
    baseline = best
    attempts: list[dict] = []

    def record(tried: dict[str, float], value: float, accepted: bool) -> None:
        item = {
            "attempt": len(attempts) + 1,
            "params": dict(tried),
            "cost": value,
            "best_cost": best,
            "accepted": accepted,
        }
        attempts.append(item)
        if on_attempt:
            on_attempt(item)

    while len(attempts) < max_attempts:
        for key in params:
            if len(attempts) >= max_attempts:
                break
            params[key] += deltas[key]
            value = cost(train, params)
            if value < best:
                best = value
                deltas[key] *= 1.1
                record(params, value, True)
                continue
            record(params, value, False)
            if len(attempts) >= max_attempts:
                params[key] -= deltas[key]
                break
            params[key] -= 2 * deltas[key]
            value = cost(train, params)
            if value < best:
                best = value
                deltas[key] *= 1.1
                record(params, value, True)
            else:
                record(params, value, False)
                params[key] += deltas[key]
                deltas[key] *= 0.9

    def table(rows: Sequence[Sample]) -> list[dict]:
        out = []
        for m, readings in rows:
            try:
                before, after = (
                    _metrics(m, readings, initial),
                    _metrics(m, readings, params),
                )
            except DomainError:
                continue
            out.append({"measurement_id": m.id, "before": before, "after": after})
        return out

    held = None
    if holdout:
        held = {
            "measurement_id": holdout[0].id,
            "baseline_cost": cost([holdout], initial),
            "tuned_cost": cost([holdout], params),
        }
    final_rows = table(train)
    mean_closure = (
        sum(r["after"]["closure_error_pct"] for r in final_rows) / len(final_rows)
        if final_rows
        else None
    )
    return {
        "method": samples[0][0].method,
        "initial_params": initial,
        "final_params": dict(_params_clamped(params)),
        "baseline_cost": baseline,
        "final_cost": best,
        "improved": best < baseline,
        "meets_green": mean_closure is not None and mean_closure < GREEN_MAX_PCT,
        "attempts": attempts,
        "measurements": final_rows,
        "holdout": held,
        "generalizes": None if held is None else held["tuned_cost"] <= held["baseline_cost"],
    }


def _params_clamped(params: dict[str, float]) -> dict[str, float]:
    out = dict(params)
    if "step_length_m" in out:
        out["step_length_m"] = min(STEP_RANGE[1], max(STEP_RANGE[0], out["step_length_m"]))
    if "speed_k" in out:
        out["speed_k"] = max(0.0, out["speed_k"])
    return out
