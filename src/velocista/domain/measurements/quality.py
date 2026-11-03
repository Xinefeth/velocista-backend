"""Semáforo de calidad de una medición según el error de cierre.

SUPUESTO PENDIENTE DEL PO: umbrales del spike SP-05 (verde < 3 %, amarillo hasta 6 %).
"""

GREEN_MAX_PCT = 3.0
YELLOW_MAX_PCT = 6.0


def quality_for(closure_error_pct: float) -> str:
    if closure_error_pct < GREEN_MAX_PCT:
        return "green"
    if closure_error_pct <= YELLOW_MAX_PCT:
        return "yellow"
    return "red"
