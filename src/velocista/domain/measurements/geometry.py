"""Geometría plana en metros: perímetro, área (Gauss), concavidad y cruces. Sin frameworks."""

from __future__ import annotations

from collections.abc import Sequence
from math import cos, hypot, radians

from velocista.domain.measurements.entities import XY

EARTH_RADIUS_M = 6_371_008.8  # radio medio de la Tierra


def dist(a: XY, b: XY) -> float:
    return hypot(b.x - a.x, b.y - a.y)


def path_length(points: Sequence[XY], closed: bool = False) -> float:
    total = sum(dist(points[i - 1], points[i]) for i in range(1, len(points)))
    if closed and len(points) > 2:
        total += dist(points[-1], points[0])
    return total


def signed_area(points: Sequence[XY]) -> float:
    """Fórmula de Gauss (del zapatero). Positiva si el contorno va en sentido antihorario."""
    n = len(points)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        s += a.x * b.y - b.x * a.y
    return s / 2


def area(points: Sequence[XY]) -> float:
    """Área de un polígono simple, convexo o cóncavo (por ejemplo en L)."""
    return abs(signed_area(points))


def is_concave(points: Sequence[XY]) -> bool:
    n = len(points)
    if n < 4:
        return False
    sign = 0
    for i in range(n):
        a, b, c = points[i], points[(i + 1) % n], points[(i + 2) % n]
        z = (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x)
        if abs(z) < 1e-9:
            continue
        s = 1 if z > 0 else -1
        if sign and s != sign:
            return True
        sign = s
    return False


def _ccw(a: XY, b: XY, c: XY) -> bool:
    return (c.y - a.y) * (b.x - a.x) > (b.y - a.y) * (c.x - a.x)


def self_crossing(points: Sequence[XY]) -> bool:
    """True si dos lados no vecinos del polígono se cruzan (el área no sería válida)."""
    n = len(points)
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            a, b = points[i], points[(i + 1) % n]
            c, d = points[j], points[(j + 1) % n]
            if _ccw(a, c, d) != _ccw(b, c, d) and _ccw(a, b, c) != _ccw(a, b, d):
                return True
    return False


def _point_segment(p: XY, a: XY, b: XY) -> float:
    dx, dy = b.x - a.x, b.y - a.y
    sq = dx * dx + dy * dy
    t = 0.0 if sq == 0 else max(0.0, min(1.0, ((p.x - a.x) * dx + (p.y - a.y) * dy) / sq))
    return dist(p, XY(a.x + t * dx, a.y + t * dy))


def min_width(points: Sequence[XY]) -> float | None:
    """Menor distancia entre dos lados no vecinos: el ancho de la parte más angosta.

    Sirve para polígonos simples; devuelve None si no hay lados no vecinos (menos de 4 lados).
    """
    n = len(points)
    best = None
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            a, b = points[i], points[(i + 1) % n]
            c, d = points[j], points[(j + 1) % n]
            if _ccw(a, c, d) != _ccw(b, c, d) and _ccw(a, b, c) != _ccw(a, b, d):
                return 0.0
            d_ij = min(
                _point_segment(a, c, d),
                _point_segment(b, c, d),
                _point_segment(c, a, b),
                _point_segment(d, a, b),
            )
            best = d_ij if best is None else min(best, d_ij)
    return best


def to_local(lat: float, lon: float, lat0: float, lon0: float) -> XY:
    """Latitud y longitud a metros en un plano local con origen en (lat0, lon0).

    x hacia el este, y hacia el norte. Aproximación equirectangular: el error es menor a 1 cm
    para terrenos de unos cientos de metros, muy por debajo del error del GPS.
    """
    x = radians(lon - lon0) * EARTH_RADIUS_M * cos(radians(lat0))
    y = radians(lat - lat0) * EARTH_RADIUS_M
    return XY(x, y)


def pct_diff(measured: float, reference: float) -> float | None:
    if reference <= 0:
        return None
    return (measured - reference) / reference * 100
