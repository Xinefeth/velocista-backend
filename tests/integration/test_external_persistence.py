"""Real PostgreSQL persistence and an opt-in deployed-service acceptance test."""

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from velocista.infrastructure.config.settings import Settings, settings
from velocista.infrastructure.integrations.velocista_sim.client import SimulatorClient
from velocista.infrastructure.integrations.velocista_sim.persistence import Store
from velocista.infrastructure.persistence import models  # noqa: F401
from velocista.infrastructure.persistence.db import Base, engine
from velocista.infrastructure.persistence.models.builder import RobotModel, VersionModel
from velocista.infrastructure.persistence.models.external import ExternalTelemetryModel
from velocista.infrastructure.persistence.models.optimization import ControllerModel, SetupModel
from velocista.infrastructure.persistence.models.rules import ProfileModel
from velocista.infrastructure.persistence.models.runs import LapModel, RunModel
from velocista.infrastructure.persistence.repositories.run_history_repository import (
    SqlAlchemyRunHistoryRepository,
)
from velocista.infrastructure.realtime.registry import Registry
from velocista.interface.rest.runs.schemas import RunOut


def test_alembic_upgrade_and_empty_downgrade():
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    root = Path(__file__).parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option(
        "script_location", str(root / "src/velocista/infrastructure/persistence/migrations")
    )
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            schema = "migration_test_" + uuid4().hex
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0005"
            command.downgrade(config, "0004")
            command.upgrade(config, "head")
        finally:
            transaction.rollback()


@pytest.fixture
def external_store():
    schema = "external_test_" + uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = create_engine(
        settings.database_url, connect_args={"options": f"-csearch_path={schema}"}
    )
    factory = sessionmaker(scoped, expire_on_commit=False)
    cfg = Settings(_env_file=None, sim_internal_robot_id="integration", sim_profile_id="club")
    try:
        Base.metadata.create_all(scoped)
        with factory.begin() as session:
            robot = RobotModel(
                id="integration", name="Integration", short_code="INT", type="racer", firmware="1"
            )
            session.add(robot)
            session.flush()
            version = VersionModel(
                robot_id=robot.id, ordinal=1, date=datetime.now(UTC), note="test", status="current"
            )
            session.add(version)
            session.flush()
            robot.current_version_id = version.id
            session.add(
                ControllerModel(
                    id="pid",
                    name="PID",
                    short_name="PID",
                    description="PID",
                    parameters=[],
                    presets={},
                )
            )
            session.add(
                ProfileModel(
                    id="club", competition="Club", label="Club", category="Racer", rules={}
                )
            )
            session.flush()
            setup = SetupModel(
                version_id=version.id,
                controller_id="pid",
                name="Test",
                parameters={},
                controller_snapshot={"id": "pid"},
            )
            session.add(setup)
            session.flush()
            cfg.sim_setup_id = setup.id
        yield Store(cfg, factory), cfg, factory
    finally:
        scoped.dispose()
        # The generated identifier is exclusively owned by this fixture.
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_runs_laps_replay_nullable_history_and_restart(external_store):
    import json
    from pathlib import Path

    store, cfg, factory = external_store
    fixtures = Path(__file__).parents[1] / "fixtures/sim_contract/valid"

    def load(group, name):
        return json.loads((fixtures / group / f"{name}.json").read_text(encoding="utf-8"))[
            "message"
        ]

    hello = load("hello", "sim-default")
    config = load("config", "pdf-config")
    sid = "sim:" + hello["session_id"]

    def item(message, run=None):
        return dict(
            message=message,
            session_id=sid,
            received_at=datetime.now(UTC),
            lost=0,
            run_id=run,
            setup_id=cfg.sim_setup_id,
        )

    store.preflight()
    store.write([item(hello), item(config)])
    start = item({"type": "event", "event": "run_started", "run_id": "r1", "t_ms": 10}, "r1")
    lap = item({"type": "event", "event": "lap", "lap": 1, "lap_ms": 1000}, "r1")
    store.write([start, lap])
    store.write([start, lap])
    summary = dict(
        laps=1,
        best_lap_ms=1000,
        avg_lap_ms=1000,
        off_tracks=0,
        track_id=config["track_id"],
        config_changed=False,
        config={key: config[key] for key in ("controller", "params", "base_speed")},
    )
    store.write(
        [item({"type": "event", "event": "run_finished", "summary": summary, "t_ms": 1010}, "r1")]
    )
    start2 = item({"type": "event", "event": "run_started", "run_id": "r2", "t_ms": 1020}, "r2")
    store.write([start2])
    store.recover()
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(RunModel)) == 2
        assert session.scalar(select(func.count()).select_from(LapModel)) == 1
        results = SqlAlchemyRunHistoryRepository(session).list_runs()["items"]
        for result in results:
            RunOut.model_validate(result)
            assert result["j"] is None
            assert result["accumulated_error"] is None
            assert result["mode"] is None
        assert {row["closure_status"] for row in results} == {"finished", "interrupted"}
        assert any(row["optimization_eligible"] for row in results)


def test_telemetry_only_for_open_runs_with_stride_and_cap(external_store):
    import json
    from pathlib import Path

    store, cfg, factory = external_store
    cfg.sim_telemetry_stride = 2
    cfg.sim_max_telemetry_rows_per_run = 3
    fixtures = Path(__file__).parents[1] / "fixtures/sim_contract/valid"

    def load(group, name):
        return json.loads((fixtures / group / f"{name}.json").read_text(encoding="utf-8"))[
            "message"
        ]

    hello, config = load("hello", "sim-default"), load("config", "pdf-config")
    sample = load("telemetry", "idle-no-run")
    sid = "sim:" + hello["session_id"]

    def item(message, run=None):
        return dict(
            message=message,
            session_id=sid,
            received_at=datetime.now(UTC),
            lost=0,
            run_id=run,
            setup_id=cfg.sim_setup_id,
        )

    def frame(seq, run=None):
        return item({**sample, "seq": seq, "run_id": run or False}, run)

    def stored():
        with factory() as session:
            return session.scalars(
                select(ExternalTelemetryModel.seq).order_by(ExternalTelemetryModel.seq)
            ).all()

    store.write([item(hello), item(config)])
    # Sin corrida (idle) no se inserta nada.
    store.write([frame(n) for n in range(6)])
    assert stored() == []
    # Los frames llegan en el mismo lote que run_started: no se pierden.
    start = item({"type": "event", "event": "run_started", "run_id": "r1", "t_ms": 10}, "r1")
    store.write([start, *[frame(n, "r1") for n in range(6, 12)]])
    # Stride 2 (seq pares) y tope 3: 6, 8, 10 entran; el resto no.
    assert stored() == [6, 8, 10]
    # El tope se mantiene entre lotes y se deja un diagnóstico, sin romper vueltas ni cierre.
    lap = item({"type": "event", "event": "lap", "lap": 1, "lap_ms": 1000}, "r1")
    store.write([*[frame(n, "r1") for n in range(12, 20)], lap])
    assert stored() == [6, 8, 10]
    summary = dict(
        laps=1,
        best_lap_ms=1000,
        avg_lap_ms=1000,
        off_tracks=0,
        track_id=config["track_id"],
        config_changed=False,
        config={key: config[key] for key in ("controller", "params", "base_speed")},
    )
    store.write(
        [item({"type": "event", "event": "run_finished", "summary": summary, "t_ms": 99}, "r1")]
    )
    # Tras run_finished vuelve a no guardarse nada.
    store.write([frame(n) for n in range(20, 24)])
    assert stored() == [6, 8, 10]
    with factory() as session:
        run = session.scalar(select(RunModel))
        assert run.closure_status == "finished"
        assert run.context_snapshot["summary"] == summary
        assert session.scalar(select(func.count()).select_from(LapModel)) == 1
        assert (
            "telemetry_capped" in session.get(models.external.ExternalSessionModel, sid).diagnostics
        )


@pytest.mark.skipif(os.getenv("SIM_LIVE_TEST") != "1", reason="Opt-in deployed WebSocket test")
@pytest.mark.asyncio
async def test_deployed_simulator_with_postgres(external_store):
    store, cfg, factory = external_store
    cfg.sim_command_timeout = 10
    client = SimulatorClient(cfg, store, Registry())

    async def until(predicate, seconds=25):
        async with asyncio.timeout(seconds):
            while not predicate():
                await asyncio.sleep(0.05)

    await client.start()
    try:
        await until(lambda: client.status == "ready")
        first_sid = client.sid
        await client.command("list", {})
        await client.command("set_config", {"base_speed": 80})
        for _ in range(2):
            await client.command("start", {})
            await asyncio.sleep(0.3)
            if client.state.active:
                await client.command("stop", {})
            await until(lambda: client.state.active is None)
        await client.command("set_config", {"base_speed": 0})
        await client.command("start", {})
        await client.ws.close()
        await until(lambda: client.status == "ready" and client.sid != first_sid)
        await client.command("start", {})
        await client.command("stop", {})
    finally:
        await client.close()
    with factory() as session:
        rows = SqlAlchemyRunHistoryRepository(session).list_runs()["items"]
        assert len(rows) == 4
        assert sum(row["closure_status"] == "interrupted" for row in rows) == 1
        assert len({row["external_session_id"] for row in rows}) == 2
        assert session.scalar(select(func.count()).select_from(ExternalTelemetryModel)) > 0
        for row in rows:
            RunOut.model_validate(row)
