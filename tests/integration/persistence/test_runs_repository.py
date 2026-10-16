"""Repositorio SQLAlchemy de corridas contra BD de prueba. PLANTILLA DE FORMATO."""

import pytest


@pytest.mark.skip(reason="plantilla de formato")
class TestSqlAlchemyRunRepository:
    def test_save_then_get_roundtrip(self) -> None:
        # given: una sesión contra una BD de prueba
        # when: se guarda una corrida y se vuelve a leer por id
        # then: la entidad recuperada equivale a la guardada
        ...

    def test_list_paginates_and_counts(self) -> None:
        # given: N corridas guardadas
        # when: list(limit, offset)
        # then: devuelve el tramo correcto y total == N
        ...
