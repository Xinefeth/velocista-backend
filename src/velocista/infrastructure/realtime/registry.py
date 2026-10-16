"""Single-process live connection registry shared by REST and WebSocket adapters."""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

DEVICES = ("robot", "timer")


def milliseconds() -> int:
    return int(time.time() * 1000)


@dataclass
class Connection:
    ws: Any
    manifest: Any = None
    last_status: Any = None
    legacy: bool = True
    last_t_ms: int = -1
    seq_out: int = 0
    received: deque = field(default_factory=lambda: deque(maxlen=256))
    warnings: set = field(default_factory=set)
    send_lock: Any = field(default_factory=asyncio.Lock)

    def next_seq(self):
        self.seq_out = (self.seq_out + 1) % 2**32
        return self.seq_out


class Registry:
    def __init__(self):
        self.connections: dict[str, Connection] = {}
        self.consoles: set = set()
        self.message_handler = None

    async def broadcast(self, sender, type, data, seq=0, ts=0):
        frame = dict(
            sender=sender, type=type, data=data, seq=seq, ts=ts, received_ms=milliseconds()
        )
        for ws in list(self.consoles):
            try:
                await ws.send_json(frame)
            except (RuntimeError, OSError):
                self.consoles.discard(ws)

    async def event(self, code, message, detail=""):
        await self.broadcast(
            "api",
            "event",
            dict(code=code, level="warning", message=message, data={"detail": detail}),
        )

    async def send(self, device, type, data, *, seq=None):
        from velocista.interface.websocket.contract.translation import (
            REVERSE_VALUES,
            translate_payload,
        )

        connection = self.connections[device]
        async with connection.send_lock:
            if seq is None:
                seq = connection.next_seq()
            if connection.legacy:
                frame = dict(
                    tipo=REVERSE_VALUES.get(type, type),
                    datos=translate_payload(data, reverse=True),
                    seq=seq,
                    ts=milliseconds() % 2**32,
                )
            else:
                frame = dict(type=type, data=data, seq=seq, ts=milliseconds() % 2**32)
            await connection.ws.send_json(frame)
        return seq


hub = Registry()


def device_status():
    return {name: name in hub.connections for name in DEVICES}


def is_connected(name):
    return name in hub.connections


def robot_running(robot_id):
    connection = hub.connections.get("robot")
    return bool(
        connection
        and connection.manifest
        and connection.manifest.id == robot_id
        and connection.last_status
        and connection.last_status.state == "running"
    )
