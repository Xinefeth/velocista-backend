"""Measurements API: calibration, ingestion, result, GPS error and precision model.

Real PostgreSQL in an isolated schema. Phone readings come from the test simulator.
"""

import random

import pytest

from support.measurement_fixtures import RECT_10x6, still_fixes, walk_readings

MEASUREMENTS = "/api/measurements"
CALIBRATIONS = "/api/calibrations"
PHONE = "phone-qa-1"
RECT_PLAN = [{"x": p.x, "y": p.y} for p in RECT_10x6]


def reading_json(r):
    data = {"seq": r.seq, "t_ms": r.t_ms, "kind": r.kind}
    if r.gyro_z_dps is not None:
        data["gyro_z_dps"] = r.gyro_z_dps
    if r.accel is not None:
        data["accel"] = list(r.accel)
    for key in ("lat", "lon", "accuracy_m", "pwm"):
        if getattr(r, key) is not None:
            data[key] = getattr(r, key)
    return data


def calibrate(client, device=PHONE, bias=0.4, steps=(29, 28, 29)):
    rng = random.Random(7)
    samples = [{"t_ms": i * 20, "gyro_z_dps": bias + rng.gauss(0, 0.1)} for i in range(250)]
    gyro = client.post(f"{CALIBRATIONS}/{device}/gyro", json={"samples": samples})
    assert gyro.status_code == 201, gyro.text
    trials = [{"distance_m": 20, "step_count": n} for n in steps]
    step = client.post(f"{CALIBRATIONS}/{device}/step", json={"trials": trials})
    assert step.status_code == 201, step.text


def start(client, device=PHONE, **overrides):
    body = {
        "method": "steps",
        "place_name": "Aula 204",
        "device_id": device,
        "reference": {"points": RECT_PLAN},
        **overrides,
    }
    response = client.post(MEASUREMENTS, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def send(client, measurement_id, readings, batch=500):
    reports = []
    for i in range(0, len(readings), batch):
        chunk = [reading_json(r) for r in readings[i : i + batch]]
        response = client.post(
            f"{MEASUREMENTS}/{measurement_id}/readings", json={"readings": chunk}
        )
        assert response.status_code == 200, response.text
        reports.append(response.json())
    return reports


def measure(client, device=PHONE, seed=1, **walk):
    m = start(client, device)
    send(client, m["id"], walk_readings(gyro_bias_dps=0.4, gyro_noise_dps=0.3, seed=seed, **walk))
    response = client.post(f"{MEASUREMENTS}/{m['id']}/finish")
    assert response.status_code == 200, response.text
    return response.json()


class TestCalibration:
    def test_new_phone_is_not_ready_for_steps(self, client):
        state = client.get(f"{CALIBRATIONS}/new-phone").json()
        assert state["ready"] == {"steps": False, "car": False, "gps": True}

    def test_calibration_is_saved_and_used(self, client):
        calibrate(client)
        state = client.get(f"{CALIBRATIONS}/{PHONE}").json()
        assert state["ready"]["steps"] is True
        assert state["calibration"]["gyro_bias_dps"] == pytest.approx(0.4, abs=0.03)
        assert state["calibration"]["step_length_m"] == pytest.approx(0.70, abs=0.01)
        assert set(state["records"]) == {"gyro_bias", "step_length"}

    def test_moving_phone_is_rejected(self, client):
        samples = [{"t_ms": i * 20, "gyro_z_dps": 30.0 * (-1) ** i} for i in range(250)]
        response = client.post(f"{CALIBRATIONS}/{PHONE}/gyro", json={"samples": samples})
        assert response.status_code == 422
        assert response.json()["detail"]["reason"] == "calibration_phone_moved"

    def test_car_speed_fit(self, client):
        trials = [{"pwm": p, "distance_m": (0.01 * p + 0.05) * 4, "seconds": 4} for p in (30, 60)]
        response = client.post(f"{CALIBRATIONS}/{PHONE}/car", json={"trials": trials})
        assert response.status_code == 201
        assert response.json()["params"]["k"] == pytest.approx(0.01)


class TestMeasurementFlow:
    def test_steps_without_calibration_can_start(self, client):
        response = client.post(
            MEASUREMENTS, json={"method": "steps", "place_name": "Aula", "device_id": "x"}
        )
        assert response.status_code == 201
        assert response.json()["calibration"]["step_length_m"] is None

    def test_car_without_calibration_is_rejected(self, client):
        response = client.post(
            MEASUREMENTS,
            json={"method": "car", "mount": "robot", "place_name": "Pista", "device_id": "x"},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["reason"] == "measurement_not_calibrated"

    def test_classroom_measured_within_3_percent(self, client):
        calibrate(client)
        result = measure(client)["result"]
        assert result["quality"] == "green"
        assert result["corners"] == 3
        assert abs(result["perimeter_error_pct"]) < 3
        assert abs(result["area_error_pct"]) < 3
        assert len(result["polygon"]) == 4

    def test_measurement_freezes_calibration(self, client):
        calibrate(client)
        m = start(client)
        assert m["status"] == "recording"
        assert m["calibration"]["gyro_calibrated"] is True
        assert m["calibration"]["step_length_m"] == pytest.approx(0.70, abs=0.01)

    def test_list_filters_by_device_and_hides_paths(self, client):
        calibrate(client)
        calibrate(client, device="other-phone")
        measure(client)
        start(client, device="other-phone")
        page = client.get(MEASUREMENTS, params={"device_id": PHONE}).json()
        assert page["total"] == 1
        assert page["items"][0]["result"]["polygon"] == []

    def test_unknown_measurement_is_404(self, client):
        response = client.get(f"{MEASUREMENTS}/999999")
        assert response.status_code == 404
        assert response.json()["detail"]["reason"] == "measurement_not_found"


class TestIngestion:
    def test_invalid_readings_are_discarded_and_counted(self, client):
        calibrate(client)
        m = start(client)
        batch = [
            {"seq": 0, "t_ms": 1000, "kind": "motion", "gyro_z_dps": 0.1, "accel": [0, 0, 9.8]},
            {"seq": 1, "t_ms": 1020, "kind": "gps", "lat": 95, "lon": 0, "accuracy_m": 5},
            {"seq": 2, "t_ms": 1040, "kind": "wifi"},
            {"seq": 3, "t_ms": 1060, "kind": "motion", "accel": [0, 9.8]},
        ]
        report = client.post(f"{MEASUREMENTS}/{m['id']}/readings", json={"readings": batch}).json()
        assert report["accepted"] == 1
        assert report["discarded"] == {
            "gps_out_of_range": 1,
            "kind_unknown": 1,
            "accel_out_of_range": 1,
        }

    def test_retrying_a_batch_does_not_duplicate(self, client):
        calibrate(client)
        m = start(client)
        readings = walk_readings()[:100]
        first = send(client, m["id"], readings)[0]
        again = send(client, m["id"], readings)[0]
        assert (first["accepted"], again["accepted"], again["duplicates"]) == (100, 0, 100)
        assert client.get(f"{MEASUREMENTS}/{m['id']}").json()["reading_count"] == 100
        assert len(client.get(f"{MEASUREMENTS}/{m['id']}/readings").json()) == 100

    def test_finished_measurement_rejects_readings(self, client):
        calibrate(client)
        done = measure(client)
        response = client.post(
            f"{MEASUREMENTS}/{done['id']}/readings",
            json={"readings": [{"seq": 99999, "t_ms": 1, "kind": "corner"}]},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "measurement_finished"

    def test_too_few_steps_cannot_finish(self, client):
        calibrate(client)
        m = start(client)
        send(client, m["id"], walk_readings()[:60])
        response = client.post(f"{MEASUREMENTS}/{m['id']}/finish")
        assert response.status_code == 422
        assert response.json()["detail"]["reason"] == "measurement_too_short"


class TestGpsError:
    def fixes(self, x, seed):
        return [
            {"t_ms": f.t_ms, "lat": f.lat, "lon": f.lon, "accuracy_m": f.accuracy_m}
            for f in still_fixes(x, 0, sigma=4, seed=seed, bad_every=5)
        ]

    def test_trial_and_summary(self, client):
        for i, (real, env) in enumerate([(30, "open"), (50, "open"), (40, "buildings")]):
            response = client.post(
                "/api/gps-trials",
                json={
                    "device_id": PHONE,
                    "place_name": f"Prueba {i}",
                    "environment": env,
                    "real_distance_m": real,
                    "start_fixes": self.fixes(0, i * 2),
                    "end_fixes": self.fixes(real, i * 2 + 1),
                },
            )
            assert response.status_code == 201, response.text
            assert set(response.json()["result"]["methods"]) == {"single", "mean", "filtered"}
        summary = client.get("/api/gps-trials/summary", params={"device_id": PHONE}).json()
        assert summary["trials"] == 3
        assert summary["min_side_m"] > 0
        assert set(summary["by_environment"]) == {"open", "buildings"}

    def test_mistaken_trial_can_be_deleted(self, client):
        body = {
            "device_id": PHONE,
            "place_name": "Equivocada",
            "environment": "open",
            "real_distance_m": 30,
            "start_fixes": self.fixes(0, 1),
            "end_fixes": self.fixes(30, 2),
        }
        trial = client.post("/api/gps-trials", json=body).json()
        assert client.delete(f"/api/gps-trials/{trial['id']}").status_code == 204
        assert client.get("/api/gps-trials", params={"device_id": PHONE}).json() == []
        summary = client.get("/api/gps-trials/summary", params={"device_id": PHONE}).json()
        assert summary["trials"] == 0
        missing = client.delete(f"/api/gps-trials/{trial['id']}")
        assert missing.status_code == 404
        assert missing.json()["detail"]["reason"] == "gps_trial_not_found"

    def test_round_trip_trial_uses_meters_only(self, client):
        response = client.post(
            "/api/gps-trials",
            json={
                "device_id": PHONE,
                "place_name": "Ida y vuelta en carro",
                "environment": "open",
                "real_distance_m": 0,
                "start_fixes": self.fixes(0, 3),
                "end_fixes": self.fixes(0, 4),
            },
        )
        assert response.status_code == 201, response.text
        single = response.json()["result"]["methods"]["single"]
        assert single["error_pct"] is None
        assert single["error_m"] == pytest.approx(single["gps_distance_m"])

    def test_trial_needs_three_fixes(self, client):
        response = client.post(
            "/api/gps-trials",
            json={
                "device_id": PHONE,
                "place_name": "x",
                "environment": "open",
                "real_distance_m": 10,
                "start_fixes": self.fixes(0, 1)[:2],
                "end_fixes": self.fixes(10, 2),
            },
        )
        assert response.status_code == 422


class TestPrecisionModel:
    def test_model_lowers_error_and_applies_calibration(self, client):
        # paso mal calibrado (0.77 en vez de 0.70) y giroscopio sin calibrar
        calibrate(client, bias=0.0, steps=(26, 26, 26))
        ids = [measure(client, seed=s)["id"] for s in range(3)]
        response = client.post(
            "/api/precision-model/runs",
            json={"measurement_ids": ids, "max_attempts": 40, "apply": True},
        )
        assert response.status_code == 201, response.text
        run = response.json()
        assert run["result"]["final_cost"] < run["result"]["baseline_cost"]
        assert run["result"]["holdout"]["measurement_id"] == ids[-1]
        assert run["applied"] is True
        state = client.get(f"{CALIBRATIONS}/{PHONE}").json()
        assert state["records"]["step_length"]["origin"] == "model"
        assert state["calibration"]["step_length_m"] == pytest.approx(0.70, abs=0.03)
        assert len(client.get("/api/precision-model/runs").json()) == 1

    def test_model_needs_existing_measurements(self, client):
        response = client.post(
            "/api/precision-model/runs", json={"measurement_ids": [999998, 999999]}
        )
        assert response.status_code == 404


class TestAdaptiveStepThreshold:
    def test_soft_walker_is_learned_and_measured(self, client):
        # pisa suave: con la regla fija (1,2) casi no se contaban sus pasos
        trials = [
            {
                "distance_m": 32,
                "readings": [reading_json(r) for r in walk_readings(step_accel=1.0, seed=s)],
            }
            for s in range(3)
        ]
        response = client.post(f"{CALIBRATIONS}/soft-phone/step", json={"trials": trials})
        assert response.status_code == 201, response.text
        params = response.json()["params"]
        assert params["step_threshold_ms2"] < 1.2
        assert params["step_length_m"] == pytest.approx(0.70, abs=0.02)

        m = start(client, device="soft-phone")
        assert m["calibration"]["step_threshold_ms2"] == pytest.approx(params["step_threshold_ms2"])
        send(client, m["id"], walk_readings(step_accel=1.0, gyro_noise_dps=0.3, seed=9))
        result = client.post(f"{MEASUREMENTS}/{m['id']}/finish").json()["result"]
        assert abs(result["perimeter_error_pct"]) < 3


class TestDeleteMeasurement:
    def test_deleted_measurement_and_its_readings_are_gone(self, client):
        calibrate(client)
        wrong = measure(client)
        kept = measure(client, seed=2)
        response = client.delete(f"{MEASUREMENTS}/{wrong['id']}")
        assert response.status_code == 204
        assert client.get(f"{MEASUREMENTS}/{wrong['id']}").status_code == 404
        assert client.get(f"{MEASUREMENTS}/{wrong['id']}/readings").status_code == 404
        page = client.get(MEASUREMENTS, params={"device_id": PHONE}).json()
        assert [m["id"] for m in page["items"]] == [kept["id"]]
        assert (
            len(client.get(f"{MEASUREMENTS}/{kept['id']}/readings").json())
            == (kept["reading_count"])
        )

    def test_cancelled_recording_can_be_deleted_and_keeps_calibration(self, client):
        calibrate(client)
        m = start(client)
        send(client, m["id"], walk_readings()[:100])
        assert client.delete(f"{MEASUREMENTS}/{m['id']}").status_code == 204
        assert client.get(f"{CALIBRATIONS}/{PHONE}").json()["ready"]["steps"] is True

    def test_unknown_measurement_cannot_be_deleted(self, client):
        response = client.delete(f"{MEASUREMENTS}/999999")
        assert response.status_code == 404
        assert response.json()["detail"]["reason"] == "measurement_not_found"
