"""Events: system log (create + list)."""

import pytest


class TestEvents:
    def test_create_event_when_valid_returns_201_with_id_and_date(self, client):
        response = client.post(
            "/api/events", json={"system": "robot", "level": "warning", "message": "Low battery"}
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["id"] >= 1 and body["date"] and body["level"] == "warning"

    def test_create_event_when_level_omitted_defaults_to_info(self, client):
        body = client.post("/api/events", json={"system": "timer", "message": "ok"}).json()
        assert body["level"] == "info"

    @pytest.mark.parametrize(
        "payload",
        [
            {"message": "no system"},
            {"system": "robot"},
            {"system": "robot", "level": "fatal", "message": "x"},
            {"system": "x" * 41, "message": "x"},
            {"system": "robot", "message": "x" * 501},
        ],
    )
    def test_create_event_when_payload_invalid_returns_422(self, client, payload):
        assert client.post("/api/events", json=payload).status_code == 422

    def test_list_events_when_several_exist_respects_limit(self, client):
        for index in range(3):
            client.post("/api/events", json={"system": "robot", "message": f"m{index}"})
        assert len(client.get("/api/events?limit=2").json()) == 2

    @pytest.mark.parametrize("limit", [0, 501])
    def test_list_events_when_limit_out_of_range_returns_422(self, client, limit):
        assert client.get(f"/api/events?limit={limit}").status_code == 422
