"""Builder: robots lifecycle (create, read, edit, archive)."""

import pytest


class TestRobots:
    def test_create_robot_when_valid_returns_201_without_version(self, client):
        response = client.post(
            "/api/robots", json={"name": "Flash", "short_code": "FL", "type": "racer"}
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["current_version_id"] is None and body["archived"] is False

    def test_create_robot_when_short_code_duplicated_returns_409(self, client, build):
        build.robot("DUP")
        response = client.post(
            "/api/robots", json={"name": "Other", "short_code": "DUP", "type": "racer"}
        )
        assert response.status_code == 409

    @pytest.mark.parametrize(
        "payload",
        [
            {"short_code": "X", "type": "racer"},
            {"name": "", "short_code": "X", "type": "racer"},
            {"name": "N", "short_code": "", "type": "racer"},
            {"name": "N", "short_code": "X" * 13, "type": "racer"},
            {"name": "N", "short_code": "X", "type": "racer", "unknown": 1},
        ],
    )
    def test_create_robot_when_payload_invalid_returns_422(self, client, payload):
        assert client.post("/api/robots", json=payload).status_code == 422

    def test_get_robot_when_missing_returns_404(self, client):
        response = client.get("/api/robots/ghost")
        assert response.status_code == 404
        assert response.json()["detail"]["reason"] == "robot_not_found"

    def test_update_robot_when_partial_changes_name_only(self, client, build):
        robot_id = build.robot()
        response = client.patch(f"/api/robots/{robot_id}", json={"name": "Renamed"})
        assert response.status_code == 200
        assert response.json()["name"] == "Renamed" and response.json()["short_code"] == "QA"

    def test_archive_robot_when_done_removes_it_from_list(self, client, build):
        robot_id = build.robot()
        assert client.delete(f"/api/robots/{robot_id}").status_code == 204
        assert client.get("/api/robots").json()["total"] == 0

    def test_update_robot_when_archived_returns_409(self, client, build):
        robot_id = build.robot()
        client.delete(f"/api/robots/{robot_id}")
        assert client.patch(f"/api/robots/{robot_id}", json={"name": "X"}).status_code == 409

    def test_list_robots_when_paginated_returns_total_and_slice(self, client, build):
        for code in ("A", "B", "C"):
            build.robot(code, name=f"Robot {code}")
        page = client.get("/api/robots?limit=2").json()
        assert page["total"] == 3 and len(page["items"]) == 2
