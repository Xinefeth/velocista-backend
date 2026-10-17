"""Contract: WebSocket envelope, translation (anti-corruption layer) and catalog."""

import pytest
from pydantic import ValidationError

from velocista.interface.websocket.contract.catalog import CATALOG
from velocista.interface.websocket.contract.envelope import Envelope
from velocista.interface.websocket.contract.translation import (
    translate_payload,
    translate_sender,
    translate_type,
)


class TestEnvelope:
    def valid(self, **overrides):
        base = {
            "type": "status",
            "seq": 1,
            "ts": 10,
            "sender": "robot",
            "data": {},
            "received_ms": 5,
        }
        return {**base, **overrides}

    def test_envelope_when_valid_is_accepted(self):
        assert Envelope(**self.valid()).type == "status"

    @pytest.mark.parametrize(
        "override",
        [
            {"type": "Status"},
            {"type": "x"},
            {"seq": -1},
            {"seq": 2**32},
            {"ts": -1},
            {"received_ms": -1},
            {"extra": 1},
        ],
    )
    def test_envelope_when_invalid_is_rejected(self, override):
        with pytest.raises(ValidationError):
            Envelope(**self.valid(**override))


class TestTranslation:
    def test_legacy_spanish_keys_are_translated_to_english(self):
        translated = translate_payload({"estado": "listo", "modo": "prueba", "linea": "negra"})
        assert translated["state"] == "listo"
        assert translated["mode"] == "test" and translated["line"] == "black"

    def test_translation_roundtrip_restores_legacy_form(self):
        legacy = {"modo": "competencia", "linea": "blanca"}
        assert translate_payload(translate_payload(legacy), reverse=True) == legacy

    def test_firmware_channel_names_are_never_translated(self):
        data = {"canales": {"error_acumulado": 1.0, "bateria_v": 7.4}}
        assert translate_payload(data)["channels"] == {"error_acumulado": 1.0, "bateria_v": 7.4}

    def test_english_payload_passes_through_unchanged(self):
        payload = {"state": "ready", "mode": "test", "line": "black"}
        assert translate_payload(payload) == payload

    @pytest.mark.parametrize(
        "legacy,english",
        [
            ("manifiesto", "manifest"),
            ("senales", "signals"),
            ("vuelta", "lap"),
            ("cierre_vuelta", "lap_close"),
            ("corte", "crossing"),
            ("rearmar", "rearm"),
        ],
    )
    def test_message_types_are_translated(self, legacy, english):
        assert translate_type(legacy) == english

    def test_sender_velocista_becomes_robot(self):
        assert translate_sender("velocista") == "robot"
        assert translate_sender("cronometro") == "timer"


class TestCatalog:
    @pytest.mark.parametrize(
        "command", ["calibrate", "start", "stop", "setup", "mode", "line", "lap_close", "ack"]
    )
    def test_api_to_robot_catalog_declares_command(self, command):
        assert ("api->robot", command) in CATALOG

    @pytest.mark.parametrize("command", ["rearm", "ack"])
    def test_api_to_timer_catalog_declares_command(self, command):
        assert ("api->timer", command) in CATALOG

    def test_catalog_message_names_are_english_snake_case(self):
        assert all(name == name.lower() and " " not in name for _, name in CATALOG)
