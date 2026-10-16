"""Casos de uso del historial; persistencia y simulacion por puerto."""

from typing import Protocol

from velocista.domain.shared.errors import NotFound


class RunHistoryRepository(Protocol):
    def list_runs(self, **filters) -> dict: ...
    def get_run(self, run_id: int) -> dict | None: ...
    def list_laps(self, run_id: int, limit: int, offset: int) -> dict: ...
    def annotate(self, run_id: int, note: str) -> dict: ...
    def simulate(self, robot_id: str) -> dict: ...


class RunHistoryService:
    def __init__(self, repository: RunHistoryRepository):
        self.repository = repository

    def list_runs(self, **filters):
        return self.repository.list_runs(**filters)

    def get_run(self, run_id):
        run = self.repository.get_run(run_id)
        if run is None:
            raise NotFound("run_not_found", "Run does not exist")
        return run

    def list_laps(self, run_id, limit, offset):
        self.get_run(run_id)
        return self.repository.list_laps(run_id, limit, offset)

    def annotate(self, run_id, note):
        self.get_run(run_id)
        return self.repository.annotate(run_id, note)

    def simulate(self, robot_id):
        return self.repository.simulate(robot_id)
