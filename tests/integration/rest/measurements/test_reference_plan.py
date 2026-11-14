"""Reference plan: any polygon (concave too) at scale 1:N is stored, returned and compared.

Real PostgreSQL in an isolated schema. Convention: real = drawn points × scale_n.
"""

import pytest

from support.measurement_fixtures import gps_walk_readings, scaled
from velocista.domain.measurements.entities import XY

MEASUREMENTS = "/api/measurements"


def reading_json(r):
    return {
        "seq": r.seq,
        "t_ms": r.t_ms,
        "kind": r.kind,
        "lat": r.lat,
        "lon": r.lon,
        "accuracy_m": r.accuracy_m,
    }


# L: barra de 12 × 4 m y brazo de 4 × 6 m. Perímetro 44 m, área 72 m².
L_REAL = (XY(0, 0), XY(12, 0), XY(12, 4), XY(4, 4), XY(4, 10), XY(0, 10))


def plan(poly, k=1.0):
    return [{"x": p.x * k, "y": p.y * k} for p in poly]


def start(client, reference, **extra):
    return client.post(
        MEASUREMENTS,
        json={
            "method": "gps",
            "place_name": "Cancha",
            "device_id": "phone-ref",
            "reference": reference,
            **extra,
        },
    )


def finish_walking(client, measurement_id, poly):
    readings = [reading_json(r) for r in gps_walk_readings(poly, sigma=0.5)]
    r = client.post(f"{MEASUREMENTS}/{measurement_id}/readings", json={"readings": readings})
    assert r.status_code == 200, r.text
    done = client.post(f"{MEASUREMENTS}/{measurement_id}/finish")
    assert done.status_code == 200, done.text
    return done.json()["result"]


class TestConcavePlan:
    def test_concave_plan_is_stored_and_returned_whole(self, client):
        ref = {"points": plan(L_REAL, 0.01), "scale_n": 100, "name": "Plano L"}
        created = start(client, ref)
        assert created.status_code == 201, created.text
        got = client.get(f"{MEASUREMENTS}/{created.json()['id']}").json()["reference"]
        assert got["scale_n"] == 100 and got["name"] == "Plano L"
        assert len(got["points"]) == 6
        for sent, back in zip(ref["points"], got["points"], strict=True):
            assert back == pytest.approx(sent)

    @pytest.mark.parametrize("scale_n, k", [(1, 1.0), (100, 0.01)])
    def test_reference_metrics_use_real_size(self, client, scale_n, k):
        """Con 1:100 los puntos van en metros del plano (×0,01) y el real es punto × 100."""
        created = start(client, {"points": plan(L_REAL, k), "scale_n": scale_n}).json()
        result = finish_walking(client, created["id"], scaled(L_REAL, 3))
        assert result["reference_perimeter_m"] == pytest.approx(44)
        assert result["reference_area_m2"] == pytest.approx(72)
        assert result["perimeter_error_pct"] is not None
        assert result["area_error_pct"] is not None
        measured = result["area_m2"]
        assert result["area_error_pct"] == pytest.approx((measured - 72) / 72 * 100)

    def test_plan_without_scale_defaults_to_real_metres(self, client):
        created = start(client, {"points": plan(L_REAL)}).json()
        assert created["reference"]["scale_n"] == 1


class TestSelfCrossingPlan:
    BOW_TIE = [{"x": 0, "y": 0}, {"x": 10, "y": 10}, {"x": 10, "y": 0}, {"x": 0, "y": 10}]

    def test_crossing_plan_is_rejected_with_a_clear_code(self, client):
        r = start(client, {"points": self.BOW_TIE})
        assert r.status_code == 422, r.text
        assert "measurement_reference_self_crossing" in r.text

    def test_concave_plan_is_not_mistaken_for_crossing(self, client):
        assert start(client, {"points": plan(L_REAL)}).status_code == 201


class TestGuidedWalkFields:
    def test_start_index_and_direction_come_back_as_sent(self, client):
        ref = {"points": plan(L_REAL), "start_index": 3, "direction": "ccw"}
        created = start(client, ref)
        assert created.status_code == 201, created.text
        got = client.get(f"{MEASUREMENTS}/{created.json()['id']}").json()["reference"]
        assert got["start_index"] == 3 and got["direction"] == "ccw"

    def test_both_are_optional_and_null_by_default(self, client):
        created = start(client, {"points": plan(L_REAL)}).json()
        assert created["reference"]["start_index"] is None
        assert created["reference"]["direction"] is None

    @pytest.mark.parametrize("bad", [{"start_index": 6}, {"start_index": -1}, {"direction": "up"}])
    def test_out_of_range_start_or_bad_direction_is_rejected(self, client, bad):
        assert start(client, {"points": plan(L_REAL), **bad}).status_code == 422

    def test_start_index_past_the_last_vertex_names_the_reference(self, client):
        r = start(client, {"points": plan(L_REAL), "start_index": 6})
        assert r.status_code == 422
        assert "measurement_reference_invalid" in r.text
