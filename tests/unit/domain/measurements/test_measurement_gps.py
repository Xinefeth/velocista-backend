"""Measurements: GPS error against tape (SP-06) and track smoothing."""

from statistics import mean

import pytest

from support.measurement_fixtures import (
    RECT_10x6,
    gps_walk_readings,
    scaled,
    still_fixes,
    true_path,
)
from velocista.domain.measurements.geometry import dist
from velocista.domain.measurements.gps import (
    Fix,
    filter_fixes,
    local_points,
    min_size_for,
    smooth_track,
    trial_errors,
    trials_summary,
)
from velocista.domain.shared.errors import Validation


def test_filter_drops_bad_accuracy():
    fixes = [Fix(i, 0, 0, 5) for i in range(9)] + [Fix(9, 0, 0, 40)]
    assert len(filter_fixes(fixes)) == 9


def test_averaging_beats_a_single_reading_on_average():
    errs = {"single": [], "filtered": []}
    for seed in range(20):
        a = still_fixes(0, 0, sigma=5, seed=seed * 2, bad_every=5)
        b = still_fixes(50, 0, sigma=5, seed=seed * 2 + 1, bad_every=5)
        r = trial_errors(a, b, 50)
        for k in errs:
            errs[k].append(r["methods"][k]["error_m"])
    assert mean(errs["filtered"]) < mean(errs["single"]) / 2


def test_return_to_same_point_reports_distance_as_error():
    a = still_fixes(0, 0, seed=1)
    b = still_fixes(0, 0, seed=2)
    r = trial_errors(a, b, 0)
    assert r["methods"]["mean"]["error_pct"] is None
    assert r["methods"]["mean"]["error_m"] == r["methods"]["mean"]["gps_distance_m"]


def test_trial_needs_three_fixes_per_point():
    with pytest.raises(Validation):
        trial_errors(still_fixes(0, 0, n=2), still_fixes(1, 0), 1)


def test_summary_min_side_and_best_method():
    results = [
        trial_errors(still_fixes(0, 0, seed=s), still_fixes(30, 0, seed=s + 50), 30)
        for s in range(4)
    ]
    s = trials_summary(results, target_pct=10)
    assert s["trials"] == 4
    assert s["best_method"] in ("mean", "filtered")
    assert s["min_side_m"] == pytest.approx(s["methods"][s["best_method"]]["max_error_m"] * 10)


def test_min_size_for():
    assert min_size_for(5, 10) == pytest.approx(50)


def test_smoothing_reduces_track_error():
    big = scaled(RECT_10x6, 8)
    readings = gps_walk_readings(big, sigma=4, seed=3)
    fixes = [Fix(r.t_ms, r.lat, r.lon, r.accuracy_m) for r in readings]
    truth = true_path(big)

    def err(points):  # distancia media a la referencia más cercana
        origin = points[0]
        start = truth[0]
        return mean(
            min(dist(type(p)(p.x - origin.x + start.x, p.y - origin.y + start.y), t) for t in truth)
            for p in points
        )

    assert err(smooth_track(fixes)) < err(local_points(fixes))
