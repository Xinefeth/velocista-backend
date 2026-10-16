"""Reglas de dominio de las vueltas. PLANTILLA DE FORMATO (sin implementar)."""

import pytest


@pytest.mark.skip(reason="plantilla de formato")
class TestCloseLap:
    """Reglas al cerrar una vuelta dentro de una corrida."""

    def test_appends_lap_when_number_is_new(self) -> None:
        # given: una corrida sin la vuelta N
        # when: se cierra la vuelta N
        # then: queda registrada y marcada como finished
        ...

    def test_rejects_lap_when_number_already_exists(self) -> None:
        # given: una corrida que ya tiene la vuelta N
        # when: se cierra otra vuelta N
        # then: ConflictError
        ...

    def test_rejects_negative_accumulated_error(self) -> None:
        # given: datos de vuelta con accumulated_error < 0
        # when: se construye la vuelta
        # then: ValidationError
        ...
