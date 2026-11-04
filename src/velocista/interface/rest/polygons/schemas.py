"""Esquemas HTTP de figuras por lados y ángulos o por puntos (EN-42). Distancias en metros."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from velocista.domain.measurements.polygon import MAX_SIDES, MIN_SIDES, Shape


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PolygonPointIO(_Strict):
    x: float
    y: float


class PolygonSolveIn(_Strict):
    sides_m: list[float | None] = Field(
        min_length=MIN_SIDES,
        max_length=MAX_SIDES,
        description="Side i goes from vertex i to vertex i + 1, in metres; null if unknown",
    )
    angles_deg: list[float | None] = Field(
        min_length=MIN_SIDES,
        max_length=MAX_SIDES,
        description=(
            "Interior angle at vertex i (between side i - 1 and side i), counterclockwise; "
            "270 for the inner corner of an L; null if unknown"
        ),
    )


class PolygonPointsIn(_Strict):
    points: list[PolygonPointIO] = Field(
        min_length=MIN_SIDES,
        max_length=MAX_SIDES,
        description="Marked points in order (clockwise or counterclockwise), in metres",
    )


class PolygonOut(BaseModel):
    points: list[PolygonPointIO] = Field(
        description="Vertices; for /solve side 0 starts at (0, 0) on +x"
    )
    sides_m: list[float]
    angles_deg: list[float]
    perimeter_m: float
    area_m2: float
    concave: bool
    self_crossing: bool
    closure_error_m: float = Field(description="How far the figure is from closing")
    angle_sum_error_deg: float = Field(description="Sum of interior angles - (n - 2) * 180 degrees")
    closes: bool
    computed_sides: list[int] = Field(description="Indexes of the sides that were calculated")
    computed_angles: list[int] = Field(description="Indexes of the angles that were calculated")
    warnings: list[str] = Field(description="angle_sum_mismatch | does_not_close | self_crossing")

    @classmethod
    def from_entity(cls, shape: Shape) -> PolygonOut:
        return cls(
            points=[PolygonPointIO(x=p.x, y=p.y) for p in shape.points],
            sides_m=list(shape.sides_m),
            angles_deg=list(shape.angles_deg),
            perimeter_m=shape.perimeter_m,
            area_m2=shape.area_m2,
            concave=shape.concave,
            self_crossing=shape.self_crossing,
            closure_error_m=shape.closure_error_m,
            angle_sum_error_deg=shape.angle_sum_error_deg,
            closes=shape.closes,
            computed_sides=list(shape.computed_sides),
            computed_angles=list(shape.computed_angles),
            warnings=list(shape.warnings),
        )
