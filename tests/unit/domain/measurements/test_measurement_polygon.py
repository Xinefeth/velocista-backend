"""Measurements: contour from sides and angles, and figures marked by points (EN-42)."""

import pytest

from support.measurement_fixtures import L_SHAPE, RECT_10x6
from velocista.domain.measurements.entities import XY
from velocista.domain.measurements.polygon import from_points, solve
from velocista.domain.shared.errors import Validation

L_SIDES = [6, 2, 4, 6, 2, 8]
L_ANGLES = [90, 90, 90, 270, 90, 90]


def approx_points(points, expected):
    assert len(points) == len(expected)
    for p, q in zip(points, expected, strict=True):
        assert (p.x, p.y) == (pytest.approx(q.x, abs=1e-6), pytest.approx(q.y, abs=1e-6))


class TestKnownFigures:
    def test_square(self):
        shape = solve([4, 4, 4, 4], [90, 90, 90, 90])
        assert shape.perimeter_m == pytest.approx(16)
        assert shape.area_m2 == pytest.approx(16)
        assert shape.closes and not shape.concave and shape.warnings == ()

    def test_rectangle_points_start_at_origin_along_x(self):
        shape = solve([10, 6, 10, 6], [90, 90, 90, 90])
        approx_points(shape.points, RECT_10x6)
        assert shape.area_m2 == pytest.approx(60)

    def test_l_shape_is_concave_and_its_area_is_right(self):
        shape = solve(L_SIDES, L_ANGLES)
        approx_points(shape.points, L_SHAPE)
        assert shape.area_m2 == pytest.approx(24)
        assert shape.perimeter_m == pytest.approx(28)
        assert shape.concave and shape.closes

    def test_angle_sum_rule_holds(self):
        shape = solve(L_SIDES, L_ANGLES)
        assert sum(shape.angles_deg) == pytest.approx((6 - 2) * 180)
        assert shape.angle_sum_error_deg == pytest.approx(0)


class TestMissingData:
    def test_one_missing_angle_comes_from_the_sum(self):
        shape = solve([10, 6, 10, 6], [90, 90, 90, None])
        assert shape.angles_deg[3] == pytest.approx(90)
        assert shape.computed_angles == (3,)

    def test_two_missing_sides_close_the_figure(self):
        shape = solve([10, 6, None, None], [90, 90, 90, 90])
        assert shape.sides_m[2:] == (pytest.approx(10), pytest.approx(6))
        assert shape.computed_sides == (2, 3)
        assert shape.closes

    def test_l_shape_with_a_missing_angle_and_two_missing_sides(self):
        shape = solve([6, 2, 4, None, None, 8], [90, 90, 90, None, 90, 90])
        assert shape.angles_deg[3] == pytest.approx(270)
        assert shape.sides_m[3] == pytest.approx(6)
        assert shape.sides_m[4] == pytest.approx(2)
        assert shape.area_m2 == pytest.approx(24)

    def test_parallel_missing_sides_cannot_be_solved(self):
        with pytest.raises(Validation) as e:
            solve([6, 2, 4, None, 2, None], [90, 90, 90, None, 90, 90])
        assert e.value.reason == "polygon_underdetermined"

    def test_two_sides_and_the_angle_between_them(self):
        shape = solve([3, 4, None], [None, 90, None])
        assert shape.sides_m[2] == pytest.approx(5)
        assert shape.angles_deg[0] == pytest.approx(53.130, abs=1e-3)
        assert shape.angles_deg[2] == pytest.approx(36.870, abs=1e-3)
        assert shape.area_m2 == pytest.approx(6)

    def test_two_missing_angles_at_the_ends_of_a_known_side(self):
        shape = solve(L_SIDES, [None, 90, 90, 270, 90, None])
        assert shape.angles_deg[0] == pytest.approx(90)
        assert shape.angles_deg[5] == pytest.approx(90)
        assert shape.closes

    def test_l_shape_closed_by_its_last_side(self):
        shape = solve([6, 2, 4, 6, None, 8], [90, 90, 90, 270, None, None])
        assert shape.sides_m[4] == pytest.approx(2)
        assert shape.angles_deg[4] == pytest.approx(90)
        assert shape.area_m2 == pytest.approx(24)


class TestWarnings:
    def test_sides_that_do_not_close_are_reported(self):
        shape = solve([10, 6, 10, 7], [90, 90, 90, 90])
        assert not shape.closes
        assert shape.closure_error_m == pytest.approx(1)
        assert "does_not_close" in shape.warnings

    def test_angles_that_do_not_add_up_are_reported(self):
        shape = solve([10, 6, 10, 6], [90, 90, 90, 80])
        assert "angle_sum_mismatch" in shape.warnings
        assert shape.angle_sum_error_deg == pytest.approx(-10)

    def test_known_side_that_does_not_match_is_reported(self):
        shape = solve([6, 2, 4, 6, 2, 9], [None, 90, 90, 270, 90, None])
        assert shape.closure_error_m == pytest.approx(1)
        assert not shape.closes


class TestInvalidData:
    @pytest.mark.parametrize(
        ("sides", "angles", "reason"),
        [
            ([1, 2], [90, 90], "polygon_side_count"),
            ([1, 2, 3], [60, 60], "polygon_lengths_mismatch"),
            ([1, -2, 3], [60, 60, 60], "polygon_invalid_side"),
            ([1, 1, 1], [60, 0, None], "polygon_invalid_angle"),
            ([10, None, None, None], [90] * 4, "polygon_underdetermined"),
            ([10, None, 10, None], [90] * 4, "polygon_underdetermined"),
            ([1, 1, 1, 1], [90, None, 90, None], "polygon_underdetermined"),
            ([10, 6, 10, 6], [90, None, None, None], "polygon_underdetermined"),
            ([1, 1, 1], [170, 170, None], "polygon_does_not_close"),
            ([10, 20, None], [90, 90, 90], "polygon_does_not_close"),
        ],
    )
    def test_rejected(self, sides, angles, reason):
        with pytest.raises(Validation) as e:
            solve(sides, angles)
        assert e.value.reason == reason


class TestMarkedPoints:
    def test_l_shape_by_points(self):
        shape = from_points(L_SHAPE)
        assert shape.area_m2 == pytest.approx(24)
        assert shape.perimeter_m == pytest.approx(28)
        assert shape.angles_deg == pytest.approx((90, 90, 90, 270, 90, 90))
        assert shape.concave and shape.closes

    def test_clockwise_points_keep_their_order_and_angles(self):
        clockwise = [L_SHAPE[0], *reversed(L_SHAPE[1:])]
        shape = from_points(clockwise)
        assert shape.points == tuple(clockwise)
        assert shape.area_m2 == pytest.approx(24)
        assert sorted(shape.angles_deg) == pytest.approx([90, 90, 90, 90, 90, 270])

    def test_crossing_sides_are_warned(self):
        shape = from_points([XY(0, 0), XY(4, 4), XY(4, 0), XY(0, 4)])
        assert shape.self_crossing and not shape.closes
        assert shape.warnings == ("self_crossing",)

    @pytest.mark.parametrize(
        ("points", "reason"),
        [
            ([XY(0, 0), XY(1, 1)], "polygon_side_count"),
            ([XY(0, 0), XY(1, 1), XY(2, 2)], "polygon_degenerate"),
            ([XY(0, 0), XY(0, 0), XY(1, 0), XY(0, 1)], "polygon_repeated_point"),
        ],
    )
    def test_rejected(self, points, reason):
        with pytest.raises(Validation) as e:
            from_points(points)
        assert e.value.reason == reason
