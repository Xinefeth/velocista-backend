"""HU-30 B1: the result of a measurement carries the total turn of the whole walk (degrees)."""

import pytest
from sqlalchemy import text

from support.measurement_fixtures import RECT_10x6, gps_walk_readings, scaled, walk_readings

MEASUREMENTS = "/api/measurements"
PHONE = "phone-turn-1"


def reading_json(r):
    data = {"seq": r.seq, "t_ms": r.t_ms, "kind": r.kind}
    for key in ("gyro_z_dps", "lat", "lon", "accuracy_m"):
        if getattr(r, key) is not None:
            data[key] = getattr(r, key)
    if r.accel is not None:
        data["accel"] = list(r.accel)
    return data


def finish(client, method, readings, **body):
    m = client.post(
        MEASUREMENTS,
        json={"method": method, "place_name": "Aula", "device_id": PHONE, **body},
    )
    assert m.status_code == 201, m.text
    mid = m.json()["id"]
    for i in range(0, len(readings), 500):
        chunk = [reading_json(r) for r in readings[i : i + 500]]
        sent = client.post(f"{MEASUREMENTS}/{mid}/readings", json={"readings": chunk})
        assert sent.status_code == 200, sent.text
    done = client.post(f"{MEASUREMENTS}/{mid}/finish")
    assert done.status_code == 200, done.text
    return mid, done.json()


def test_clockwise_square_returns_about_minus_360(client):
    clockwise = tuple(reversed(RECT_10x6))
    _, out = finish(client, "steps", walk_readings(poly=clockwise))
    assert out["result"]["turn_total_deg"] == pytest.approx(-360, abs=3)
    assert out["result"]["heading_drift_deg"] is not None  # los campos existentes siguen


def test_counterclockwise_square_returns_about_plus_360(client):
    _, out = finish(client, "steps", walk_readings())
    assert out["result"]["turn_total_deg"] == pytest.approx(360, abs=3)


def test_get_measurement_returns_the_same_value_as_finish(client):
    mid, out = finish(client, "steps", walk_readings())
    again = client.get(f"{MEASUREMENTS}/{mid}").json()
    assert again["result"]["turn_total_deg"] == out["result"]["turn_total_deg"]


def test_gps_measurement_returns_null(client):
    _, out = finish(client, "gps", gps_walk_readings(scaled(RECT_10x6, 8)))
    assert "turn_total_deg" in out["result"]
    assert out["result"]["turn_total_deg"] is None


def test_row_saved_before_the_field_existed_returns_null(client, db):
    mid, _ = finish(client, "steps", walk_readings())
    db.execute(
        text("UPDATE measurement SET result = result - 'turn_total_deg' WHERE id = :id"),
        {"id": mid},
    )
    stored = db.execute(
        text("SELECT result ? 'turn_total_deg' FROM measurement WHERE id = :id"), {"id": mid}
    ).scalar()
    assert stored is False  # la fila ya no tiene el campo, como las guardadas antes de HU-30
    old = client.get(f"{MEASUREMENTS}/{mid}")
    assert old.status_code == 200
    assert old.json()["result"]["turn_total_deg"] is None
    assert old.json()["result"]["perimeter_m"] > 0  # el resto del resultado sigue igual


def test_list_does_not_break_with_the_new_field(client):
    finish(client, "steps", walk_readings())
    page = client.get(MEASUREMENTS)
    assert page.status_code == 200
    assert page.json()["items"][0]["result"]["turn_total_deg"] == pytest.approx(360, abs=3)
