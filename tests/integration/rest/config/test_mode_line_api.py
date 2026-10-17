"""Config: operating mode and line color per robot (commands need a connected robot)."""

import pytest


class TestModeLine:
    def test_get_mode_line_when_never_saved_returns_404_no_config(self, client, build):
        robot_id = build.robot()
        response = client.get(f"/api/robots/{robot_id}/mode-line")
        assert response.status_code == 404
        assert response.json()["detail"]["reason"] == "no_config"

    @pytest.mark.parametrize(
        "path,body", [("mode", {"mode": "test"}), ("line", {"color": "black"})]
    )
    def test_set_command_when_robot_has_no_manifest_returns_409(self, client, build, path, body):
        robot_id = build.robot()
        response = client.post(f"/api/robots/{robot_id}/mode-line/{path}", json=body)
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "no_manifest"

    @pytest.mark.parametrize("path,field", [("mode", "mode"), ("line", "color")])
    @pytest.mark.parametrize("value", ["invalid", None, 42, {}, []])
    def test_set_command_when_value_invalid_returns_422(self, client, build, path, field, value):
        robot_id = build.robot()
        response = client.post(f"/api/robots/{robot_id}/mode-line/{path}", json={field: value})
        assert response.status_code == 422
        assert response.json()["detail"]["reason"] == "invalid_command"
