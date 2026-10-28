"""Esquemas HTTP del contexto `tracks`. Claves JSON en inglés y snake_case; distancias en cm.

SUPUESTO PENDIENTE DEL PO: los límites vienen de `domain/tracks/validation.py` (propuestas EN-28).
"""

from __future__ import annotations

from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from velocista.domain.tracks import validation as limits
from velocista.domain.tracks.entities import Board, Point, Start, Track, Zone

CM = "in centimetres"
# Campos de solo lectura: un export puede reimportarse tal cual, así que se ignoran al entrar.
READ_ONLY = ("id", "created_at", "updated_at")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class PointIO(_Strict):
    x: float = Field(ge=-limits.COORD_MAX_CM, le=limits.COORD_MAX_CM, description=f"X {CM}")
    y: float = Field(ge=-limits.COORD_MAX_CM, le=limits.COORD_MAX_CM, description=f"Y {CM}")
    radius: float = Field(
        default=0,
        ge=0,
        le=limits.RADIUS_MAX_CM,
        description=f"Curve radius {CM}; 0 means a sharp corner",
    )
    gap: bool = Field(
        default=False,
        strict=True,
        description="True when the edge leaving this point has a line gap (assumed boolean)",
    )


class ZoneIO(_Strict):
    x: float = Field(ge=-limits.COORD_MAX_CM, le=limits.COORD_MAX_CM, description=f"X {CM}")
    y: float = Field(ge=-limits.COORD_MAX_CM, le=limits.COORD_MAX_CM, description=f"Y {CM}")
    width: float = Field(gt=0, le=limits.ZONE_SIZE_MAX_CM, description=f"Width {CM}")
    height: float = Field(gt=0, le=limits.ZONE_SIZE_MAX_CM, description=f"Height {CM}")
    name: str = Field(default="", max_length=limits.ZONE_NAME_MAX)


class BoardIO(_Strict):
    width_cm: float = Field(
        ge=limits.BOARD_MIN_CM, le=limits.BOARD_MAX_CM, description="Board width in centimetres"
    )
    height_cm: float = Field(
        ge=limits.BOARD_MIN_CM, le=limits.BOARD_MAX_CM, description="Board height in centimetres"
    )


class StartIO(_Strict):
    edge: int = Field(
        default=0,
        ge=0,
        strict=True,
        description="Index of the edge where the run starts (0 to points-1 if closed, "
        "0 to points-2 if open)",
    )
    t: float = Field(default=0.5, ge=0, le=1, description="Fraction of the edge (0 to 1)")


class TrackIn(_Strict):
    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
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
                "profile_id": "lgr2026",
                "length_cm": 812.4,
            }
        },
    )

    name: str = Field(min_length=1, max_length=limits.NAME_MAX)
    board: BoardIO
    closed: bool
    points: list[PointIO] = Field(min_length=limits.MIN_POINTS, max_length=limits.MAX_POINTS)
    zones: list[ZoneIO] = Field(default_factory=list, max_length=limits.MAX_ZONES)
    start: StartIO = Field(default_factory=StartIO)
    profile_id: str | None = Field(default=None, min_length=1, max_length=40)
    length_cm: float = Field(
        gt=0,
        le=limits.LENGTH_MAX_CM,
        description="Total line length in centimetres, computed by the frontend and stored as sent",
    )

    @model_validator(mode="before")
    @classmethod
    def _drop_read_only(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k not in READ_ONLY}
        return data

    def to_entity(self) -> Track:
        return Track(
            name=self.name,
            board=Board(self.board.width_cm, self.board.height_cm),
            closed=self.closed,
            points=tuple(Point(p.x, p.y, p.radius, p.gap) for p in self.points),
            zones=tuple(Zone(z.x, z.y, z.width, z.height, z.name) for z in self.zones),
            start=Start(self.start.edge, self.start.t),
            profile_id=self.profile_id,
            length_cm=self.length_cm,
        )


class TrackOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=1, le=9007199254740991)
    name: str
    board: BoardIO
    closed: bool
    points: list[PointIO]
    zones: list[ZoneIO]
    start: StartIO
    profile_id: str | None
    length_cm: float = Field(description="Total line length in centimetres")
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @classmethod
    def from_entity(cls, track: Track) -> TrackOut:
        return cls(
            id=track.id,
            name=track.name,
            board=BoardIO(width_cm=track.board.width_cm, height_cm=track.board.height_cm),
            closed=track.closed,
            points=[PointIO(x=p.x, y=p.y, radius=p.radius, gap=p.gap) for p in track.points],
            zones=[
                ZoneIO(x=z.x, y=z.y, width=z.width, height=z.height, name=z.name)
                for z in track.zones
            ],
            start=StartIO(edge=track.start.edge, t=track.start.t),
            profile_id=track.profile_id,
            length_cm=track.length_cm,
            created_at=track.created_at,
            updated_at=track.updated_at,
        )


class TracksPage(BaseModel):
    items: list[TrackOut]
    total: int
    limit: int
    offset: int
