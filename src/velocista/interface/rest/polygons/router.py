"""Controlador REST de figuras sin sensores (EN-42). Solo valida formato y delega en el dominio.

- POST /api/polygons/solve        lados y ángulos conocidos → figura cerrada (HU-43, CU-5)
- POST /api/polygons/from-points  puntos marcados → lados, ángulos, perímetro y área (HU-41, CU-3)

No guarda nada: el plano resultante se guarda como pista o referencia desde la consola.
"""

from __future__ import annotations

from fastapi import APIRouter

from velocista.domain.measurements import polygon
from velocista.domain.measurements.entities import XY
from velocista.interface.rest.errors import error_responses
from velocista.interface.rest.polygons.schemas import PolygonOut, PolygonPointsIn, PolygonSolveIn

UNAUTHORIZED = "Missing, expired or tampered token (`unauthorized`)"
INVALID = "Invalid body or a domain rule failed (`{detail: {reason, detail}}`)"

router = APIRouter(prefix="/api/polygons", tags=["polygons"])


@router.post(
    "/solve",
    response_model=PolygonOut,
    operation_id="solvePolygon",
    summary="Close a figure from known sides and angles",
    description=(
        "Calculates the missing sides and angles (null), closes the figure and returns its "
        "points, perimeter and area, also for concave figures (an L). The interior angles must "
        "add up to (n - 2) * 180 degrees. At most one angle can be missing, or the two at both "
        "ends of one side; at most two non-parallel sides can be missing "
        "(`polygon_underdetermined`). "
        "Data that do not close the figure or sides that cross are reported in `warnings`. "
        "Saves nothing."
    ),
    responses=error_responses({401: UNAUTHORIZED, 422: INVALID}),
)
def solve_polygon(data: PolygonSolveIn) -> PolygonOut:
    return PolygonOut.from_entity(polygon.solve(data.sides_m, data.angles_deg))


@router.post(
    "/from-points",
    response_model=PolygonOut,
    operation_id="measurePolygonPoints",
    summary="Sides, angles, perimeter and area of marked points",
    description=(
        "For areas of any shape marked point by point. Keeps the order of the points and warns "
        "with `self_crossing` when two sides cross (the area would not be valid). Points on one "
        "line answer 422 (`polygon_degenerate`). Saves nothing."
    ),
    responses=error_responses({401: UNAUTHORIZED, 422: INVALID}),
)
def polygon_from_points(data: PolygonPointsIn) -> PolygonOut:
    return PolygonOut.from_entity(polygon.from_points([XY(p.x, p.y) for p in data.points]))
