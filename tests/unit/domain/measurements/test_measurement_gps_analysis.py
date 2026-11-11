"""Measurements: GPS error analysis per environment, distance, wait and accuracy (CU-4)."""

from dataclasses import replace

import pytest

from support.measurement_fixtures import still_fixes
from velocista.domain.measurements.gps import Fix
from velocista.domain.measurements.gps_analysis import (
    GpsConfig,
    TrialRow,
    summarize,
    trial_analysis,
)

CFG = GpsConfig()


def fake_result(error_m: float, distance_m: float, reported_m: float = 5.0) -> dict:
    """Resultado de una prueba con errores conocidos, sin pasar por lecturas."""
    method = {"gps_distance_m": distance_m, "error_m": error_m, "error_pct": None}
    pct = error_m / distance_m * 100 if distance_m else None
    full = {**method, "error_pct": pct}
    return {
        "methods": {"single": full, "mean": full, "filtered": full},
        "reported_accuracy_m": reported_m,
        "by_wait": {
            "5": {"usable": True, "error_m": error_m},
            "10": {"usable": True, "error_m": error_m},
            "20": {"usable": True, "error_m": error_m},
        },
        "by_accuracy": {
            "3": {"usable": False, "kept": 0, "total": 40, "error_m": None},
            "5": {"usable": True, "kept": 20, "total": 40, "error_m": error_m * 2},
            "10": {"usable": True, "kept": 40, "total": 40, "error_m": error_m},
            "20": {"usable": True, "kept": 40, "total": 40, "error_m": error_m},
        },
    }


def rows(env: str, errors: list[float], distance_m: float = 50, reported_m: float = 5.0):
    return [TrialRow(env, distance_m, fake_result(e, distance_m, reported_m)) for e in errors]


# ---------------------------------------------------------------- por prueba


def test_trial_analysis_keeps_sp06_keys_and_adds_wait_and_accuracy():
    start = still_fixes(0, 0, n=20, sigma=3, seed=1)
    end = still_fixes(50, 0, n=20, sigma=3, seed=2)
    r = trial_analysis(start, end, 50, CFG)
    assert set(r["methods"]) == {"single", "mean", "filtered"}
    assert {"reported_accuracy_m", "start_spread", "end_spread", "fix_count"} <= set(r)
    assert set(r["by_wait"]) == {"5", "10", "20"}
    assert set(r["by_accuracy"]) == {"3", "5", "10", "20"}


def test_wait_uses_only_the_first_seconds():
    # 20 lecturas, una por segundo: los primeros 5 s dejan 6 por punto; 20 s las deja todas.
    start = still_fixes(0, 0, n=20, sigma=3, seed=1)
    end = still_fixes(50, 0, n=20, sigma=3, seed=2)
    r = trial_analysis(start, end, 50, CFG)
    assert r["by_wait"]["5"]["usable"] is True
    assert r["by_wait"]["20"]["error_m"] == pytest.approx(r["methods"]["mean"]["error_m"])


def test_wait_not_usable_when_fewer_than_three_fixes():
    # Lecturas cada 10 s: en 5 s solo cabe la primera.
    start = [Fix(i * 10_000, -8.1116, -79.0287, 5.0) for i in range(5)]
    end = [Fix(i * 10_000, -8.1116, -79.0283, 5.0) for i in range(5)]
    r = trial_analysis(start, end, 40, CFG)
    assert r["by_wait"]["5"] == {"usable": False, "error_m": None}


def test_accuracy_threshold_drops_inaccurate_fixes():
    # sigma 4 -> precisión informada 6 m: con umbral 3 no queda nada, con 10 queda todo.
    start = still_fixes(0, 0, n=20, sigma=4, seed=1)
    end = still_fixes(50, 0, n=20, sigma=4, seed=2)
    r = trial_analysis(start, end, 50, CFG)
    assert r["by_accuracy"]["3"]["usable"] is False
    assert r["by_accuracy"]["3"]["kept"] == 0
    assert r["by_accuracy"]["10"]["kept"] == 40 == r["by_accuracy"]["10"]["total"]


def test_config_is_not_hardwired():
    cfg = replace(CFG, wait_seconds=(2.0, 7.5), accuracy_thresholds_m=(4.0,))
    r = trial_analysis(
        still_fixes(0, 0, n=20, sigma=3, seed=1), still_fixes(50, 0, n=20, sigma=3, seed=2), 50, cfg
    )
    assert set(r["by_wait"]) == {"2", "7.5"}
    assert set(r["by_accuracy"]) == {"4"}


# ---------------------------------------------------------------- resumen


def test_empty_summary_has_every_new_field():
    s = summarize([], CFG)
    assert s["trials"] == 0 and s["min_side_m"] is None
    assert s["conclusion"]["code"] == "no_data"
    assert s["environments"] == {} and s["reported_vs_real"] is None
    assert s["error_trend"] is None and s["recommended_accuracy_m"] is None
    assert [b["trials"] for b in s["by_distance"]] == [0, 0, 0, 0]
    assert s["config"] == CFG.to_dict()


def test_min_side_per_environment():
    data = rows("open", [1, 2, 1.5, 1, 2]) + rows("indoor", [8, 9, 10, 9, 8])
    s = summarize(data, CFG)
    # error máximo 2 m y 10 m con objetivo 10 % -> 20 m y 100 m
    assert s["environments"]["open"]["min_side_m"] == pytest.approx(20)
    assert s["environments"]["indoor"]["min_side_m"] == pytest.approx(100)
    assert s["min_side_m"] == pytest.approx(100)  # el global mezcla todo y no cambia
    assert set(s["by_environment"]) == {"open", "indoor"}  # forma de SP-06 intacta


def test_target_pct_changes_the_minimum_side():
    data = rows("open", [2, 2, 2, 2, 2])
    s5 = summarize(data, replace(CFG, target_pct=5))
    assert s5["environments"]["open"]["min_side_m"] == pytest.approx(40)


def test_few_trials_warn_and_mark_environment_insufficient():
    data = rows("open", [1] * 5) + rows("trees", [3, 4, 3])
    s = summarize(data, CFG)
    assert s["environments"]["open"]["enough_data"] is True
    trees = s["environments"]["trees"]
    assert trees["enough_data"] is False and trees["missing_trials"] == 2
    codes = {(w["code"], w["environment"]) for w in s["warnings"]}
    assert ("gps_environment_few_trials", "trees") in codes
    assert ("gps_few_trials", None) not in codes  # 8 pruebas en total


def test_global_few_trials_gives_insufficient_conclusion():
    s = summarize(rows("open", [2, 3]), CFG)
    assert s["conclusion"]["code"] == "insufficient_data"
    assert any(w["code"] == "gps_few_trials" for w in s["warnings"])
    assert "llega a 5" in s["conclusion"]["text"]


def test_enough_trials_in_total_but_not_per_environment_is_insufficient():
    data = rows("open", [2, 2, 2]) + rows("indoor", [8, 8, 8])
    c = summarize(data, CFG)["conclusion"]
    assert c["code"] == "insufficient_data" and c["ready_environments"] == []


def test_conclusion_only_covers_environments_with_enough_trials():
    data = rows("open", [2] * 5) + rows("trees", [4, 4])
    c = summarize(data, CFG)["conclusion"]
    assert c["code"] == "ok" and c["ready_environments"] == ["open"]
    assert "«open»" in c["text"] and "20 m" in c["text"]
    assert "Faltan pruebas en: «trees»" in c["text"]


def test_min_trials_is_configurable():
    s = summarize(rows("open", [2, 3]), replace(CFG, min_trials=2))
    assert s["conclusion"]["code"] == "ok"
    assert s["environments"]["open"]["enough_data"] is True
    assert not s["warnings"]


def test_conclusion_text_uses_the_data():
    s = summarize(rows("open", [2, 2, 2, 2, 2]), CFG)
    assert s["conclusion"]["code"] == "ok"
    assert "5 pruebas" in s["conclusion"]["text"] and "20 m" in s["conclusion"]["text"]


# ---------------------------------------------------------------- error frente a la distancia


def test_distance_bands_and_flat_trend():
    data = rows("open", [2, 2], distance_m=3) + rows("open", [2, 2.2], distance_m=30)
    s = summarize(data, CFG)
    bands = {b["from_m"]: b for b in s["by_distance"]}
    assert bands[0]["trials"] == 2 and bands[20]["trials"] == 2 and bands[5]["trials"] == 0
    assert bands[5]["mean_error_m"] is None
    assert bands[20]["to_m"] == 50 and bands[50]["to_m"] is None
    assert s["error_trend"] == "flat"


def test_error_that_grows_with_distance_is_reported():
    data = rows("open", [1, 1], distance_m=3) + rows("open", [6, 7], distance_m=60)
    assert summarize(data, CFG)["error_trend"] == "grows"


def test_trend_needs_two_bands():
    assert summarize(rows("open", [1, 1], distance_m=3), CFG)["error_trend"] is None


# ---------------------------------------------------------------- espera y precisión


def test_recommended_accuracy_is_the_lowest_mean_error():
    s = summarize(rows("open", [4, 4, 4, 4, 4]), CFG)
    by = {a["max_accuracy_m"]: a for a in s["by_accuracy"]}
    assert by[3]["usable_trials"] == 0 and by[3]["mean_error_m"] is None
    assert by[5]["mean_error_m"] == 8 and by[5]["mean_kept_pct"] == 50
    assert by[10]["mean_error_m"] == 4
    # 10 y 20 empatan en error: gana el más laxo, que deja más lecturas
    assert s["recommended_accuracy_m"] == 20


def test_wait_table():
    s = summarize(rows("open", [3, 5]), CFG)
    assert [w["seconds"] for w in s["by_wait"]] == [5, 10, 20]
    assert s["by_wait"][0]["mean_error_m"] == 4 and s["by_wait"][0]["max_error_m"] == 5


def test_phone_reporting_better_than_real_is_optimistic():
    s = summarize(rows("open", [10] * 5, reported_m=1.0), CFG)
    r = s["reported_vs_real"]
    assert r["optimistic"] is True and r["ratio"] > 1
    assert r["mean_expected_error_m"] == pytest.approx(2**0.5)


def test_phone_reporting_honestly_is_not_optimistic():
    s = summarize(rows("open", [3] * 5, reported_m=5.0), CFG)
    assert s["reported_vs_real"]["optimistic"] is False


def test_real_trials_end_to_end():
    """Con lecturas simuladas: el interior (más ruido) pide un lado mayor que el abierto."""
    data = []
    for env, sigma in (("open", 2.0), ("indoor", 8.0)):
        for i in range(5):
            res = trial_analysis(
                still_fixes(0, 0, n=20, sigma=sigma, seed=10 + i),
                still_fixes(40, 0, n=20, sigma=sigma, seed=50 + i),
                40,
                CFG,
            )
            data.append(TrialRow(env, 40, res))
    s = summarize(data, CFG)
    assert s["environments"]["indoor"]["min_side_m"] > s["environments"]["open"]["min_side_m"]
    assert s["conclusion"]["code"] == "ok"
    assert s["recommended_accuracy_m"] is not None
