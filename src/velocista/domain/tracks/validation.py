"""Reglas puras de validación de una pista. Sin frameworks ni HTTP.

SUPUESTO PENDIENTE DEL PO: todos los límites de este módulo son propuestas (spec EN-28) hasta que
el PO las confirme. Son la única fuente de verdad: los esquemas REST las importan y la migración
`0006` repite las de columnas escalares y longitud de arreglos como CHECK.
"""

from __future__ import annotations

from math import isfinite

from velocista.domain.shared.errors import Validation
from velocista.domain.tracks.entities import Track

NAME_MAX = 80
MIN_POINTS = 2
MAX_POINTS = 500
MAX_ZONES = 100
BOARD_MIN_CM = 50
BOARD_MAX_CM = 2000
RADIUS_MAX_CM = 200
COORD_MAX_CM = 10000  # los puntos pueden salir del tablero: la regla `margin` lo detecta
ZONE_SIZE_MAX_CM = 2000
ZONE_NAME_MAX = 80
LENGTH_MAX_CM = 100000


def _numbers(track: Track):
    yield track.board.width_cm
    yield track.board.height_cm
    yield track.length_cm
    yield track.start.t
    for p in track.points:
        yield from (p.x, p.y, p.radius)
    for z in track.zones:
        yield from (z.x, z.y, z.width, z.height)


def edge_count(point_count: int, closed: bool) -> int:
    """Tramos de la poligonal: n si es cerrada, n-1 si es abierta."""
    return point_count if closed else point_count - 1


def validate_track(track: Track) -> None:
    """Lanza `Validation(reason, detail)` con el primer incumplimiento; `reason` es estable."""
    if not all(isfinite(v) for v in _numbers(track)):
        raise Validation("track_not_finite", "Numbers must be finite (no NaN or Infinity)")
    if not 1 <= len(track.name.strip()) <= NAME_MAX:
        raise Validation("track_name_invalid", f"Name must have 1 to {NAME_MAX} characters")
    if not MIN_POINTS <= len(track.points) <= MAX_POINTS:
        raise Validation("track_points_count", f"A track needs {MIN_POINTS} to {MAX_POINTS} points")
    if len(track.zones) > MAX_ZONES:
        raise Validation("track_zones_count", f"A track allows at most {MAX_ZONES} zones")
    board = track.board
    if not (
        BOARD_MIN_CM <= board.width_cm <= BOARD_MAX_CM
        and BOARD_MIN_CM <= board.height_cm <= BOARD_MAX_CM
    ):
        raise Validation(
            "track_board_size", f"Board sides must be {BOARD_MIN_CM} to {BOARD_MAX_CM} cm"
        )
    for point in track.points:
        if not 0 <= point.radius <= RADIUS_MAX_CM:
            raise Validation("track_radius_range", f"Radius must be 0 to {RADIUS_MAX_CM} cm")
        if abs(point.x) > COORD_MAX_CM or abs(point.y) > COORD_MAX_CM:
            raise Validation(
                "track_coordinate_range", f"Coordinates must be within +/-{COORD_MAX_CM} cm"
            )
    for zone in track.zones:
        if abs(zone.x) > COORD_MAX_CM or abs(zone.y) > COORD_MAX_CM:
            raise Validation(
                "track_coordinate_range", f"Coordinates must be within +/-{COORD_MAX_CM} cm"
            )
        if not (0 < zone.width <= ZONE_SIZE_MAX_CM and 0 < zone.height <= ZONE_SIZE_MAX_CM):
            raise Validation(
                "track_zone_size",
                f"Zone width and height must be above 0 and up to {ZONE_SIZE_MAX_CM} cm",
            )
        if len(zone.name) > ZONE_NAME_MAX:
            raise Validation(
                "track_zone_name", f"Zone name must have at most {ZONE_NAME_MAX} characters"
            )
    if not 0 < track.length_cm <= LENGTH_MAX_CM:
        raise Validation(
            "track_length_invalid", f"length_cm must be above 0 and up to {LENGTH_MAX_CM}"
        )
    # Con menos de 3 puntos el prototipo trata la pista como abierta aunque `closed` esté activo.
    if track.closed and len(track.points) < 3:
        raise Validation(
            "track_closed_needs_three_points", "A closed track needs at least 3 points"
        )
    if not 0 <= track.start.t <= 1:
        raise Validation("track_start_invalid", "start.t must be between 0 and 1")
    if not 0 <= track.start.edge < edge_count(len(track.points), track.closed):
        raise Validation("track_start_invalid", "start.edge is not an edge of the polyline")
