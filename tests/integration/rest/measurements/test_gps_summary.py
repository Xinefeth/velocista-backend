"""CU-4 API: minimum field size per environment, error against distance and trial minimum.

Real PostgreSQL in an isolated schema. GPS readings come from the test simulator.
"""

import pytest

from support.measurement_fixtures import still_fixes

PHONE = "phone-cu4"
TRIALS = "/api/gps-trials"
SUMMARY = "/api/gps-trials/summary"


def fixes(x: float, seed: int, sigma: float) -> list[dict]:
    return [
        {"t_ms": f.t_ms, "lat": f.lat, "lon": f.lon, "accuracy_m": f.accuracy_m}
        for f in still_fixes(x, 0, n=20, sigma=sigma, seed=seed)
    ]


def add_trials(client, env: str, count: int, sigma: float, distance: float = 40.0, seed0: int = 0):
    for i in range(count):
        response = client.post(
            TRIALS,
            json={
                "device_id": PHONE,
                "place_name": f"{env} {i}",
                "environment": env,
                "real_distance_m": distance,
                "start_fixes": fixes(0, seed0 + i * 2, sigma),
                "end_fixes": fixes(distance, seed0 + i * 2 + 1, sigma),
            },
        )
        assert response.status_code == 201, response.text


def summary(client, **params):
    response = client.get(SUMMARY, params={"device_id": PHONE, **params})
    assert response.status_code == 200, response.text
    return response.json()


class TestSummaryPerEnvironment:
    def test_empty_summary_has_the_full_shape(self, client):
        s = summary(client)
        assert s["trials"] == 0 and s["min_side_m"] is None
        assert s["conclusion"]["code"] == "no_data"
        assert s["environments"] == {} and s["reported_vs_real"] is None
        assert s["config"]["min_trials"] == 5 and s["config"]["target_pct"] == 10

    def test_minimum_side_per_environment(self, client):
        add_trials(client, "open", 5, sigma=2.0, seed0=0)
        add_trials(client, "indoor", 5, sigma=8.0, seed0=100)
        s = summary(client)
        assert set(s["environments"]) == {"open", "indoor"}
        assert s["environments"]["indoor"]["min_side_m"] > s["environments"]["open"]["min_side_m"]
        assert s["environments"]["open"]["enough_data"] is True
        assert s["conclusion"]["code"] == "ok" and s["warnings"] == []
        assert s["conclusion"]["ready_environments"] == ["open", "indoor"]
        # lo de SP-06 sigue igual
        assert set(s["by_environment"]) == {"open", "indoor"}
        assert set(s["methods"]) == {"single", "mean", "filtered"} and s["min_side_m"] > 0

    def test_few_trials_in_an_environment_warns(self, client):
        add_trials(client, "open", 5, sigma=2.0)
        add_trials(client, "trees", 2, sigma=5.0, seed0=100)
        s = summary(client)
        assert s["environments"]["trees"] == {**s["environments"]["trees"], "enough_data": False}
        assert s["environments"]["trees"]["missing_trials"] == 3
        assert [w["code"] for w in s["warnings"]] == ["gps_environment_few_trials"]
        assert s["warnings"][0]["environment"] == "trees"

    def test_min_trials_and_target_come_from_the_query(self, client):
        add_trials(client, "open", 3, sigma=3.0)
        assert summary(client)["conclusion"]["code"] == "insufficient_data"
        s = summary(client, min_trials=3, target_pct=20)
        assert s["conclusion"]["code"] == "ok" and s["warnings"] == []
        assert s["config"]["min_trials"] == 3 and s["config"]["target_pct"] == 20

    @pytest.mark.parametrize("params", [{"min_trials": 0}, {"target_pct": 0}, {"target_pct": 101}])
    def test_invalid_query_is_rejected(self, client, params):
        assert client.get(SUMMARY, params=params).status_code == 422


class TestDistanceWaitAndAccuracy:
    def test_error_against_distance_in_bands(self, client):
        add_trials(client, "open", 3, sigma=3.0, distance=3.0)
        add_trials(client, "open", 3, sigma=3.0, distance=30.0, seed0=100)
        s = summary(client)
        bands = {b["from_m"]: b for b in s["by_distance"]}
        assert bands[0]["trials"] == 3 and bands[20]["trials"] == 3
        assert bands[5]["trials"] == 0 and bands[5]["mean_error_m"] is None
        assert s["error_trend"] in ("flat", "grows")

    def test_wait_time_and_accuracy_threshold(self, client):
        add_trials(client, "open", 5, sigma=3.0)
        s = summary(client)
        assert [w["seconds"] for w in s["by_wait"]] == [5, 10, 20]
        assert all(w["usable_trials"] == 5 for w in s["by_wait"])
        assert [a["max_accuracy_m"] for a in s["by_accuracy"]] == [3, 5, 10, 20]
        assert s["recommended_accuracy_m"] in (5, 10, 20)

    def test_reported_accuracy_against_real_error(self, client):
        add_trials(client, "open", 5, sigma=3.0)
        r = summary(client)["reported_vs_real"]
        assert r["trials"] == 5 and r["ratio"] > 0
        assert r["optimistic"] in (True, False)

    def test_new_trial_result_has_wait_and_accuracy(self, client):
        add_trials(client, "open", 1, sigma=3.0)
        result = client.get(TRIALS, params={"device_id": PHONE}).json()[0]["result"]
        assert set(result["methods"]) == {"single", "mean", "filtered"}
        assert set(result["by_wait"]) == {"5", "10", "20"}
        assert set(result["by_accuracy"]) == {"3", "5", "10", "20"}
