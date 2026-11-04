"""EN-42: contorno desde lados y ángulos conocidos, y medidas de una figura por puntos.

Convención (recorrido antihorario, como se dibuja un plano):
- El lado `i` va del vértice `i` al vértice `i + 1`; el último vuelve al vértice 0.
- El ángulo `i` es el ángulo INTERIOR en el vértice `i` (entre el lado `i - 1` y el lado `i`).
  Una esquina entrante de una figura en L mide 270°.
- El lado 0 sale del origen hacia +x. Al llegar al vértice `i` se gira `180° - ángulo_i`.

Qué datos pueden faltar (`None`):
- Ángulos: la suma de los interiores debe ser (n − 2) × 180°, así que falta a lo sumo uno.
  O bien faltan exactamente los dos ángulos de los extremos de un mismo lado (se cierra la figura
  con ese lado, que también puede faltar).
- Lados: con todos los ángulos, la figura debe cerrar (2 ecuaciones), así que faltan a lo sumo dos
  lados que no sean paralelos.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, radians, sin

from velocista.domain.measurements.entities import XY
from velocista.domain.measurements.geometry import area, is_concave, path_length, self_crossing
from velocista.domain.shared.errors import Validation

MIN_SIDES = 3
MAX_SIDES = 100
ANGLE_TOLERANCE_DEG = 0.5  # cuánto puede no cuadrar la suma de ángulos escritos a mano
CLOSE_TOLERANCE_M = 0.01  # cuánto puede no cerrar la figura con lados escritos a mano
_EPS = 1e-9


@dataclass(frozen=True)
class Shape:
    """Figura cerrada con sus medidas."""

    points: tuple[XY, ...]
    sides_m: tuple[float, ...]
    angles_deg: tuple[float, ...]
    perimeter_m: float
    area_m2: float
    concave: bool
    self_crossing: bool
    closure_error_m: float  # distancia que le falta a la figura para cerrar (0 si cierra)
    angle_sum_error_deg: float  # suma de ángulos menos (n − 2) × 180°
    closes: bool
    computed_sides: tuple[int, ...] = ()  # índices de los lados que se calcularon
    computed_angles: tuple[int, ...] = ()
    warnings: tuple[str, ...] = ()


def _headings(angles: Sequence[float]) -> list[float]:
    """Rumbo (grados) de cada lado a partir de los ángulos interiores."""
    out = [0.0]
    for i in range(1, len(angles)):
        out.append(out[-1] + 180.0 - angles[i])
    return out


def _walk(sides: Sequence[float], headings: Sequence[float]) -> list[XY]:
    points = [XY(0.0, 0.0)]
    for length, h in zip(sides, headings, strict=True):
        last = points[-1]
        points.append(XY(last.x + length * cos(radians(h)), last.y + length * sin(radians(h))))
    return points


def _interior(prev_heading: float, next_heading: float, ccw: bool = True) -> float:
    """Ángulo interior entre dos rumbos consecutivos, en (0°, 360°)."""
    turn = (next_heading - prev_heading + 180.0) % 360.0 - 180.0
    return 180.0 - turn if ccw else 180.0 + turn


def _check_inputs(sides: Sequence[float | None], angles: Sequence[float | None]) -> int:
    n = len(sides)
    if n < MIN_SIDES or n > MAX_SIDES:
        raise Validation(
            "polygon_side_count", f"A polygon needs between {MIN_SIDES} and {MAX_SIDES} sides"
        )
    if len(angles) != n:
        raise Validation(
            "polygon_lengths_mismatch", "Give one angle per side (use null if unknown)"
        )
    for s in sides:
        if s is not None and s <= 0:
            raise Validation("polygon_invalid_side", "Sides must be greater than 0 m")
    for a in angles:
        if a is not None and not 0 < a < 360:
            raise Validation("polygon_invalid_angle", "Interior angles must be between 0° and 360°")
    return n


def _solve_two_sides(
    sides: list[float | None], headings: Sequence[float], missing: Sequence[int]
) -> None:
    """Calcula hasta dos lados que faltan para que la figura cierre (sistema lineal 2 × 2)."""
    gap_x = -sum(s * cos(radians(h)) for s, h in zip(sides, headings, strict=True) if s is not None)
    gap_y = -sum(s * sin(radians(h)) for s, h in zip(sides, headings, strict=True) if s is not None)
    if len(missing) == 1:
        i = missing[0]
        length = hypot(gap_x, gap_y)
        direction = degrees(atan2(gap_y, gap_x))
        off = abs((direction - headings[i] + 180.0) % 360.0 - 180.0)
        if length < _EPS or off > ANGLE_TOLERANCE_DEG:
            raise Validation(
                "polygon_does_not_close",
                f"With these angles side {i + 1} cannot close the figure",
            )
        sides[i] = length
        return
    i, j = missing
    ax, ay = cos(radians(headings[i])), sin(radians(headings[i]))
    bx, by = cos(radians(headings[j])), sin(radians(headings[j]))
    det = ax * by - bx * ay
    if abs(det) < 1e-6:
        raise Validation(
            "polygon_underdetermined",
            f"Sides {i + 1} and {j + 1} are parallel: give one of them",
        )
    a = (gap_x * by - bx * gap_y) / det
    b = (ax * gap_y - gap_x * ay) / det
    if a <= _EPS or b <= _EPS:
        raise Validation(
            "polygon_does_not_close",
            f"Sides {i + 1} and {j + 1} would need a negative length: check the data",
        )
    sides[i], sides[j] = a, b


def _close_with_side(
    sides: list[float | None], angles: list[float | None], side: int
) -> tuple[list[float | None], list[float | None]]:
    """Faltan los ángulos de los extremos del lado `side`: se recorre el resto y se cierra."""
    n = len(sides)
    start = (side + 1) % n  # el recorrido empieza al final del lado que cierra
    order = [(start + k) % n for k in range(n - 1)]  # lados conocidos, en orden
    heading, rel = 0.0, {}
    for k, idx in enumerate(order):
        if k:
            heading += 180.0 - angles[idx]  # type: ignore[operator]
        rel[idx] = heading
    pts = _walk([sides[idx] for idx in order], [rel[idx] for idx in order])  # type: ignore[misc]
    end = pts[-1]
    gap = hypot(end.x, end.y)
    if gap < _EPS:
        raise Validation("polygon_does_not_close", "The known sides already close the figure")
    rel[side] = degrees(atan2(-end.y, -end.x))
    if sides[side] is None:
        sides[side] = gap  # si se dio, al recorrer la figura se ve cuánto no cierra
    angles[start] = _interior(rel[side], rel[start])
    angles[side] = _interior(rel[(side - 1) % n], rel[side])
    return sides, angles


def solve(sides: Sequence[float | None], angles: Sequence[float | None]) -> Shape:
    """Completa los lados y ángulos que faltan, cierra la figura y calcula sus medidas."""
    n = _check_inputs(sides, angles)
    s, a = list(sides), list(angles)
    missing_angles = [i for i, v in enumerate(a) if v is None]
    missing_sides = [i for i, v in enumerate(s) if v is None]
    target = (n - 2) * 180.0

    if len(missing_angles) == 2:
        i, j = missing_angles
        if j - i == 1:
            side = i
        elif i == 0 and j == n - 1:
            side = n - 1
        else:
            raise Validation(
                "polygon_underdetermined",
                "Two missing angles must be at both ends of the same side",
            )
        if any(k != side for k in missing_sides):
            raise Validation(
                "polygon_underdetermined",
                "With two missing angles only the side between them can be missing",
            )
        s, a = _close_with_side(s, a, side)
    elif len(missing_angles) > 2:
        raise Validation(
            "polygon_underdetermined", "Too many missing angles: give at least n − 2 of them"
        )
    else:
        if len(missing_angles) == 1:
            value = target - sum(v for v in a if v is not None)
            if not 0 < value < 360:
                raise Validation(
                    "polygon_does_not_close",
                    f"The other angles leave {value:.1f}° for angle {missing_angles[0] + 1}",
                )
            a[missing_angles[0]] = value
        if len(missing_sides) > 2:
            raise Validation(
                "polygon_underdetermined", "Too many missing sides: give at least n − 2 of them"
            )
        if missing_sides:
            _solve_two_sides(s, _headings(a), missing_sides)  # type: ignore[arg-type]

    final_sides: list[float] = [float(v) for v in s]  # type: ignore[arg-type]
    final_angles: list[float] = [float(v) for v in a]  # type: ignore[arg-type]
    walked = _walk(final_sides, _headings(final_angles))
    closure = hypot(walked[-1].x, walked[-1].y)
    points = tuple(walked[:-1])
    angle_error = sum(final_angles) - target
    closes = closure <= CLOSE_TOLERANCE_M and abs(angle_error) <= ANGLE_TOLERANCE_DEG
    crossing = self_crossing(points)
    warnings = []
    if abs(angle_error) > ANGLE_TOLERANCE_DEG:
        warnings.append("angle_sum_mismatch")
    if closure > CLOSE_TOLERANCE_M:
        warnings.append("does_not_close")
    if crossing:
        warnings.append("self_crossing")
    return Shape(
        points=points,
        sides_m=tuple(final_sides),
        angles_deg=tuple(final_angles),
        perimeter_m=path_length(points, closed=True),
        area_m2=area(points),
        concave=is_concave(points),
        self_crossing=crossing,
        closure_error_m=closure,
        angle_sum_error_deg=angle_error,
        closes=closes,
        computed_sides=tuple(missing_sides),
        computed_angles=tuple(missing_angles),
        warnings=tuple(warnings),
    )


def from_points(points: Sequence[XY]) -> Shape:
    """Medidas de una figura marcada punto a punto (HU-41): lados, ángulos, perímetro y área.

    Respeta el orden en que se marcaron los puntos (horario o antihorario).
    """
    n = len(points)
    if n < MIN_SIDES or n > MAX_SIDES:
        raise Validation(
            "polygon_side_count", f"A polygon needs between {MIN_SIDES} and {MAX_SIDES} points"
        )
    pts = list(points)
    o = pts[0]
    if all(
        abs((p.x - o.x) * (q.y - o.y) - (q.x - o.x) * (p.y - o.y)) < _EPS for p in pts for q in pts
    ):
        raise Validation("polygon_degenerate", "The points are on one line: there is no area")
    signed = sum(pts[i].x * pts[(i + 1) % n].y - pts[(i + 1) % n].x * pts[i].y for i in range(n))
    ccw = signed >= 0
    sides = [hypot(pts[(i + 1) % n].x - p.x, pts[(i + 1) % n].y - p.y) for i, p in enumerate(pts)]
    if min(sides) < _EPS:
        raise Validation("polygon_repeated_point", "Two consecutive points are the same")
    headings = [
        degrees(atan2(pts[(i + 1) % n].y - p.y, pts[(i + 1) % n].x - p.x))
        for i, p in enumerate(pts)
    ]
    angles = [_interior(headings[i - 1], headings[i], ccw) for i in range(n)]
    crossing = self_crossing(pts)
    return Shape(
        points=tuple(pts),
        sides_m=tuple(sides),
        angles_deg=tuple(angles),
        perimeter_m=path_length(pts, closed=True),
        area_m2=area(pts),
        concave=is_concave(pts),
        self_crossing=crossing,
        closure_error_m=0.0,
        angle_sum_error_deg=sum(angles) - (n - 2) * 180.0,
        closes=not crossing,
        warnings=("self_crossing",) if crossing else (),
    )
