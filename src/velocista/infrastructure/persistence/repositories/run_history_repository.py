"""Historial SQL y generacion de datos simulados, marcados como tales."""

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from velocista.domain.optimization.validation import validate_parameters
from velocista.domain.runs.scoring import best_lap, calculate_j
from velocista.domain.shared.errors import Conflict, NotFound
from velocista.infrastructure.persistence.models.builder import RobotModel
from velocista.infrastructure.persistence.models.config import RobotConfigModel
from velocista.infrastructure.persistence.models.optimization import ControllerModel, SetupModel
from velocista.infrastructure.persistence.models.rules import ProfileModel
from velocista.infrastructure.persistence.models.runs import (
    LapModel,
    LapSectorModel,
    LapSegmentModel,
    RunModel,
)
from velocista.infrastructure.persistence.repositories.rules_repository import as_dict


class SqlAlchemyRunHistoryRepository:
    def __init__(self, session):
        self.session = session

    def _laps(self, run_id):
        laps = self.session.scalars(
            select(LapModel).where(LapModel.run_id == run_id).order_by(LapModel.number)
        ).all()
        ids = [lap.id for lap in laps]
        sectors = {key: [] for key in ids}
        segments = {key: [] for key in ids}
        if ids:
            for row in self.session.scalars(
                select(LapSectorModel)
                .where(LapSectorModel.lap_id.in_(ids))
                .order_by(LapSectorModel.number)
            ):
                sectors[row.lap_id].append(row.time_s)
            for row in self.session.scalars(
                select(LapSegmentModel)
                .where(LapSegmentModel.lap_id.in_(ids))
                .order_by(LapSegmentModel.number)
            ):
                segments[row.lap_id].append(
                    {
                        key: value
                        for key, value in as_dict(row).items()
                        if key not in {"lap_id", "number"}
                    }
                )
        return [
            {**as_dict(lap), "sectors_s": sectors[lap.id], "segments": segments[lap.id]}
            for lap in laps
        ]

    def _summary(self, row):
        if row.closed_at is None:
            raise Conflict("run_active", "Run is still active")
        laps = self._laps(row.id)
        if not laps:
            raise Conflict("run_without_laps", "Closed run has no registered laps")
        lap = best_lap(laps)
        snapshot = row.context_snapshot
        return {
            **{
                key: value
                for key, value in as_dict(row).items()
                if key not in {"closed_at", "context_snapshot"}
            },
            "controller_id": snapshot["controller"]["id"],
            "parameters": snapshot["parameters"],
            **{
                key: lap[key]
                for key in [
                    "time_s",
                    "finished",
                    "accumulated_error",
                    "battery_v",
                    "sectors_s",
                    "time_source",
                ]
            },
            "j": calculate_j(lap["time_s"], lap["accumulated_error"], lap["finished"]),
        }

    def list_runs(
        self, limit=50, offset=0, robot_id=None, version_id=None, controller_id=None, source=None
    ):
        query = select(RunModel).where(RunModel.closed_at.is_not(None))
        for field, value in [
            (RunModel.robot_id, robot_id),
            (RunModel.version_id, version_id),
            (RunModel.source, source),
        ]:
            if value is not None:
                query = query.where(field == value)
        if controller_id is not None:
            query = query.where(
                RunModel.context_snapshot["controller"]["id"].astext == controller_id
            )
        total = self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.session.scalars(
            query.order_by(RunModel.date.desc(), RunModel.id.desc()).limit(limit).offset(offset)
        )
        return {
            "items": [self._summary(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_run(self, run_id):
        row = self.session.get(RunModel, run_id)
        return self._summary(row) if row else None

    def list_laps(self, run_id, limit, offset):
        laps = self._laps(run_id)
        return {
            "items": laps[offset : offset + limit],
            "total": len(laps),
            "limit": limit,
            "offset": offset,
        }

    def annotate(self, run_id, note):
        row = self.session.get(RunModel, run_id, with_for_update=True)
        row.note = note
        self.session.flush()
        result = self._summary(row)
        self.session.commit()
        return result

    def simulate(self, robot_id):
        robot = self.session.get(RobotModel, robot_id, with_for_update=True)
        if robot is None or robot.archived:
            raise NotFound("robot_not_found", "Robot does not exist")
        if robot.current_version_id is None:
            raise Conflict("no_current_version", "Robot needs a current version before simulation")
        if self.session.scalar(
            select(RunModel.id)
            .where(RunModel.robot_id == robot_id, RunModel.closed_at.is_(None))
            .limit(1)
        ):
            raise Conflict("robot_running", "Robot already has an active run")
        controller = self.session.get(ControllerModel, "pid") or self.session.scalar(
            select(ControllerModel).order_by(ControllerModel.id).limit(1)
        )
        profile = self.session.get(ProfileModel, "club") or self.session.scalar(
            select(ProfileModel).order_by(ProfileModel.id).limit(1)
        )
        if controller is None or profile is None:
            raise Conflict(
                "missing_reference_data", "Seed controllers and profiles before simulation"
            )
        parameters = controller.presets.get("Base", controller.presets.get("base"))
        if parameters is None:
            parameters = next(
                iter(controller.presets.values()),
                {p["key"]: p["min"] for p in controller.parameters},
            )
        parameters = validate_parameters(controller.parameters, parameters)
        setup = self.session.scalar(
            select(SetupModel).where(
                SetupModel.version_id == robot.current_version_id,
                SetupModel.name == "Simulation",
                SetupModel.archived.is_(False),
            )
        )
        if setup is None:
            setup = SetupModel(
                version_id=robot.current_version_id,
                controller_id=controller.id,
                name="Simulation",
                parameters=parameters,
                controller_snapshot=as_dict(controller),
            )
            self.session.add(setup)
            self.session.flush()
        now = datetime.now(UTC)
        config = self.session.get(RobotConfigModel, robot_id)
        run = RunModel(
            robot_id=robot_id,
            version_id=robot.current_version_id,
            setup_id=setup.id,
            profile_id=profile.id,
            date=now,
            closed_at=now,
            source="sim",
            mode=(config.mode if config else None) or "test",
            line=(config.line if config else None) or "black",
            battery_compensation=True,
            turbine_power_pct=0,
            note="Simulated run",
            context_snapshot={
                "generator": "console-v1",
                "firmware": robot.firmware,
                "manifest": None,
                "controller": setup.controller_snapshot,
                "parameters": setup.parameters,
                "profile": as_dict(profile),
            },
        )
        self.session.add(run)
        self.session.flush()
        rng = random.Random()
        total_time = 0.0
        for number in range(1, rng.randint(3, 8) + 1):
            duration = round(rng.uniform(8.5, 14), 3)
            error = round(rng.uniform(0.2, 2.5), 3)
            finished = rng.random() >= 0.08
            lap = LapModel(
                run_id=run.id,
                number=number,
                time_s=duration if finished else None,
                duration_s=duration,
                internal_time_ms=round(duration * 1000),
                accumulated_error=error,
                lost_lines=rng.randint(0, 2),
                battery_v=round(rng.uniform(7.2, 8.2), 2),
                finished=finished,
                time_source="telemetry",
                reason="" if finished else "Simulated line loss",
            )
            self.session.add(lap)
            self.session.flush()
            first = round(duration * rng.uniform(0.28, 0.38), 6)
            second = round(duration * rng.uniform(0.28, 0.38), 6)
            for sector_number, value in enumerate(
                [first, second, round(duration - first - second, 6)], 1
            ):
                self.session.add(LapSectorModel(lap_id=lap.id, number=sector_number, time_s=value))
            for segment_number in range(1, 5):
                self.session.add(
                    LapSegmentModel(
                        lap_id=lap.id,
                        number=segment_number,
                        type="curve" if segment_number % 2 == 0 else "straight",
                        duration_s=duration / 4,
                        angle_degrees=45 if segment_number % 2 == 0 else 0,
                        accumulated_error=error / 4,
                    )
                )
            total_time += duration
        run.closed_at = now + timedelta(seconds=total_time)
        self.session.flush()
        result = self._summary(run)
        self.session.commit()
        return result
