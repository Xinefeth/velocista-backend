"""Caso de uso CloseLap. PLANTILLA DE FORMATO (sin implementar).

Usa el doble `runs_repo` (InMemoryRunRepository) de conftest.py.
"""

import pytest


@pytest.mark.skip(reason="plantilla de formato")
class TestCloseLap:
    def test_closes_lap_when_run_exists(self, runs_repo) -> None:
        # given: una corrida guardada en el repo
        # when: se ejecuta CloseLap con datos válidos
        # then: el repo guarda la corrida con la vuelta cerrada
        ...

    def test_raises_not_found_when_run_missing(self, runs_repo) -> None:
        # given: repo vacío
        # when: se ejecuta CloseLap con run_id inexistente
        # then: NotFound
        ...
