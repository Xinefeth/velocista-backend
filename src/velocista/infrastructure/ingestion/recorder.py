"""Ingesta transaccional de corridas reales; nunca fabrica telemetria."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from velocista.infrastructure.persistence.db import SessionLocal
from velocista.infrastructure.persistence.models.builder import RobotModel
from velocista.infrastructure.persistence.models.optimization import ControllerModel, SetupModel
from velocista.infrastructure.persistence.models.rules import ProfileModel
from velocista.infrastructure.persistence.models.runs import LapModel, RunModel
from velocista.infrastructure.persistence.repositories.rules_repository import as_dict
from velocista.infrastructure.realtime.registry import hub


class RunRecorder:
    def __init__(self, session):
        self.session = session

    def _robot(self, robot_id):
        # El bloqueo serializa numero de vuelta, snapshots y cierre para un robot.
        return self.session.get(RobotModel, robot_id, with_for_update=True)

    def _run(self, robot_id, include_recent=False):
        query = select(RunModel).where(RunModel.robot_id == robot_id, RunModel.source == "robot")
        if include_recent:
            query = query.where(
                (RunModel.closed_at.is_(None))
                | (RunModel.closed_at >= datetime.now(UTC) - timedelta(seconds=30))
            )
        else:
            query = query.where(RunModel.closed_at.is_(None))
        return self.session.scalar(query.order_by(RunModel.id.desc()).limit(1))

    def status(self, robot_id, status, manifest):
        robot = self._robot(robot_id)
        if robot is None or robot.archived:
            return False
        run = self._run(robot_id)
        if status["state"] == "running":
            if run is not None:
                return True
            if robot.current_version_id is None or manifest is None:
                return False
            live = manifest.controller(status["controller"])
            controller = self.session.get(ControllerModel, status["controller"])
            profile = self.session.get(ProfileModel, "club") or self.session.scalar(
                select(ProfileModel).order_by(ProfileModel.id).limit(1)
            )
            if live is None or controller is None or profile is None:
                return False
            parameters = {parameter.name: parameter.value for parameter in live.parameters}
            setup = self.session.scalar(
                select(SetupModel)
                .where(
                    SetupModel.version_id == robot.current_version_id,
                    SetupModel.controller_id == controller.id,
                    SetupModel.parameters == parameters,
                    SetupModel.archived.is_(False),
                )
                .order_by(SetupModel.id.desc())
                .limit(1)
            )
            if setup is None:
                setup = SetupModel(
                    version_id=robot.current_version_id,
                    controller_id=controller.id,
                    name="Live controller",
                    parameters=parameters,
                    controller_snapshot=as_dict(controller),
                )
                self.session.add(setup)
                self.session.flush()
            now = datetime.now(UTC)
            run = RunModel(
                robot_id=robot_id,
                version_id=robot.current_version_id,
                setup_id=setup.id,
                profile_id=profile.id,
                date=now,
                closed_at=None,
                source="robot",
                mode=status["mode"],
                line=status["line"],
                battery_compensation=manifest.battery_compensation,
                turbine_power_pct=parameters.get("turbine_power_pct", 0),
                context_snapshot={
                    "firmware": manifest.firmware,
                    "manifest": manifest.model_dump(mode="json"),
                    "controller": setup.controller_snapshot,
                    "parameters": parameters,
                    "profile": as_dict(profile),
                    "timer_crossings": {},
                },
                note="",
            )
            self.session.add(run)
            self.session.flush()
            return True
        if run is not None and status["state"] in ("stopped", "ready", "error"):
            now = datetime.now(UTC)
            if not self.session.scalar(
                select(func.count()).select_from(LapModel).where(LapModel.run_id == run.id)
            ):
                duration = max(0.0, (now - run.date).total_seconds())
                battery = status.get("channels", {}).get(
                    "battery_v", status.get("channels", {}).get("bateria_v", 0)
                )
                self.session.add(
                    LapModel(
                        run_id=run.id,
                        number=1,
                        time_s=None,
                        duration_s=duration,
                        internal_time_ms=None,
                        accumulated_error=0,
                        lost_lines=0,
                        battery_v=float(battery) if isinstance(battery, (int, float)) else 0,
                        finished=False,
                        time_source="telemetry",
                        reason="Stopped before a complete lap summary",
                    )
                )
            run.closed_at = now
            self.session.flush()
            return True
        return False

    def lap(self, robot_id, payload):
        if self._robot(robot_id) is None:
            return False
        run = self._run(robot_id, include_recent=True)
        if run is None:
            return False
        number = payload["lap_id"]
        row = self.session.scalar(
            select(LapModel).where(LapModel.run_id == run.id, LapModel.number == number)
        )
        if row is not None and row.finished:
            return True
        internal_s = payload["internal_time_ms"] / 1000
        official = run.context_snapshot.get("timer_crossings", {}).get(str(number))
        values = dict(
            time_s=official if official is not None else internal_s,
            duration_s=internal_s,
            internal_time_ms=payload["internal_time_ms"],
            accumulated_error=payload["accumulated_error"],
            lost_lines=payload["lost_lines"],
            battery_v=payload["battery_v"],
            finished=True,
            time_source="finish" if official is not None else "telemetry",
            reason="",
        )
        if row is None:
            self.session.add(LapModel(run_id=run.id, number=number, **values))
        else:
            for name, value in values.items():
                setattr(row, name, value)
        self.session.flush()
        return True

    def crossing(self, robot_id, payload):
        if self._robot(robot_id) is None:
            return False
        run = self._run(robot_id, include_recent=True)
        if run is None or payload.get("lap_time_ms") is None:
            return False
        number = payload["crossing_number"] - 1
        if number < 1:
            return False
        official = payload["lap_time_ms"] / 1000
        crossings = dict(run.context_snapshot.get("timer_crossings", {}))
        # Primera medicion oficial aceptada es inmutable ante reenvios.
        if str(number) in crossings:
            return True
        crossings[str(number)] = official
        run.context_snapshot = {**run.context_snapshot, "timer_crossings": crossings}
        lap = self.session.scalar(
            select(LapModel).where(
                LapModel.run_id == run.id, LapModel.number == number, LapModel.finished.is_(True)
            )
        )
        if lap is not None:
            lap.time_s = official
            lap.time_source = "finish"
        self.session.flush()
        return True


def on_status(robot_id, status):
    connection = hub.connections.get("robot")
    manifest = connection.manifest if connection else None
    with SessionLocal.begin() as session:
        return RunRecorder(session).status(robot_id, status, manifest)


def on_lap(robot_id, lap):
    with SessionLocal.begin() as session:
        return RunRecorder(session).lap(robot_id, lap)


def on_crossing(robot_id, crossing):
    with SessionLocal.begin() as session:
        return RunRecorder(session).crossing(robot_id, crossing)


def on_sync(robot_id, sync):
    with SessionLocal.begin() as session:
        recorder = RunRecorder(session)
        for lap in sync["laps"]:
            recorder.lap(robot_id, lap)


def handle_message(device: str, type: str, data: dict):
    connection = hub.connections.get("robot")
    if connection is None or connection.manifest is None:
        return False
    robot_id = connection.manifest.id
    if device == "robot":
        if type == "status":
            return on_status(robot_id, data)
        if type == "lap":
            return on_lap(robot_id, data)
        if type == "sync":
            return on_sync(robot_id, data)
    elif device == "timer" and type == "crossing":
        return on_crossing(robot_id, data)
    return False
