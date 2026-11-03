"""Measurements: plane geometry in metres (EN-34)."""

import pytest

from support.measurement_fixtures import L_SHAPE, RECT_10x6
from velocista.domain.measurements.entities import XY
from velocista.domain.measurements.geometry import (
    area,
    is_concave,
    path_length,
    pct_diff,
    self_crossing,
    to_local,
)


def test_area_and_perimeter_of_a_rectangle():
    assert area(RECT_10x6) == pytest.approx(60)
    assert path_length(RECT_10x6, closed=True) == pytest.approx(32)


def test_area_does_not_depend_on_direction():
    assert area(tuple(reversed(RECT_10x6))) == pytest.approx(60)


def test_area_of_concave_l_shape():
    # 6 x 8 menos el hueco de 4 x 6
    assert area(L_SHAPE) == pytest.approx(6 * 8 - 4 * 6)
    assert is_concave(L_SHAPE)
    assert not is_concave(RECT_10x6)


def test_self_crossing_bow_tie():
    bow = (XY(0, 0), XY(4, 4), XY(4, 0), XY(0, 4))
    assert self_crossing(bow)
    assert not self_crossing(RECT_10x6)
    assert not self_crossing(L_SHAPE)


def test_open_path_length():
    assert path_length(RECT_10x6) == pytest.approx(26)


def test_to_local_one_thousandth_degree():
    p = to_local(-8.112, -79.0287, -8.111, -79.0287)
    assert p.x == pytest.approx(0, abs=1e-6)
    assert p.y == pytest.approx(-111.19, abs=0.05)
    q = to_local(0, 0.001, 0, 0)
    assert q.x == pytest.approx(111.19, abs=0.05)


def test_pct_diff():
    assert pct_diff(33, 30) == pytest.approx(10)
    assert pct_diff(1, 0) is None
