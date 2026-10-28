"""Payloads and entities of valid tracks, shared by the tracks tests (distances in cm)."""

from dataclasses import replace

from velocista.domain.tracks.entities import Board, Point, Start, Track, Zone


def track_payload(**overrides) -> dict:
    """JSON body of a valid closed track (a 220 x 170 cm rectangle with rounded corners)."""
    body = {
        "name": "Technical 3 x 2.5",
        "board": {"width_cm": 300, "height_cm": 250},
        "closed": True,
        "points": [
            {"x": 40, "y": 40, "radius": 15, "gap": False},
            {"x": 260, "y": 40, "radius": 15, "gap": False},
            {"x": 260, "y": 210, "radius": 15, "gap": False},
            {"x": 40, "y": 210, "radius": 15, "gap": False},
        ],
        "zones": [{"x": 104, "y": 0, "width": 12, "height": 12, "name": "timer post"}],
        "start": {"edge": 0, "t": 0.35},
        "profile_id": None,
        "length_cm": 700.5,
    }
    body.update(overrides)
    return body


def make_track(**overrides) -> Track:
    """Domain entity of a valid track; any field can be replaced."""
    track = Track(
        name="Technical 3 x 2.5",
        board=Board(300, 250),
        closed=True,
        points=(Point(40, 40, 15), Point(260, 40, 15), Point(260, 210, 15), Point(40, 210, 15)),
        zones=(Zone(104, 0, 12, 12, "timer post"),),
        start=Start(0, 0.35),
        profile_id=None,
        length_cm=700.5,
    )
    return replace(track, **overrides)


def many_points(count: int) -> tuple[Point, ...]:
    return tuple(Point(float(i % 200), float(i // 200), 0) for i in range(count))
