"""Ordered batch persistence; each batch is atomic and safe to retry."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from velocista.domain.shared.errors import Conflict
from velocista.infrastructure.persistence.db import SessionLocal
from velocista.infrastructure.persistence.models.builder import RobotModel, VersionModel
from velocista.infrastructure.persistence.models.external import (
    ExternalSessionModel,
    ExternalTelemetryModel,
)
from velocista.infrastructure.persistence.models.optimization import SetupModel
from velocista.infrastructure.persistence.models.rules import ProfileModel
from velocista.infrastructure.persistence.models.runs import LapModel, RunModel
from velocista.infrastructure.persistence.repositories.rules_repository import as_dict


class Store:
    def __init__(self, settings, factory=SessionLocal):
        self.settings = settings
        self.factory = factory

    def context(self, session, setup_id=None, robot_id=None):
        cfg = self.settings
        robot = (
            session.get(RobotModel, robot_id or cfg.sim_internal_robot_id)
            if (robot_id or cfg.sim_internal_robot_id)
            else None
        )
        selected = setup_id or cfg.sim_setup_id
        setup = session.get(SetupModel, selected) if selected else None
        profile = session.get(ProfileModel, cfg.sim_profile_id) if cfg.sim_profile_id else None
        version = session.get(VersionModel, setup.version_id) if setup else None
        if (
            not robot
            or robot.archived
            or not setup
            or setup.archived
            or not profile
            or not version
            or version.robot_id != robot.id
            or setup.controller_id != "pid"
        ):
            raise Conflict(
                "sim_context_missing", "Configure a valid internal robot, PID setup and profile"
            )
        return robot, version, setup, profile

    def preflight(self, setup_id=None, robot_id=None):
        with self.factory() as session:
            self.context(session, setup_id, robot_id)

    def recover(self):
        with self.factory.begin() as session:
            for acquisition in session.scalars(
                select(ExternalSessionModel).where(ExternalSessionModel.closed_at.is_(None))
            ):
                self._close(session, acquisition, datetime.now(UTC), "backend_restart")

    def _close(self, session, acquisition, now, reason):
        acquisition.closed_at = now
        acquisition.state = "disconnected"
        acquisition.diagnostics = {**acquisition.diagnostics, "close_reason": reason}
        for run in session.scalars(
            select(RunModel).where(
                RunModel.external_session_id == acquisition.id, RunModel.closed_at.is_(None)
            )
        ):
            run.closed_at = now
            run.closure_status = "interrupted"
            run.context_snapshot = {**run.context_snapshot, "interruption_reason": reason}

    def write(self, batch):
        with self.factory.begin() as session:
            for item in batch:
                self._write(session, item)

    def _write(self, session, item):
        frame, now, sid = item["message"], item["received_at"], item["session_id"]
        kind = frame["type"]
        acquisition = session.get(ExternalSessionModel, sid)
        if kind == "hello":
            if acquisition is None:
                robot = (
                    session.get(RobotModel, self.settings.sim_internal_robot_id)
                    if self.settings.sim_internal_robot_id
                    else None
                )
                session.add(
                    ExternalSessionModel(
                        id=sid,
                        source=frame["source"],
                        external_id=frame["session_id"],
                        external_robot_id=frame["robot"]["id"],
                        robot_id=robot.id if robot else None,
                        state="connecting",
                        opened_at=now,
                        hello=frame,
                        config=None,
                        lost_samples=0,
                        diagnostics={},
                    )
                )
                session.flush()
            return
        if acquisition is None:
            raise ValueError("Session must be persisted before its messages")
        acquisition.lost_samples = max(acquisition.lost_samples, item["lost"])
        if kind == "disconnect":
            self._close(session, acquisition, now, frame["reason"])
            return
        run = None
        if item.get("run_id"):
            run = session.scalar(
                select(RunModel).where(
                    RunModel.external_session_id == sid, RunModel.external_run_id == item["run_id"]
                )
            )
        if kind == "config":
            acquisition.config = frame
            acquisition.state = "ready"
            if run:
                changes = run.context_snapshot.get("config_changes", [])
                run.context_snapshot = {**run.context_snapshot, "config_changes": [*changes, frame]}
        elif kind == "telemetry" and self.settings.sim_store_telemetry:
            session.execute(
                insert(ExternalTelemetryModel)
                .values(
                    session_id=sid,
                    seq=frame["seq"],
                    run_id=run.id if run else None,
                    t_ms=frame["t_ms"],
                    received_at=now,
                    payload=frame,
                )
                .on_conflict_do_nothing()
            )
        elif kind == "event":
            event = frame["event"]
            if event == "run_started" and run is None:
                robot, version, setup, profile = self.context(
                    session, item.get("setup_id"), item.get("robot_id")
                )
                acquisition.robot_id = robot.id
                config = acquisition.config
                selected_setup_id = setup.id
                effective = {**config["params"], "base_speed": config["base_speed"]}
                if setup.parameters != effective:
                    setup = SetupModel(
                        version_id=version.id,
                        controller_id=setup.controller_id,
                        name="External effective configuration",
                        parameters=effective,
                        controller_snapshot=setup.controller_snapshot,
                    )
                    session.add(setup)
                    session.flush()
                run = RunModel(
                    robot_id=robot.id,
                    version_id=version.id,
                    setup_id=setup.id,
                    profile_id=profile.id,
                    date=now,
                    source=acquisition.source,
                    mode=None,
                    line=None,
                    battery_compensation=None,
                    turbine_power_pct=None,
                    external_session_id=sid,
                    external_run_id=frame["run_id"],
                    closure_status="active",
                    context_snapshot={
                        "external": True,
                        "controller": setup.controller_snapshot,
                        "selected_setup_id": selected_setup_id,
                        "parameters": {**config["params"], "base_speed": config["base_speed"]},
                        "profile": as_dict(profile),
                        "hello": acquisition.hello,
                        "initial_config": config,
                        "config_changes": [],
                        "started_t_ms": frame["t_ms"],
                    },
                )
                session.add(run)
                session.flush()
            elif event == "lap" and run:
                exists = session.scalar(
                    select(LapModel.id).where(
                        LapModel.run_id == run.id, LapModel.number == frame["lap"]
                    )
                )
                if exists is None:
                    session.add(
                        LapModel(
                            run_id=run.id,
                            number=frame["lap"],
                            time_s=frame["lap_ms"] / 1000,
                            duration_s=frame["lap_ms"] / 1000,
                            internal_time_ms=frame["lap_ms"],
                            accumulated_error=None,
                            lost_lines=None,
                            battery_v=None,
                            finished=True,
                            time_source="telemetry",
                            reason="",
                        )
                    )
            elif event == "run_finished" and run and run.closed_at is None:
                run.closed_at = now
                run.closure_status = "finished"
                run.context_snapshot = {
                    **run.context_snapshot,
                    "summary": frame["summary"],
                    "finished_t_ms": frame["t_ms"],
                    "lost_samples": item["lost"],
                }
        elif kind == "diagnostic":
            acquisition.diagnostics = {**acquisition.diagnostics, frame["code"]: frame["detail"]}
        session.flush()
