"""Tracks: pure validation rules (limits are proposals pending the PO)."""

from dataclasses import replace

import pytest

from support.track_fixtures import make_track, many_points
from velocista.domain.shared.errors import Validation
from velocista.domain.tracks.entities import Board, Point, Start, Zone
from velocista.domain.tracks.validation import edge_count, validate_track


def reason_of(track) -> str:
    with pytest.raises(Validation) as error:
        validate_track(track)
    return error.value.reason


class TestValidTracks:
    def test_validate_when_track_is_valid_passes(self):
        validate_track(make_track())

    @pytest.mark.parametrize("name", ["a", "x" * 80])
    def test_validate_when_name_at_the_limits_passes(self, name):
        validate_track(make_track(name=name))

    def test_validate_when_points_at_the_limits_passes(self):
        validate_track(make_track(points=many_points(2), closed=False, start=Start(0, 0)))
        validate_track(make_track(points=many_points(500), start=Start(499, 1)))

    def test_validate_when_zones_at_the_limits_passes(self):
        validate_track(make_track(zones=()))
        validate_track(make_track(zones=tuple(Zone(0, 0, 1, 1) for _ in range(100))))

    @pytest.mark.parametrize("side", [50, 2000])
    def test_validate_when_board_side_at_the_limits_passes(self, side):
        validate_track(make_track(board=Board(side, side)))

    @pytest.mark.parametrize("radius", [0, 200])
    def test_validate_when_radius_at_the_limits_passes(self, radius):
        validate_track(make_track(points=(Point(1, 1, radius),) * 4))

    @pytest.mark.parametrize("value", [-10000, 10000])
    def test_validate_when_points_outside_the_board_within_range_passes(self, value):
        validate_track(make_track(points=(Point(value, value, 0),) * 4))

    @pytest.mark.parametrize("length", [0.1, 100000])
    def test_validate_when_length_at_the_limits_passes(self, length):
        validate_track(make_track(length_cm=length))

    def test_validate_when_closed_has_three_points_passes(self):
        validate_track(make_track(points=many_points(3), start=Start(2, 1)))


class TestInvalidTracks:
    @pytest.mark.parametrize("name", ["", "   ", "x" * 81])
    def test_validate_when_name_out_of_range_rejects(self, name):
        assert reason_of(make_track(name=name)) == "track_name_invalid"

    @pytest.mark.parametrize("count", [1, 501])
    def test_validate_when_points_count_out_of_range_rejects(self, count):
        track = make_track(points=many_points(count), closed=False, start=Start(0, 0))
        assert reason_of(track) == "track_points_count"

    def test_validate_when_zones_over_the_limit_rejects(self):
        zones = tuple(Zone(0, 0, 1, 1) for _ in range(101))
        assert reason_of(make_track(zones=zones)) == "track_zones_count"

    @pytest.mark.parametrize("board", [Board(49.9, 100), Board(100, 2000.1), Board(0, 0)])
    def test_validate_when_board_out_of_range_rejects(self, board):
        assert reason_of(make_track(board=board)) == "track_board_size"

    @pytest.mark.parametrize("radius", [-0.1, 200.1])
    def test_validate_when_radius_out_of_range_rejects(self, radius):
        assert reason_of(make_track(points=(Point(1, 1, radius),) * 4)) == "track_radius_range"

    @pytest.mark.parametrize("point", [Point(10000.1, 0), Point(0, -10000.1)])
    def test_validate_when_point_coordinate_out_of_range_rejects(self, point):
        assert reason_of(make_track(points=(point,) * 4)) == "track_coordinate_range"

    def test_validate_when_zone_coordinate_out_of_range_rejects(self):
        track = make_track(zones=(Zone(10001, 0, 5, 5),))
        assert reason_of(track) == "track_coordinate_range"

    @pytest.mark.parametrize("zone", [Zone(0, 0, 0, 5), Zone(0, 0, 5, -1), Zone(0, 0, 2000.1, 5)])
    def test_validate_when_zone_size_out_of_range_rejects(self, zone):
        assert reason_of(make_track(zones=(zone,))) == "track_zone_size"

    def test_validate_when_zone_name_too_long_rejects(self):
        assert reason_of(make_track(zones=(Zone(0, 0, 5, 5, "z" * 81),))) == "track_zone_name"

    @pytest.mark.parametrize("length", [0, -5, 100000.1])
    def test_validate_when_length_out_of_range_rejects(self, length):
        assert reason_of(make_track(length_cm=length)) == "track_length_invalid"

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_validate_when_any_number_not_finite_rejects(self, bad):
        assert reason_of(make_track(length_cm=bad)) == "track_not_finite"
        assert reason_of(make_track(board=Board(bad, 100))) == "track_not_finite"
        assert reason_of(make_track(points=(Point(bad, 0),) * 4)) == "track_not_finite"
        assert reason_of(make_track(zones=(Zone(0, 0, bad, 5),))) == "track_not_finite"

    def test_validate_when_closed_with_two_points_rejects(self):
        track = make_track(points=many_points(2), start=Start(0, 0))
        assert reason_of(track) == "track_closed_needs_three_points"

    @pytest.mark.parametrize("t", [-0.1, 1.1])
    def test_validate_when_start_t_out_of_range_rejects(self, t):
        assert reason_of(make_track(start=Start(0, t))) == "track_start_invalid"


class TestStartEdge:
    @pytest.mark.parametrize(
        ("closed", "points", "edge", "valid"),
        [
            (True, 4, 3, True),
            (True, 4, 4, False),
            (False, 4, 2, True),
            (False, 4, 3, False),
            (False, 2, 0, True),
            (False, 2, 1, False),
            (True, 3, 2, True),
            (True, 3, 3, False),
            (True, 4, -1, False),
        ],
    )
    def test_validate_start_edge_depends_on_closed(self, closed, points, edge, valid):
        track = make_track(closed=closed, points=many_points(points), start=Start(edge, 0.5))
        if valid:
            validate_track(track)
        else:
            assert reason_of(track) == "track_start_invalid"

    @pytest.mark.parametrize(
        ("count", "closed", "expected"), [(4, True, 4), (4, False, 3), (2, False, 1)]
    )
    def test_edge_count_when_closed_or_open(self, count, closed, expected):
        assert edge_count(count, closed) == expected


def test_validate_reports_the_first_failure_only():
    track = replace(make_track(), name="", length_cm=0)
    assert reason_of(track) == "track_name_invalid"
