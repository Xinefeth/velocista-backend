"""Protect robot versions while a run is active in memory or persistence."""

from sqlalchemy import select

from velocista.infrastructure.realtime.registry import robot_running


class RealtimeRobotActivity:
    def __init__(self, session):
        self._session = session

    def is_running(self, robot_id):
        if robot_running(robot_id):
            return True
        from velocista.infrastructure.persistence.models.runs import RunModel

        return (
            self._session.scalar(
                select(RunModel.id)
                .where(RunModel.robot_id == robot_id, RunModel.closed_at.is_(None))
                .limit(1)
            )
            is not None
        )
