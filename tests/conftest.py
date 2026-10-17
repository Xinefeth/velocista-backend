"""Fixtures compartidas. Esqueleto de formato.

Ejemplo de doble de prueba que implementa un port de `application` (no se mockea el ORM).
"""

import pytest

from velocista.application.runs.ports import RunRepository
from velocista.domain.runs.entities import Run
from velocista.infrastructure.config.settings import settings


class InMemoryRunRepository(RunRepository):
    """Repositorio en memoria para tests de casos de uso."""

    def __init__(self) -> None:
        self._runs: dict[int, Run] = {}

    def get(self, run_id: int) -> Run | None:
        return self._runs.get(run_id)

    def list(self, *, limit: int, offset: int) -> tuple[list[Run], int]:
        items = list(self._runs.values())
        return items[offset : offset + limit], len(items)

    def save(self, run: Run) -> Run:
        assert run.id is not None
        self._runs[run.id] = run
        return run


@pytest.fixture
def runs_repo() -> InMemoryRunRepository:
    return InMemoryRunRepository()


@pytest.fixture(autouse=True)
def backend_without_external_simulator(monkeypatch):
    """Existing API tests use simulated runs and commands without the external service."""
    monkeypatch.setattr(settings, "sim_enabled", False)
