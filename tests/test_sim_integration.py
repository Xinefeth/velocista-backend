import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from websockets.asyncio.server import serve

from velocista.domain.shared.errors import Conflict
from velocista.infrastructure.integrations.velocista_sim.client import SimulatorClient
from velocista.infrastructure.integrations.velocista_sim.contract import validate
from velocista.infrastructure.integrations.velocista_sim.session import SessionState
from velocista.infrastructure.realtime.registry import Registry

FIXTURES = Path(__file__).parent / "fixtures/sim_contract"


def fixture(group, name):
    return json.loads((FIXTURES / f"valid/{group}/{name}.json").read_text(encoding="utf-8"))[
        "message"
    ]


@pytest.mark.parametrize(
    "path",
    [
        p
        for p in FIXTURES.glob("valid/*/*.json")
        if p.parent.name in {"hello", "config", "telemetry", "event", "catalog", "error"}
    ],
)
def test_official_valid_examples(path):
    example = json.loads(path.read_text(encoding="utf-8"))
    hello = fixture("hello", example["hello"]) if "hello" in example else None
    validate(example["message"], hello)


@pytest.mark.parametrize(
    "path",
    [
        p
        for p in FIXTURES.glob("invalid/*/*.json")
        if p.parent.name in {"hello", "config", "telemetry", "event", "catalog", "error"}
    ],
)
def test_official_invalid_examples(path):
    example = json.loads(path.read_text(encoding="utf-8"))
    hello = fixture("hello", example["hello"]) if "hello" in example else None
    with pytest.raises(ValueError):
        validate(example["message"], hello)


def event(name, run="r1", **fields):
    return {"type": "event", "v": 1, "t_ms": 12001, "event": name, "run_id": run, **fields}


def finished(run="r1"):
    config = fixture("config", "pdf-config")
    return event(
        "run_finished",
        run,
        summary={
            "laps": 0,
            "best_lap_ms": None,
            "avg_lap_ms": None,
            "off_tracks": 0,
            "track_id": config["track_id"],
            "config_changed": False,
            "config": {key: config[key] for key in ("controller", "params", "base_speed")},
        },
    )


def test_sequence_and_two_runs():
    state = SessionState()
    with pytest.raises(ValueError):
        state.accept(fixture("config", "pdf-config"))
    state.accept(fixture("hello", "sim-default"))
    state.accept(fixture("config", "pdf-config"))
    sample = fixture("telemetry", "idle-no-run")
    sample["seq"] = 0
    assert state.accept(sample)
    assert not state.accept(sample)
    assert state.accept({**sample, "seq": 3})
    assert state.lost == 2
    for run in ("r1", "r2"):
        assert state.accept(event("run_started", run))
        assert not state.accept(event("run_started", run))
        assert state.accept(event("lap", run, lap=1, lap_ms=100))
        assert not state.accept(event("lap", run, lap=1, lap_ms=100))
        assert state.accept(finished(run))
    with pytest.raises(ValueError):
        state.accept({**sample, "seq": 4, "t_ms": 1})


class MemoryStore:
    def __init__(self):
        self.items = []
        self.fail = False
        self.attempts = 0
        self.preflight_args = []

    def preflight(self, setup_id=None, robot_id=None):
        self.preflight_args.append((setup_id, robot_id))

    def recover(self):
        pass

    def write(self, batch):
        self.attempts += 1
        if self.fail:
            raise OSError("database unavailable")
        self.items.extend(copy.deepcopy(batch))


def settings(url):
    return SimpleNamespace(
        sim_ws_url=url,
        sim_queue_size=64,
        sim_robot_id=None,
        sim_track_id=None,
        sim_internal_robot_id="internal",
        sim_command_timeout=0.3,
        sim_reconnect_max_seconds=1,
        sim_store_telemetry=True,
    )


async def until(predicate, timeout=5):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_server_commands_reconnect_and_persistence_retry():
    connections = []

    async def server(ws):
        connections.append(ws)
        hello = fixture("hello", "sim-default")
        hello["session_id"] = f"session-{len(connections)}"
        await ws.send(json.dumps(hello))
        await ws.send(json.dumps(fixture("config", "pdf-config")))
        async for raw in ws:
            cmd = json.loads(raw)
            if cmd["cmd"] == "start":
                await ws.send(json.dumps(event("run_started")))
            elif cmd["cmd"] == "stop":
                await ws.send(json.dumps(finished()))
            elif cmd["cmd"] == "set_config":
                await ws.send(
                    json.dumps(
                        {
                            "type": "error",
                            "v": 1,
                            "t_ms": 12001,
                            "code": "out_of_range",
                            "message": "Rejected",
                            "cmd": "set_config",
                        }
                    )
                )

    async with serve(server, "127.0.0.1", 0) as server_instance:
        port = server_instance.sockets[0].getsockname()[1]
        store, hub = MemoryStore(), Registry()
        client = SimulatorClient(settings(f"ws://127.0.0.1:{port}"), store, hub)
        await client.start()
        try:
            await until(lambda: client.status == "ready")
            await client.command("start", {"setup_id": 7}, robot_id="robot-001")
            assert client.state.active == "r1"
            assert store.preflight_args == [(7, "robot-001")]
            await until(
                lambda: any(
                    item["message"].get("event") == "run_started" for item in store.items
                )
            )
            started = next(
                item
                for item in store.items
                if item["message"].get("event") == "run_started"
            )
            assert (started["robot_id"], started["setup_id"]) == ("robot-001", 7)
            await client.command("stop", {})
            assert client.state.active is None
            with pytest.raises(Conflict, match="Rejected"):
                await client.command("set_config", {"base_speed": 100})
            store.fail = True
            sample = fixture("telemetry", "idle-no-run")
            sample.update(seq=0, t_ms=12002)
            await connections[-1].send(json.dumps(sample))
            await until(lambda: not client.persistence_ok)
            store.fail = False
            await until(lambda: client.persistence_ok)
            await connections[-1].close()
            await until(lambda: len(connections) == 2 and client.status == "ready")
            assert client.sid == "sim:session-2"
            assert any(i["message"]["type"] == "disconnect" for i in store.items)
            with pytest.raises(Conflict, match="Timed out"):
                await client.command("set_rate", {"hz": 20})
            assert client.uncertain
            with pytest.raises(Conflict, match="Reconnect"):
                await client.command("start", {})
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_slow_console_does_not_block_other_console():
    class Console:
        def __init__(self, slow=False):
            self.messages = []
            self.slow = slow

        async def send_json(self, frame):
            if self.slow:
                await asyncio.sleep(10)
            self.messages.append(frame)

        async def close(self, **kwargs):
            pass

    hub = Registry()
    slow, fast = Console(True), Console()
    hub.consoles.update((slow, fast))
    try:
        for n in range(10):
            await hub.broadcast("sim", "telemetry", {"seq": n})
        await until(lambda: len(fast.messages) == 10, timeout=1)
        assert slow.messages == []
    finally:
        await hub.close_relays()
