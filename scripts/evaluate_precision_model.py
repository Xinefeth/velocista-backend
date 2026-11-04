"""SP-07: evaluate the precision model on measurements already saved in the database.

Usage (with POSTGRES_* or DATABASE_URL pointing at the database):
    python scripts/evaluate_precision_model.py 10 11 12 13
    python scripts/evaluate_precision_model.py 10 11 12 13 --attempts 60 --json

Prints the baseline (algorithm alone) against the model and the verdict. Saves nothing.
"""

from __future__ import annotations

import argparse
import json

from velocista.application.measurements.use_cases import PrecisionModelService
from velocista.infrastructure.persistence.db import SessionLocal
from velocista.infrastructure.persistence.repositories.measurements_repository import (
    SqlAlchemyMeasurementsRepository,
)


def _fmt(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def report(out: dict) -> str:
    base, model = out["baseline"], out["model"]
    lines = [
        f"Mediciones: {out['measurement_count']} ({out['train_count']} para ajustar, "
        f"validación: {out['holdout_measurement_id'] or 'ninguna'})",
        f"Parámetros: {out['initial_params']} -> {out['final_params']}",
        "",
        "| | Error de cierre (m) | Error de cierre (%) | Error vs plano (%) | Calidad |",
        "|---|---|---|---|---|",
        f"| Sin modelo | {_fmt(base['mean_closure_error_m'])} | "
        f"{_fmt(base['mean_closure_error_pct'])} | "
        f"{_fmt(base['mean_abs_perimeter_error_pct'])} | {base['quality']} |",
        f"| Con modelo | {_fmt(model['mean_closure_error_m'])} | "
        f"{_fmt(model['mean_closure_error_pct'])} | "
        f"{_fmt(model['mean_abs_perimeter_error_pct'])} | {model['quality']} |",
        "",
        "| Medición | Rol | Cierre antes (%) | Cierre después (%) "
        "| Plano antes (%) | Plano después (%) |",
        "|---|---|---|---|---|---|",
    ]
    for row in out["measurements"]:
        b, a = row["before"], row["after"]
        lines.append(
            f"| {row['measurement_id']} | {row['role']} | {_fmt(b['closure_error_pct'])} | "
            f"{_fmt(a['closure_error_pct'])} | {_fmt(b['perimeter_error_pct'])} | "
            f"{_fmt(a['perimeter_error_pct'])} |"
        )
    lines += [
        "",
        f"Mejora: {_fmt(out['improvement_pct_points'])} puntos · verde (< "
        f"{out['green_limit_pct']} %): {out['meets_green']} · generaliza: {out['generalizes']}",
        f"Veredicto: {out['verdict']}",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ids", type=int, nargs="+", help="repeated measurements, holdout last")
    parser.add_argument("--attempts", type=int, default=40)
    parser.add_argument("--json", action="store_true", help="print the raw evaluation")
    args = parser.parse_args()
    with SessionLocal() as session:
        service = PrecisionModelService(SqlAlchemyMeasurementsRepository(session))
        out = service.evaluate(args.ids, max_attempts=args.attempts)
    print(json.dumps(out, indent=2, default=str) if args.json else report(out))


if __name__ == "__main__":
    main()
