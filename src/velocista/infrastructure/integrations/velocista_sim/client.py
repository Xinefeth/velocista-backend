"""One managed connection per backend process, with bounded ordered persistence."""

import asyncio
import contextlib
import json
import logging
import random
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from websockets.asyncio.client import connect

from velocista.domain.shared.errors import Conflict, DeviceUnavailable

from .adapter import telemetry
from .commands import confirms, translate
from .session import SessionState

logger = logging.getLogger(__name__)


class SimulatorClient:
    def __init__(self, settings, store, hub):
        self.settings, self.store, self.hub = settings, store, hub
        self.state = SessionState()
        self.status = "disconnected"
        self.queue = asyncio.Queue(maxsize=settings.sim_queue_size)
        self.lock = asyncio.Lock()
        self.ws = None
        self.pending = None
        self.task = self.writer = None
        self.persistence_ok = False
        self.last_error = None
        self.dropped = 0
        self.command_seq = 0
        self.uncertain = False
        self.run_context = None

    @property
    def sid(self):
        hello = self.state.hello
        return f"{hello['source']}:{hello['session_id']}" if hello else None

    def snapshot(self):
        return {
            "state": self.status,
            "session_id": self.sid,
            "hello": self.state.hello,
            "config": self.state.config,
            "telemetry": telemetry(self.state.telemetry) if self.state.telemetry else None,
            "active_run_id": self.state.active,
            "lost_samples": self.state.lost,
            "dropped_samples": self.dropped,
            "persistence_ok": self.persistence_ok,
            "queue_size": self.queue.qsize(),
            "last_error": self.last_error,
            "commands_uncertain": self.uncertain,
            "internal_robot_id": self.settings.sim_internal_robot_id,
        }

    async def start(self):
        self.writer = asyncio.create_task(self._writer(), name="sim-persistence")
        self.task = asyncio.create_task(self._connect(), name="sim-connection")

    async def close(self):
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                await asyncio.wait_for(self.task, timeout=3)
        try:
            await asyncio.wait_for(self.queue.join(), timeout=10)
        except TimeoutError:
            logger.error("Simulation shutdown left %s unpersisted messages", self.queue.qsize())
        if self.writer:
            self.writer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.writer

    def _item(self, frame, run_id=None, *, setup_id=None, robot_id=None):
        return {
            "message": frame,
            "session_id": self.sid,
            "received_at": datetime.now(UTC),
            "lost": self.state.lost + self.dropped,
            "setup_id": (
                setup_id
                if setup_id is not None
                else getattr(self.settings, "sim_setup_id", None)
            ),
            "robot_id": (
                robot_id
                if robot_id is not None
                else getattr(self.settings, "sim_internal_robot_id", None)
            ),
            "run_id": run_id if run_id is not None else self.state.active,
        }

    def enqueue(self, frame, run_id=None):
        # Reserve capacity for lifecycle messages; telemetry is expendable, events aren't.
        if frame["type"] == "telemetry" and self.queue.qsize() >= self.queue.maxsize - 16:
            self.dropped += 1
            self.last_error = "telemetry_queue_overflow"
            return
        context = self.run_context if (run_id or frame.get("event") == "run_started") else None
        self.queue.put_nowait(
            self._item(frame, run_id, **(context or {}))
        )
        if frame.get("event") == "run_finished":
            self.run_context = None

    async def _writer(self):
        while True:
            try:
                await asyncio.to_thread(self.store.recover)
                self.persistence_ok = True
                break
            except Exception:
                self.last_error = "persistence_recovery_failed"
                logger.exception("External session recovery failed")
                await asyncio.sleep(2)
        while True:
            batch = [await self.queue.get()]
            await asyncio.sleep(0.05)
            while len(batch) < 100 and not self.queue.empty():
                batch.append(self.queue.get_nowait())
            while True:
                try:
                    await asyncio.to_thread(self.store.write, batch)
                    self.persistence_ok = True
                    for _ in batch:
                        self.queue.task_done()
                    break
                except Exception:
                    self.persistence_ok = False
                    self.last_error = "persistence_failed"
                    logger.exception("External batch retained for retry")
                    await self.hub.broadcast("sim", "diagnostic", self.snapshot())
                    await asyncio.sleep(2)

    def _url(self):
        parts = urlsplit(self.settings.sim_ws_url)
        query = dict(parse_qsl(parts.query))
        for key, value in (
            ("robot", self.settings.sim_robot_id),
            ("track", self.settings.sim_track_id),
        ):
            if value:
                query[key] = value
        return urlunsplit(parts._replace(query=urlencode(query)))

    async def _connect(self):
        delay = 1
        while True:
            # Persist old session closure before reconnecting or accepting further commands.
            await self.queue.join()
            while not self.persistence_ok:
                await asyncio.sleep(0.1)
            self.state = SessionState()
            self.dropped = 0
            self.uncertain = False
            self.status = "connecting"
            await self.hub.broadcast("sim", "connection", self.snapshot())
            try:
                async with connect(
                    self._url(),
                    open_timeout=10,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=1024 * 1024,
                    max_queue=32,
                ) as ws:
                    self.ws = ws
                    for _ in range(2):
                        await self.receive(await asyncio.wait_for(ws.recv(), timeout=10))
                    if not self.state.config:
                        raise ValueError("Invalid handshake")
                    delay = 1
                    async for raw in ws:
                        await self.receive(raw)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = type(exc).__name__
                logger.warning("Simulator connection ended: %s", type(exc).__name__)
            finally:
                self.ws = None
                self.status = "disconnected"
                if self.pending and not self.pending[2].done():
                    self.pending[2].set_exception(
                        DeviceUnavailable(
                            "command_uncertain", "Disconnected before command confirmation"
                        )
                    )
                if self.sid:
                    # Await only on shutdown/connection failure, never in normal acquisition.
                    await self.queue.put(
                        self._item({"type": "disconnect", "reason": "connection_closed"})
                    )
                await self.hub.broadcast("sim", "connection", self.snapshot())
            await asyncio.sleep(delay + random.random() * 0.2)
            delay = min(delay * 2, self.settings.sim_reconnect_max_seconds)

    async def receive(self, raw):
        try:
            message = json.loads(raw)
            previous_lost = self.state.lost
            if not self.state.accept(message):
                return
        except (ValueError, TypeError) as exc:
            self.last_error = f"invalid_message: {str(exc)[:200]}"
            logger.warning("Invalid simulator frame: %s", self.last_error)
            if self.sid and self.queue.qsize() < self.queue.maxsize - 8:
                self.enqueue(
                    {"type": "diagnostic", "code": "invalid_message", "detail": self.last_error}
                )
            await self.hub.broadcast("sim", "diagnostic", {"error": self.last_error})
            return
        self.enqueue(message, message.get("run_id"))
        if message["type"] == "config":
            if (
                self.settings.sim_robot_id
                and self.state.hello["robot"]["id"] != self.settings.sim_robot_id
            ) or (self.settings.sim_track_id and message["track_id"] != self.settings.sim_track_id):
                self.status = "mismatch"
                self.last_error = "Requested robot or track differs from server selection"
            else:
                self.status = "ready"
            await self.hub.broadcast("sim", "connection", self.snapshot())
        if self.pending:
            command, run_id, future = self.pending
            if not future.done():
                if (
                    message["type"] == "error"
                    and message.get("cmd", command["cmd"]) == command["cmd"]
                ):
                    future.set_exception(Conflict(message["code"], message["message"]))
                elif confirms(command, message, run_id):
                    future.set_result(message)
        if self.state.lost != previous_lost:
            await self.hub.broadcast("sim", "diagnostic", {"lost_samples": self.state.lost})
        data = telemetry(message) if message["type"] == "telemetry" else message
        await self.hub.broadcast(
            "sim", message["type"], data, message.get("seq", 0), message["t_ms"]
        )

    async def command(self, kind, data, robot_id=None):
        data = dict(data)
        requested_setup = data.pop("setup_id", None) if kind == "start" else None
        frame = translate(kind, data)
        async with self.lock:
            selected_robot = robot_id or self.settings.sim_internal_robot_id
            if self.status != "ready" or self.ws is None:
                raise DeviceUnavailable("sim_disconnected", "External source is not ready")
            if self.uncertain:
                raise Conflict("command_uncertain", "Reconnect before sending another command")
            selected_setup = data.get("setup_id") if kind == "setup" else requested_setup
            if selected_setup is not None and kind == "setup":
                await asyncio.to_thread(self.store.preflight, selected_setup)
            if frame["cmd"] == "start":
                if self.state.active:
                    raise Conflict("run_active", "A run is already active")
                if not self.persistence_ok:
                    raise DeviceUnavailable(
                        "persistence_unavailable", "Cannot start without persistence"
                    )
                selected_setup = selected_setup or getattr(self.settings, "sim_setup_id", None)
                await asyncio.to_thread(self.store.preflight, selected_setup, selected_robot)
                self.run_context = {"setup_id": selected_setup, "robot_id": selected_robot}
            self.command_seq += 1
            seq = self.command_seq
            future = asyncio.get_running_loop().create_future()
            self.pending = (frame, self.state.active, future)
            result = {"seq": seq, "command": frame["cmd"], "outcome": "uncertain"}
            try:
                await self.ws.send(json.dumps(frame))
                confirmation = await asyncio.wait_for(
                    future, timeout=self.settings.sim_command_timeout
                )
                if selected_setup is not None:
                    self.settings.sim_setup_id = selected_setup
                result.update(outcome="confirmed", confirmation=confirmation)
                return seq
            except TimeoutError as exc:
                self.uncertain = True
                raise Conflict(
                    "command_uncertain", "Timed out; command will not be retried"
                ) from exc
            except Conflict as exc:
                result.update(outcome="rejected", reason=exc.reason)
                raise
            except asyncio.CancelledError:
                self.uncertain = True
                raise
            except Exception as exc:
                self.uncertain = True
                raise DeviceUnavailable(
                    "command_uncertain", "Delivery could not be confirmed"
                ) from exc
            finally:
                self.pending = None
                if not future.done():
                    future.cancel()
                if self.sid and self.queue.qsize() < self.queue.maxsize - 8:
                    self.enqueue({"type": "diagnostic", "code": "last_command", "detail": result})
                await self.hub.broadcast("sim", "command_result", result, seq)
