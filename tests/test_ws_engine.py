"""End-to-end in-process sockets exercise real relay and command delivery."""

import asyncio
import copy

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from velocista.domain.shared.errors import DomainError, NotFound, Validation
from velocista.infrastructure.config.settings import settings
from velocista.infrastructure.realtime.device_gateway import RealtimeDeviceGateway
from velocista.infrastructure.realtime.registry import device_status, hub
from velocista.interface.rest.devices.router import router as device_router
from velocista.interface.websocket.contract.manifest import Manifest
from velocista.interface.websocket.contract.translation import translate_payload
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


@pytest.fixture
def client(monkeypatch):
    hub.connections.clear()
    hub.consoles.clear()
    monkeypatch.setattr(hub, "message_handler", None)
    monkeypatch.setattr(hub, "message_handler", None)
    monkeypatch.setattr(hub, "message_handler", None)
    monkeypatch.setattr(settings, "auth_required", False, raising=False)
    app = FastAPI()
    app.include_router(ws_router)
    app.include_router(device_router)

    @app.exception_handler(DomainError)
    async def errors(request, exc):
        code = 422 if isinstance(exc, Validation) else 404 if isinstance(exc, NotFound) else 409
        return JSONResponse(status_code=code, content={"reason": exc.reason, "detail": exc.detail})

    with TestClient(app) as result:
        yield result
    hub.connections.clear()
    hub.consoles.clear()


def frame(type, data, seq=1):
    return dict(type=type, data=data, seq=seq, ts=10)


def connect_robot(client):
    return client.websocket_connect("/ws/robot?token=" + settings.device_token_robot)


def test_bad_device_token(client):
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect("/ws/robot?token=bad"):
            pass
    assert error.value.code == 1008
    assert not device_status()["robot"]


def test_manifest_relay_commands_ack_and_disconnect(client):
    with client.websocket_connect("/ws/console") as console:
        assert console.receive_json()["data"]["devices"] == {"robot": False, "timer": False}
        with connect_robot(client) as robot:
            assert console.receive_json()["data"] == {"device": "robot", "connected": True}
            robot.send_json(frame("manifest", MANIFEST))
            assert robot.receive_json()["data"]["ok"] is True
            message = console.receive_json()
            assert message["type"] == "manifest" and message["sender"] == "robot"
            assert message["data"]["channels"][1]["name"] == "bateria_v"
            assert client.get("/api/devices/robot/manifest").json()["id"] == "racer"
            robot.send_json(frame("status", STATUS, 2))
            assert console.receive_json()["data"]["state"] == "ready"
            response = client.post(
                "/api/devices/robot/commands",
                json={"type": "mode", "data": {"mode": "competition"}},
            )
            assert response.status_code == 202
            command = robot.receive_json()
            assert command["type"] == "mode" and command["data"] == {"mode": "competition"}
            robot.send_json(frame("ack", {"ok": True}, command["seq"]))
            assert console.receive_json()["type"] == "ack"
        assert console.receive_json()["data"]["connected"] is False
        assert client.get("/api/devices/robot/manifest").status_code == 404
    assert device_status() == {"robot": False, "timer": False}


@pytest.mark.parametrize("value", [{}, [], None, "invalid"])
def test_invalid_config_is_422_even_without_manifest(client, value):
    response = client.post(
        "/api/devices/robot/commands", json={"type": "mode", "data": {"mode": value}}
    )
    assert response.status_code == 422 and response.json()["reason"] == "invalid_command"
    with pytest.raises(Validation):
        asyncio.run(RealtimeDeviceGateway().apply_mode("racer", value))


def test_guard_order_and_busy(client):
    assert (
        client.post("/api/devices/robot/commands", json={"type": "stop"}).json()["reason"]
        == "no_manifest"
    )
    with connect_robot(client) as robot:
        manifest = copy.deepcopy(MANIFEST)
        manifest["commands"].remove("line")
        robot.send_json(frame("manifest", manifest))
        robot.receive_json()
        assert (
            client.post(
                "/api/devices/robot/commands", json={"type": "line", "data": {"color": "black"}}
            ).json()["reason"]
            == "unknown_command"
        )
        status = STATUS | {"state": "running", "mode": "competition"}
        robot.send_json(frame("status", status, 2))
        # Flush WebSocket processing through a following acknowledged event.
        robot.send_json(frame("event", {"code": "sync", "level": "info", "message": "sync"}, 3))
        robot.receive_json()
        assert (
            client.post(
                "/api/devices/robot/commands", json={"type": "mode", "data": {"mode": "test"}}
            ).json()["reason"]
            == "competition_locked"
        )
        robot.send_json(frame("status", status | {"mode": "test"}, 4))
        robot.send_json(frame("event", {"code": "sync", "level": "info", "message": "sync"}, 5))
        robot.receive_json()
        assert (
            client.post(
                "/api/devices/robot/commands", json={"type": "mode", "data": {"mode": "test"}}
            ).json()["reason"]
            == "busy"
        )
        assert client.post("/api/devices/robot/commands", json={"type": "stop"}).status_code == 202
        assert robot.receive_json()["type"] == "stop"


def test_legacy_translation_and_duplicate_ack(client):
    with client.websocket_connect("/ws/console") as console, connect_robot(client) as robot:
        console.receive_json()
        console.receive_json()
        legacy = translate_payload(MANIFEST, reverse=True)
        robot.send_json({"tipo": "manifiesto", "datos": legacy, "seq": 1, "ts": 0})
        assert robot.receive_json()["tipo"] == "ack"
        public = console.receive_json()
        assert public["data"]["commands"] == MANIFEST["commands"]
        assert public["data"]["frequencies"]["status_hz"] == 1
        robot.send_json({"tipo": "manifiesto", "datos": legacy, "seq": 1, "ts": 0})
        assert robot.receive_json()["seq"] == 1
        response = client.post(
            "/api/devices/robot/commands", json={"type": "line", "data": {"color": "white"}}
        )
        assert response.status_code == 202
        assert robot.receive_json()["datos"] == {"color": "blanca"}
        robot.send_json(
            {
                "tipo": "evento",
                "datos": {"codigo": "after_duplicate", "nivel": "info", "mensaje": "ok"},
                "seq": 2,
                "ts": 0,
            }
        )
        robot.receive_json()
        assert console.receive_json()["type"] == "event"  # duplicate manifest was not relayed


def test_signals_order_and_manifest_first(client):
    with client.websocket_connect("/ws/console") as console, connect_robot(client) as robot:
        console.receive_json()
        console.receive_json()
        robot.send_json(frame("status", STATUS))
        assert console.receive_json()["data"]["code"] == "no_manifest"
        robot.send_json(frame("manifest", MANIFEST, 2))
        robot.receive_json()
        console.receive_json()
        robot.send_json(frame("signals", {"t_ms": 100, "channels": {"error": 1}}, 3))
        assert console.receive_json()["data"]["t_ms"] == 100
        robot.send_json(frame("signals", {"t_ms": 99, "channels": {"error": 2}}, 4))
        robot.send_json(frame("signals", {"t_ms": 100, "channels": {"error": 3}}, 5))
        robot.send_json(frame("signals", {"t_ms": 101, "channels": {"error": 4}}, 6))
        assert console.receive_json()["data"]["t_ms"] == 101


def test_timer_relay_and_command(client):
    assert client.post("/api/devices/timer/commands", json={"type": "rearm"}).status_code == 503
    with client.websocket_connect("/ws/console") as console:
        console.receive_json()
        with client.websocket_connect("/ws/timer?token=" + settings.device_token_timer) as timer:
            console.receive_json()
            timer.send_json(
                frame(
                    "hello",
                    {"id": "finish", "firmware": "1.0", "contract": "2.0", "debounce_ms": 100},
                )
            )
            timer.receive_json()
            assert console.receive_json()["type"] == "hello"
            timer.send_json(
                frame(
                    "crossing", {"crossing_number": 1, "lap_time_ms": None, "timestamp_us": 1000}, 2
                )
            )
            timer.receive_json()
            assert console.receive_json()["type"] == "crossing"
            assert (
                client.post("/api/devices/timer/commands", json={"type": "rearm"}).status_code
                == 202
            )
            assert timer.receive_json()["type"] == "rearm"


def test_console_origin_denied(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/ws/console", headers={"origin": "https://untrusted.example"}
        ):
            pass


def test_manifest_validation_rejects_unknown_channel_and_duplicate_names():
    bad = copy.deepcopy(MANIFEST)
    bad["channels"].append(bad["channels"][0])
    with pytest.raises(ValueError):
        Manifest.model_validate(bad)


def test_english_battery_and_lap_fields_are_accepted():
    manifest = copy.deepcopy(MANIFEST)
    manifest["id"] = "r_08e09345813f4e6eb0dc6bb78a17077d"
    manifest["channels"][1]["name"] = "battery_v"
    assert Manifest.model_validate(manifest)
    from velocista.interface.websocket.contract.robot import Lap

    lap = Lap.model_validate(
        {
            "lap_id": 1,
            "internal_time_ms": 12500,
            "accumulated_error": 0.8,
            "lines_lost": 0,
            "battery_v": 7.3,
        }
    )
    assert lap.lost_lines == 0
