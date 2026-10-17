"""End-to-end: robot <-> backend <-> console over real in-process WebSockets.

Flow: console connects -> robot connects with token -> manifest -> status relayed ->
operator sends command through REST -> robot receives and acks -> disconnect is announced.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from velocista.infrastructure.config.settings import settings
from velocista.infrastructure.realtime.registry import device_status, hub
from velocista.interface.rest.devices.router import router as devices_router
from velocista.interface.rest.errors import register_error_handlers
from velocista.interface.websocket.gateway import router as ws_router

MANIFEST = {
    "contract": "2.0",
    "id": "racer",
    "robot_type": "velocista",
    "firmware": "1.0",
    "sensors": [],
    "actuators": [],
    "channels": [
        {"name": "error", "type": "float", "group": "signals"},
        {"name": "bateria_v", "type": "float", "group": "status"},
    ],
    "controllers": [
        {
            "name": "pid",
            "parameters": [
                {"name": "kp", "label": "Kp", "type": "float", "min": 0, "max": 100, "value": 1}
            ],
        }
    ],
    "active_controller": "pid",
    "commands": ["calibrate", "start", "stop", "setup", "mode", "line", "lap_close"],
    "frequencies": {"loop_hz": 1000, "status_hz": 1, "signals_hz": 20},
    "start_mode": "command",
    "battery_compensation": True,
}
STATUS = {
    "state": "ready",
    "calibrated": True,
    "mode": "test",
    "line": "black",
    "controller": "pid",
    "loop_hz": 1000,
    "rssi_dbm": -40,
    "channels": {"bateria_v": 7.4},
}


def frame(type, data, seq=1):
    return {"type": type, "data": data, "seq": seq, "ts": 10}


@pytest.fixture
def app_client(monkeypatch):
    hub.connections.clear()
    hub.consoles.clear()
    monkeypatch.setattr(settings, "auth_required", False, raising=False)
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(ws_router)
    app.include_router(devices_router)
    with TestClient(app) as client:
        yield client
    hub.connections.clear()
    hub.consoles.clear()


def robot_socket(client):
    return client.websocket_connect("/ws/robot?token=" + settings.device_token_robot)


def test_robot_rejects_bad_token(app_client):
    with pytest.raises(WebSocketDisconnect) as error:
        with app_client.websocket_connect("/ws/robot?token=bad"):
            pass
    assert error.value.code == 1008


def test_full_robot_session_manifest_status_command_ack_disconnect(app_client):
    with app_client.websocket_connect("/ws/console") as console:
        assert console.receive_json()["data"]["devices"] == {"robot": False, "timer": False}
        with robot_socket(app_client) as robot:
            assert console.receive_json()["data"] == {"device": "robot", "connected": True}

            robot.send_json(frame("manifest", MANIFEST))
            assert robot.receive_json()["data"]["ok"] is True
            relayed = console.receive_json()
            assert relayed["type"] == "manifest" and relayed["sender"] == "robot"
            assert app_client.get("/api/devices/robot/manifest").json()["id"] == "racer"

            robot.send_json(frame("status", STATUS, 2))
            assert console.receive_json()["data"]["state"] == "ready"

            sent = app_client.post(
                "/api/devices/robot/commands",
                json={"type": "mode", "data": {"mode": "competition"}},
            )
            assert sent.status_code == 202
            command = robot.receive_json()
            assert command["type"] == "mode" and command["data"] == {"mode": "competition"}

            robot.send_json(frame("ack", {"ok": True}, command["seq"]))
            assert console.receive_json()["type"] == "ack"

        assert console.receive_json()["data"]["connected"] is False
        assert app_client.get("/api/devices/robot/manifest").status_code == 404
    assert device_status() == {"robot": False, "timer": False}


def test_start_is_refused_until_robot_is_calibrated(app_client):
    with robot_socket(app_client) as robot:
        robot.send_json(frame("manifest", MANIFEST))
        robot.receive_json()
        robot.send_json(frame("status", {**STATUS, "calibrated": False}, 2))
        response = app_client.post("/api/devices/robot/commands", json={"type": "start"})
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "not_calibrated"
