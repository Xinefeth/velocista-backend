"""Devices: manifest and raw commands when no physical device is connected."""


class TestDevices:
    def test_get_manifest_when_robot_not_connected_returns_404(self, client):
        response = client.get("/api/devices/robot/manifest")
        assert response.status_code == 404
        assert response.json()["detail"]["reason"] == "no_manifest"

    def test_send_robot_command_when_no_manifest_returns_409(self, client):
        response = client.post("/api/devices/robot/commands", json={"type": "start"})
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "no_manifest"

    def test_send_command_when_type_not_in_contract_returns_422(self, client):
        response = client.post("/api/devices/timer/commands", json={"type": "explode"})
        assert response.status_code == 422
        assert response.json()["detail"]["reason"] == "invalid_command"

    def test_send_command_when_device_unknown_returns_422(self, client):
        assert client.post("/api/devices/drone/commands", json={"type": "x"}).status_code == 422

    def test_send_command_when_extra_fields_returns_422(self, client):
        response = client.post("/api/devices/robot/commands", json={"type": "x", "bad": 1})
        assert response.status_code == 422
