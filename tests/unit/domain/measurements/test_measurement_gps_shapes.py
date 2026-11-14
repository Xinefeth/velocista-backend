"""Medición GPS de figuras cóncavas con zonas estrechas («llave») y avisos de esquinas."""

import pytest

from support.measurement_fixtures import (
    L_SHAPE,
    RECT_10x6,
    gps_walk_with_corners,
    key_shape,
    measurement,
    scaled,
)
from velocista.domain.measurements import gps as gps_mod
from velocista.domain.measurements.compute import compute_result
from velocista.domain.measurements.entities import XY
from velocista.domain.measurements.geometry import area, min_width

KEY = key_shape()
# Con ruido de 4 m (precisión informada 6 m) estas semillas cruzan el polígono con el suavizado
# normal: el cuello mide 4 m y el ruido es mayor que su ancho.
CROSSING_SEEDS = (14, 27, 33, 39)


def run(poly, sigma=3.0, seed=1, skip=(), **kw):
    return compute_result(
        measurement("gps", reference=poly),
        gps_walk_with_corners(poly, sigma=sigma, seed=seed, skip=skip),
        **kw,
    )


# ---------------------------------------------------------------- ancho mínimo


def test_min_width_of_a_rectangle_is_its_short_side():
    assert min_width(list(RECT_10x6)) == pytest.approx(6)


def test_min_width_of_the_key_is_the_neck():
    assert min_width(list(KEY)) == pytest.approx(4, abs=0.01)


def test_min_width_of_a_triangle_is_none():
    assert min_width([XY(0, 0), XY(5, 0), XY(0, 5)]) is None


def test_min_width_is_zero_when_the_polygon_crosses_itself():
    assert min_width([XY(0, 0), XY(10, 10), XY(10, 0), XY(0, 10)]) == 0.0


# ---------------------------------------------------------------- suavizado de la llave


@pytest.mark.parametrize("seed", CROSSING_SEEDS)
def test_key_polygon_never_crosses_itself_and_says_so(seed, monkeypatch):
    with monkeypatch.context() as mp:  # sin la segunda oportunidad el polígono se cruza
        mp.setattr(gps_mod, "FALLBACK_ACCEL_STD", ())
        assert run(KEY, sigma=4, seed=seed).self_crossing is True
    r = run(KEY, sigma=4, seed=seed)
    assert r.self_crossing is False
    assert "gps_smoothing_adjusted" in r.warnings
    assert r.area_m2 == pytest.approx(area(KEY), rel=0.3)


def test_no_adjustment_when_the_default_smoothing_is_fine():
    r = run(KEY, sigma=2, seed=1)
    assert "gps_smoothing_adjusted" not in r.warnings and r.self_crossing is False


def test_stronger_smoothing_follows_the_track_less():
    from support.measurement_fixtures import gps_walk_readings

    fixes = [
        gps_mod.Fix(r.t_ms, r.lat, r.lon, r.accuracy_m)
        for r in gps_walk_readings(scaled(RECT_10x6, 8), sigma=3)
    ]
    raw = gps_mod.local_points(fixes)

    def roughness(track):
        return sum(abs(a.x - b.x) + abs(a.y - b.y) for a, b in zip(track, track[1:], strict=False))

    assert roughness(gps_mod.smooth_track(fixes, 0.3)) < roughness(gps_mod.smooth_track(fixes))
    assert roughness(gps_mod.smooth_track(fixes)) < roughness(raw)


# ---------------------------------------------------------------- zona estrecha


def test_narrow_neck_warns():
    assert "gps_narrow_section" in run(KEY, sigma=2, seed=1).warnings


def test_wide_field_has_no_narrow_warning():
    r = run(scaled(RECT_10x6, 8), sigma=1.0)
    assert "gps_narrow_section" not in r.warnings


def test_steps_measurement_never_gets_the_gps_warning():
    from support.measurement_fixtures import walk_readings

    r = compute_result(measurement(), walk_readings())
    assert "gps_narrow_section" not in r.warnings


# ---------------------------------------------------------------- esquina interior sin marcar

L3 = scaled(L_SHAPE, 3)
CONCAVE_VERTEX = 3  # (2, 2) × 3, la esquina interior de la L


def test_missing_inner_corner_warns_area_mismatch():
    r = run(L3, sigma=1.0, skip=(CONCAVE_VERTEX,))
    assert "corner_area_mismatch" in r.warnings
    assert r.area_m2 > area(L3)  # se sobreestima: no cambia el cálculo, solo avisa


def test_all_corners_marked_no_mismatch():
    assert "corner_area_mismatch" not in run(L3, sigma=1.0).warnings


def test_mismatch_tolerance_is_configurable():
    r = run(L3, sigma=1.0, skip=(CONCAVE_VERTEX,), corner_area_tolerance_pct=80)
    assert "corner_area_mismatch" not in r.warnings


def test_no_mismatch_without_corners():
    readings = [r for r in gps_walk_with_corners(L3, sigma=1.0) if r.kind != "corner"]
    r = compute_result(measurement("gps", reference=L3), readings)
    assert "corner_area_mismatch" not in r.warnings
