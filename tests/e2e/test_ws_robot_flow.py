"""Flujo e2e robot→API→consola. PLANTILLA DE FORMATO.

Usa httpx/ASGI para levantar la app y un cliente WS de prueba.
"""

import pytest


@pytest.mark.skip(reason="plantilla de formato")
class TestRobotFlow:
    def test_manifest_required_before_telemetry(self) -> None:
        # given: robot recién conectado a /ws/robot
        # when: envía "estado" antes del manifiesto
        # then: la consola recibe un event "missing_manifest" y no se reenvía la telemetría
        ...

    def test_status_reaches_console_translated_to_english(self) -> None:
        # given: robot con manifiesto enviado
        # when: envía "estado" (español) con modo="prueba"
        # then: la consola recibe type="status", sender="robot", data.mode="test"
        ...
