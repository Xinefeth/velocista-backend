"""Optimization: controller catalog and setups (parameter sets per version)."""

import pytest


class TestControllers:
    def test_list_controllers_returns_catalog_with_parameters_and_presets(self, client):
        controller = client.get("/api/controllers").json()[0]
        assert controller["id"] == "pid"
        assert {p["key"] for p in controller["parameters"]} == {"kp", "kd"}
        assert "Base" in controller["presets"]


class TestSetups:
    def test_create_setup_when_valid_returns_201_with_float_parameters(self, client, build):
        robot_id = build.robot()
        version_id = build.version(robot_id, build.component())
        response = client.post(
            f"/api/robots/{robot_id}/setups",
            json={
                "version_id": version_id,
                "name": "Fast",
                "controller_id": "pid",
                "parameters": {"kp": 2, "kd": 1},
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["parameters"] == {"kp": 2.0, "kd": 1.0}

    @pytest.mark.parametrize(
        "parameters,reason",
        [
            ({"kp": 11, "kd": 1}, "out_of_range"),
            ({"kp": 1}, "invalid_parameters"),
            ({"kp": 1, "kd": 1, "extra": 1}, "invalid_parameters"),
        ],
    )
    def test_create_setup_when_parameters_invalid_returns_422(
        self, client, build, parameters, reason
    ):
        robot_id = build.robot()
        version_id = build.version(robot_id, build.component())
        response = client.post(
            f"/api/robots/{robot_id}/setups",
            json={
                "version_id": version_id,
                "name": "X",
                "controller_id": "pid",
                "parameters": parameters,
            },
        )
        assert response.status_code == 422
        assert response.json()["detail"]["reason"] == reason

    def test_create_setup_when_controller_missing_returns_404(self, client, build):
        robot_id = build.robot()
        version_id = build.version(robot_id, build.component())
        response = client.post(
            f"/api/robots/{robot_id}/setups",
            json={
                "version_id": version_id,
                "name": "X",
                "controller_id": "ghost",
                "parameters": {},
            },
        )
        assert response.status_code == 404
        assert response.json()["detail"]["reason"] == "controller_not_found"

    def test_create_setup_when_version_belongs_to_other_robot_returns_404(self, client, build):
        owner = build.robot("A")
        version_id = build.version(owner, build.component())
        other = build.robot("B", name="Other")
        response = client.post(
            f"/api/robots/{other}/setups",
            json={
                "version_id": version_id,
                "name": "X",
                "controller_id": "pid",
                "parameters": {"kp": 1, "kd": 1},
            },
        )
        assert response.status_code == 404
        assert response.json()["detail"]["reason"] == "version_not_found"

    def test_list_setups_when_filtered_by_version_returns_only_those(self, client, build):
        robot_id, version_id, _ = build.robot_ready()
        assert (
            client.get(f"/api/robots/{robot_id}/setups?version_id={version_id}").json()["total"]
            == 1
        )
        assert client.get(f"/api/robots/{robot_id}/setups?version_id=999999").json()["total"] == 0

    def test_list_setups_when_robot_missing_returns_404(self, client):
        assert client.get("/api/robots/ghost/setups").status_code == 404

    def test_archive_setup_when_done_hides_it_from_list_but_get_still_works(self, client, build):
        robot_id, _, setup_id = build.robot_ready()
        assert client.delete(f"/api/setups/{setup_id}").status_code == 204
        assert client.get(f"/api/robots/{robot_id}/setups").json()["total"] == 0
        assert client.get(f"/api/setups/{setup_id}").json()["archived"] is True

    def test_get_setup_when_missing_returns_404(self, client):
        assert client.get("/api/setups/999999").status_code == 404

    def test_apply_setup_when_robot_not_connected_returns_error_not_500(self, client, build):
        robot_id, _, setup_id = build.robot_ready()
        response = client.post(f"/api/robots/{robot_id}/setups/{setup_id}/apply")
        assert response.status_code in (409, 503), response.text
        assert "reason" in response.json()["detail"]

    def test_apply_setup_when_archived_returns_409(self, client, build):
        robot_id, _, setup_id = build.robot_ready()
        client.delete(f"/api/setups/{setup_id}")
        response = client.post(f"/api/robots/{robot_id}/setups/{setup_id}/apply")
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "setup_archived"

    def test_apply_preset_when_unknown_preset_returns_422(self, client, build):
        robot_id = build.robot()
        response = client.post(
            f"/api/robots/{robot_id}/presets/apply",
            json={"controller_id": "pid", "preset_id": "Nope"},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["reason"] == "preset_not_found"

    def test_live_configuration_when_robot_has_no_manifest_returns_404(self, client, build):
        robot_id = build.robot()
        response = client.get(f"/api/robots/{robot_id}/configuration")
        assert response.status_code == 404
        assert response.json()["detail"]["reason"] == "no_manifest"

    def test_reconciled_controllers_when_no_manifest_marks_none_active(self, client, build):
        robot_id = build.robot()
        body = client.get(f"/api/robots/{robot_id}/controllers").json()
        assert body["active_controller"] is None
        assert all(c["active"] is False for c in body["controllers"])
