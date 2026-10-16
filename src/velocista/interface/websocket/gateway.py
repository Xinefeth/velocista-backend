"""Authenticated device gateway and English console relay."""

import hmac
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from velocista.infrastructure.config.settings import settings
from velocista.infrastructure.realtime.registry import Connection, device_status, hub
from velocista.interface.websocket.contract.base import Envelope
from velocista.interface.websocket.contract.catalog import (
    InvalidMessage,
    requires_ack,
    validate_data,
)
from velocista.interface.websocket.contract.manifest import Manifest
from velocista.interface.websocket.contract.robot import Signals, Status
from velocista.interface.websocket.contract.translation import translate_payload, translate_type
from velocista.interface.websocket.contract.validation import check_channels

router = APIRouter()


async def process(device, connection, raw):
    try:
        frame = json.loads(raw)
        connection.legacy = "tipo" in frame
        if connection.legacy:
            envelope = Envelope.model_validate(frame)
            type = translate_type(envelope.type)
            data = translate_payload(envelope.data)
        else:
            envelope = Envelope.model_validate(frame)
            type, data = envelope.type, envelope.data
        model = validate_data(device, type, data)
    except (json.JSONDecodeError, ValidationError, InvalidMessage, TypeError) as exc:
        await hub.event("invalid_message", f"Invalid message from {device}", str(exc)[:300])
        return
    with_ack = requires_ack(device, type)
    if with_ack and envelope.seq in connection.received:
        await hub.send(device, "ack", {"ok": True}, seq=envelope.seq)
        return
    if device == "robot":
        if isinstance(model, Manifest):
            connection.manifest = model
            connection.last_status = None
            connection.last_t_ms = -1
            connection.warnings.clear()
        elif connection.manifest is None:
            await hub.event("no_manifest", "Robot must send its manifest first")
            return
        else:
            if isinstance(model, Signals):
                if model.t_ms <= connection.last_t_ms:
                    return
                connection.last_t_ms = model.t_ms
            if isinstance(model, Status):
                connection.last_status = model
            if isinstance(model, (Status, Signals)):
                group = "status" if isinstance(model, Status) else "signals"
                for warning in check_channels(connection.manifest, group, model.channels):
                    if warning not in connection.warnings:
                        connection.warnings.add(warning)
                        await hub.event("invalid_channel", warning)
    if hub.message_handler is not None:
        try:
            await run_in_threadpool(
                hub.message_handler, device, type, model.model_dump(exclude_none=True)
            )
        except Exception as exc:
            await hub.event(
                "ingestion_failed", "Device message could not be saved", exc.__class__.__name__
            )
            return
    if with_ack:
        connection.received.append(envelope.seq)
        await hub.send(device, "ack", {"ok": True}, seq=envelope.seq)
    await hub.broadcast(
        device, type, model.model_dump(exclude_none=True), envelope.seq, envelope.ts
    )


async def serve(ws, device, expected):
    token = ws.headers.get("x-device-token") or ws.query_params.get("token")
    if not token or not expected or not hmac.compare_digest(token, expected):
        await ws.close(code=1008)
        return
    await ws.accept()
    connection = Connection(ws)
    previous = hub.connections.get(device)
    hub.connections[device] = connection
    if previous:
        try:
            await previous.ws.close(code=1012)
        except (RuntimeError, OSError):
            pass
    await hub.broadcast("api", "link", {"device": device, "connected": True})
    try:
        while hub.connections.get(device) is connection:
            raw = await ws.receive_text()
            if hub.connections.get(device) is connection:
                await process(device, connection, raw)
    except WebSocketDisconnect:
        pass
    finally:
        if hub.connections.get(device) is connection:
            hub.connections.pop(device, None)
            await hub.broadcast("api", "link", {"device": device, "connected": False})


@router.websocket("/ws/robot")
async def ws_robot(ws: WebSocket):
    await serve(ws, "robot", settings.device_token_robot)


@router.websocket("/ws/timer")
async def ws_timer(ws: WebSocket):
    await serve(ws, "timer", settings.device_token_timer)


@router.websocket("/ws/console")
async def ws_console(ws: WebSocket):
    origin = ws.headers.get("origin")
    if origin and origin not in settings.cors_list:
        await ws.close(code=1008)
        return
    if getattr(settings, "auth_required", False):
        from velocista.infrastructure.security import decode_access_token

        token = ws.query_params.get("token") or ws.headers.get("authorization", "").removeprefix(
            "Bearer "
        )
        try:
            decode_access_token(token)
        except (ValueError, TypeError):
            await ws.close(code=1008)
            return
    await ws.accept()
    hub.consoles.add(ws)
    await ws.send_json(
        {
            "sender": "api",
            "type": "hello",
            "seq": 0,
            "ts": 0,
            "data": {"devices": device_status()},
            "received_ms": __import__("time").time_ns() // 1_000_000,
        }
    )
    # Send current snapshots when a console reconnects after the devices.
    for device, connection in list(hub.connections.items()):
        for type, model in (("manifest", connection.manifest), ("status", connection.last_status)):
            if model:
                await ws.send_json(
                    {
                        "sender": device,
                        "type": type,
                        "seq": 0,
                        "ts": 0,
                        "data": model.model_dump(exclude_none=True),
                        "received_ms": __import__("time").time_ns() // 1_000_000,
                    }
                )
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.consoles.discard(ws)
