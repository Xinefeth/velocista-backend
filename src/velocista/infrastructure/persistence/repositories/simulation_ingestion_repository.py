"""Persist completed runs sent by the separate simulation service."""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from velocista.domain.shared.errors import Conflict, NotFound
from velocista.infrastructure.persistence.models.builder import RobotModel, VersionModel
from velocista.infrastructure.persistence.models.optimization import SetupModel
from velocista.infrastructure.persistence.models.rules import ProfileModel
from velocista.infrastructure.persistence.models.runs import (
    LapModel,
    LapSectorModel,
    LapSegmentModel,
    RunModel,
)
from velocista.infrastructure.persistence.repositories.rules_repository import as_dict
from velocista.infrastructure.persistence.repositories.run_history_repository import (
    SqlAlchemyRunHistoryRepository,
)


class SimulationIngestionRepository:
    def __init__(self, session: Session):
        self.session = session
        self.history = SqlAlchemyRunHistoryRepository(session)

    def _existing(self, external_run_id: str) -> RunModel | None:
        return self.session.scalar(select(RunModel).where(RunModel.ingestion_id == external_run_id))

    @staticmethod
    def _fingerprint(payload) -> str:
        normalized = payload.model_dump(mode="json")
        encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _replay(self, existing: RunModel, fingerprint: str) -> tuple[dict, bool]:
        recorded = existing.context_snapshot.get("ingestion", {}).get("payload_sha256")
        if recorded != fingerprint:
            raise Conflict(
                "external_run_conflict",
                "The external run ID was already ingested with different data",
            )
        return self.history.get_run(existing.id), False

    def ingest(self, payload) -> tuple[dict, bool]:
        fingerprint = self._fingerprint(payload)
        existing = self._existing(payload.external_run_id)
        if existing is not None:
            return self._replay(existing, fingerprint)

        robot = self.session.get(RobotModel, payload.robot_id)
        if robot is None:
            raise NotFound("robot_not_found", "Robot does not exist")
        if robot.archived:
            raise Conflict("robot_archived", "Archived robots cannot receive runs")

        version = self.session.get(VersionModel, payload.version_id)
        if version is None or version.robot_id != robot.id:
            raise NotFound("version_not_found", "Version does not belong to the requested robot")
        setup = self.session.get(SetupModel, payload.setup_id)
        if setup is None or setup.version_id != version.id:
            raise NotFound("setup_not_found", "Setup does not belong to the requested version")
        profile = self.session.get(ProfileModel, payload.profile_id)
        if profile is None:
            raise NotFound("profile_not_found", "Profile does not exist")

        snapshot = {
            "source_service": "simulation",
            "external_run_id": payload.external_run_id,
            "ingestion": {"payload_sha256": fingerprint},
            "firmware": robot.firmware,
            "manifest": None,
            "controller": setup.controller_snapshot,
            "parameters": setup.parameters,
            "profile": as_dict(profile),
        }
        run = RunModel(
            robot_id=robot.id,
            version_id=version.id,
            setup_id=setup.id,
            profile_id=profile.id,
            date=payload.started_at,
            closed_at=payload.finished_at,
            source="sim",
            mode=payload.mode,
            line=payload.line,
            battery_compensation=payload.battery_compensation,
            turbine_power_pct=payload.turbine_power_pct,
            context_snapshot=snapshot,
            note="",
            ingestion_id=payload.external_run_id,
        )
        self.session.add(run)
        try:
            self.session.flush()
            for lap_data in payload.laps:
                lap = LapModel(
                    run_id=run.id,
                    number=lap_data.number,
                    time_s=lap_data.time_s,
                    duration_s=lap_data.duration_s,
                    internal_time_ms=lap_data.internal_time_ms,
                    accumulated_error=lap_data.accumulated_error,
                    lost_lines=lap_data.lost_lines,
                    battery_v=lap_data.battery_v,
                    finished=lap_data.finished,
                    time_source=lap_data.time_source,
                    reason=lap_data.reason,
                )
                self.session.add(lap)
                self.session.flush()
                self.session.add_all(
                    LapSectorModel(lap_id=lap.id, number=index, time_s=value)
                    for index, value in enumerate(lap_data.sectors_s, start=1)
                )
                self.session.add_all(
                    LapSegmentModel(
                        lap_id=lap.id,
                        number=index,
                        type=segment.type,
                        duration_s=segment.duration_s,
                        angle_degrees=segment.angle_degrees,
                        accumulated_error=segment.accumulated_error,
                    )
                    for index, segment in enumerate(lap_data.segments, start=1)
                )
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self._existing(payload.external_run_id)
            if existing is not None:
                return self._replay(existing, fingerprint)
            raise
        return self.history.get_run(run.id), True
