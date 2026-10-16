"""Contrato WS 2.0: envelope + traducción (ACL). PLANTILLA DE FORMATO."""

import pytest


@pytest.mark.skip(reason="plantilla de formato")
class TestTranslation:
    """La anti-corruption layer traduce español→inglés en la frontera."""

    def test_translates_known_message_type(self) -> None:
        # given: type "estado" del robot
        # when: translate_type
        # then: "status"
        ...

    def test_translates_enum_values_in_payload(self) -> None:
        # given: payload con modo="prueba", linea="negra"
        # when: translate_payload
        # then: mode="test", line="black"
        ...

    def test_keeps_channel_keys_untouched(self) -> None:
        # given: data.channels con claves del firmware (p.ej. battery_v, line_array)
        # when: translate_payload
        # then: las claves de channels se reenvían tal cual (vocabulario abierto)
        ...


@pytest.mark.skip(reason="plantilla de formato")
class TestEnvelope:
    def test_rejects_unknown_fields(self) -> None:
        # given: un envelope con un campo no declarado
        # when: se valida
        # then: error de validación (extra="forbid")
        ...
