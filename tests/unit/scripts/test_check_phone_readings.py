"""EN-32 (7.5): the support script tells real phone readings from fake or broken ones."""

import importlib.util
import json
import math
import random
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_phone_readings.py"
spec = importlib.util.spec_from_file_location("check_phone_readings", SCRIPT)
chk = importlib.util.module_from_spec(spec)
sys.modules["check_phone_readings"] = chk  # dataclasses needs the module registered
spec.loader.exec_module(chk)

T0 = 1_730_592_000_000


def motion(seconds, hz=50, gyro=lambda t: 0.0, accel=lambda t: (0.1, 0.2, 9.8), seed=1, start=0):
    """Motion readings with a little timing jitter, like a browser."""
    rng = random.Random(seed)
    out, t = [], 0.0
    seq = start
    while t <= seconds:
        t_ms = T0 + int(t * 1000 + rng.uniform(-2, 2))
        out.append(
            {
                "seq": seq,
                "t_ms": t_ms,
                "kind": "motion",
                "gyro_z_dps": gyro(t),
                "accel": list(accel(t)),
                "step": False,
                "pwm": None,
            }
        )
        seq += 1
        t += 1 / hz
    return out


def rest_readings(seconds=10, seed=1):
    rng = random.Random(seed)
    return motion(
        seconds,
        gyro=lambda t: rng.gauss(0.3, 0.2),
        accel=lambda t: (rng.gauss(0.1, 0.05), rng.gauss(0.2, 0.05), rng.gauss(9.78, 0.05)),
        seed=seed,
    )


def levels(findings):
    return {f.name: f.level for f in findings}


# ------------------------------------------------------------------ reposo


def test_rest_phone_passes_the_rest_step():
    result = chk.analyse(rest_readings(), "rest", user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS)")
    assert result["verdict"] == "APTO"
    step = levels(result["sections"]["paso"])
    assert step["Módulo de aceleración"] == "OK"
    assert step["Giro en reposo"] == "OK"
    assert 9.7 < result["summary"]["accel_mean_ms2"] < 9.9


def test_moving_phone_fails_the_rest_step():
    readings = motion(10, accel=lambda t: (3.0 * math.sin(20 * t), 0.0, 9.8 + 5 * math.sin(7 * t)))
    result = chk.analyse(readings, "rest")
    assert "AVISO" in levels(result["sections"]["paso"]).values()


def test_rest_with_wrong_gravity_fails():
    readings = motion(10, accel=lambda t: (0.0, 0.0, 4.0 + 0.01 * math.sin(t * 9)))
    step = levels(chk.analyse(readings, "rest")["sections"]["paso"])
    assert step["Módulo de aceleración"] == "FALLA"


# ------------------------------------------------------------------ giro de 360°


def test_full_turn_integrates_to_360_degrees():
    readings = motion(10, gyro=lambda t: 36.0)  # 36 °/s durante 10 s
    result = chk.analyse(readings, "turn")
    assert result["summary"]["gyro_integral"]["total_deg"] == pytest.approx(360, rel=0.01)
    assert levels(result["sections"]["paso"])["Giro de 360°"] == "OK"


def test_turn_off_by_more_than_ten_percent_fails():
    readings = motion(10, gyro=lambda t: 30.0)  # 300°
    assert levels(chk.analyse(readings, "turn")["sections"]["paso"])["Giro de 360°"] == "FALLA"


def test_clockwise_turn_counts_by_magnitude():
    readings = motion(10, gyro=lambda t: -36.0)
    assert levels(chk.analyse(readings, "turn")["sections"]["paso"])["Giro de 360°"] == "OK"


def test_radians_per_second_are_detected():
    omega = math.radians(36.0)  # el navegador manda rad/s: 0,628 por segundo
    readings = motion(10, gyro=lambda t: omega)
    step = levels(chk.analyse(readings, "turn")["sections"]["paso"])
    assert step["Giro de 360°"] == "FALLA"
    assert step["Unidades del giro"] == "FALLA"


def test_bias_option_is_subtracted():
    readings = motion(10, gyro=lambda t: 36.0 + 1.0)
    assert chk.integrate_gyro(readings, 1.0)["total_deg"] == pytest.approx(360, rel=0.01)


def test_irregular_intervals_still_integrate_exactly():
    # 36 °/s con intervalos irregulares: la regla del trapecio usa el dt real
    rng = random.Random(3)
    readings, t = [], 0
    for seq in range(200):
        readings.append(
            {"seq": seq, "t_ms": T0 + t, "kind": "motion", "gyro_z_dps": 36.0, "accel": [0, 0, 9.8]}
        )
        t += rng.choice([10, 20, 30, 50])
    expected = 36.0 * (t - readings[-1]["t_ms"] + T0 + 0) / 1000  # hasta la última muestra
    expected = 36.0 * (readings[-1]["t_ms"] - T0) / 1000
    assert chk.integrate_gyro(readings)["total_deg"] == pytest.approx(expected, rel=1e-9)


# ------------------------------------------------------------------ huecos y orden


def test_seq_gaps_are_reported():
    readings = [r for r in motion(5) if r["seq"] not in (10, 11, 50)]
    seq = chk.seq_report(readings)
    assert seq["missing"] == 3
    assert seq["ranges"] == [(10, 11), (50, 50)]
    result = chk.analyse(readings, "continuity")
    assert levels(result["sections"]["integridad"])["Huecos de seq"] == "FALLA"
    assert result["verdict"] == "NO APTO"


def test_complete_run_of_60_seconds_passes_continuity():
    result = chk.analyse(motion(60), "continuity")
    step = levels(result["sections"]["paso"])
    assert step["Duración"] == "OK"
    assert step["seq sin huecos"] == "OK"
    assert step["t_ms creciente"] == "OK"
    assert result["summary"]["motion_rate"]["hz"] == pytest.approx(50, rel=0.02)


def test_short_run_fails_continuity():
    step = levels(chk.analyse(motion(20), "continuity")["sections"]["paso"])
    assert step["Duración"] == "FALLA"


def test_time_going_backwards_is_detected():
    readings = motion(5)
    readings[100]["t_ms"] -= 5000
    tim = chk.time_report(readings)
    assert tim["decreasing"] >= 1
    assert levels(chk.analyse(readings)["sections"]["integridad"])["Orden de t_ms"] == "FALLA"


def test_time_gap_over_two_seconds_is_a_warning():
    readings = motion(2) + motion(2, start=200)
    for r in readings[len(readings) // 2 :]:
        r["t_ms"] += 5000
    assert chk.time_report(readings)["gaps_over_limit"] == 1
    assert "Huecos de tiempo" in levels(chk.analyse(readings)["sections"]["integridad"])


def test_network_cut_without_loss_passes():
    step = levels(chk.analyse(motion(30), "cut")["sections"]["paso"])
    assert set(step.values()) == {"OK"}


def test_repeated_seq_is_detected():
    readings = motion(2)
    readings.append(dict(readings[5]))
    assert chk.seq_report(readings)["repeated"] == 1
    assert levels(chk.analyse(readings, "cut")["sections"]["paso"])["Sin duplicados"] == "FALLA"


# ------------------------------------------------------------------ dato falso


def test_all_null_motion_is_no_motion_data():
    readings = [
        {"seq": i, "t_ms": T0 + i * 20, "kind": "motion", "gyro_z_dps": None, "accel": None}
        for i in range(100)
    ]
    result = chk.analyse(readings)
    assert levels(result["sections"]["datos_falsos"])["Sin datos de movimiento"] == "FALLA"
    assert result["verdict"] == "NO APTO"


def test_all_zero_motion_fails():
    result = chk.analyse(motion(5, gyro=lambda t: 0.0, accel=lambda t: (0.0, 0.0, 0.0)))
    assert levels(result["sections"]["datos_falsos"])["Todo ceros"] == "FALLA"


def test_constant_values_fail():
    result = chk.analyse(motion(5, gyro=lambda t: 1.5, accel=lambda t: (0.0, 0.0, 9.81)))
    found = levels(result["sections"]["datos_falsos"])
    assert found["Aceleración constante"] == "FALLA"
    assert found["Giro constante"] == "FALLA"


def test_perfect_seq_with_frozen_clock_fails():
    readings = [
        {
            "seq": i,
            "t_ms": T0 + (i % 3),
            "kind": "motion",
            "gyro_z_dps": 0.1 * i % 1,
            "accel": [0.1, 0.2, 9.8 + i % 5],
        }
        for i in range(200)
    ]
    assert (
        levels(chk.analyse(readings)["sections"]["datos_falsos"])["Tiempo sin variación"] == "FALLA"
    )


def test_perfectly_regular_clock_is_a_warning():
    readings = [
        {
            "seq": i,
            "t_ms": T0 + i * 20,
            "kind": "motion",
            "gyro_z_dps": math.sin(i / 7),
            "accel": [0.1, math.cos(i / 9), 9.8],
        }
        for i in range(200)
    ]
    assert (
        levels(chk.analyse(readings)["sections"]["datos_falsos"])["Reloj demasiado perfecto"]
        == "AVISO"
    )


def test_acceleration_in_g_is_flagged():
    result = chk.analyse(motion(5, accel=lambda t: (0.0, 0.0, 1.0 + 0.01 * math.sin(t * 5))))
    assert "Unidades de la aceleración" in levels(result["sections"]["datos_falsos"])


def test_desktop_user_agent_fails_and_phone_passes():
    desktop = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"
    android = "Mozilla/5.0 (Linux; Android 14; Pixel 8) Chrome/130.0 Mobile Safari/537.36"
    assert chk.is_desktop_agent(desktop)
    assert not chk.is_desktop_agent(android)
    rest = rest_readings()
    assert (
        levels(chk.analyse(rest, user_agent=desktop)["sections"]["datos_falsos"])[
            "Agente de escritorio"
        ]
        == "FALLA"
    )
    assert (
        levels(chk.analyse(rest, user_agent=android)["sections"]["datos_falsos"])["Agente"] == "OK"
    )


def test_without_user_agent_it_is_only_info():
    assert levels(chk.analyse(rest_readings())["sections"]["datos_falsos"])["Agente"] == "INFO"


def test_empty_measurement_fails():
    assert chk.analyse([])["verdict"] == "NO APTO"


# ------------------------------------------------------------------ GPS y agitar


def gps_walk(meters=20, fixes=15, constant_accuracy=False, still=False):
    out = []
    rng = random.Random(5)
    for i in range(fixes):
        north = 0.0 if still else meters * i / (fixes - 1)
        out.append(
            {
                "seq": i,
                "t_ms": T0 + i * 1000,
                "kind": "gps",
                "lat": -8.1116 + north / 111_320 + (0 if still else rng.gauss(0, 1e-6)),
                "lon": -79.0287,
                "accuracy_m": 5.0 if constant_accuracy else 4.0 + rng.random() * 3,
            }
        )
    return out


def test_walk_of_20_meters_passes_the_gps_step():
    result = chk.analyse(gps_walk(), "gps")
    step = levels(result["sections"]["paso"])
    assert step["Variación de lat/lon"] == "OK"
    assert step["accuracy_m"] == "OK"
    assert 15 < result["summary"]["gps"]["extent_m"] < 25


def test_standing_still_fails_the_gps_step():
    step = levels(chk.analyse(gps_walk(still=True), "gps")["sections"]["paso"])
    assert step["Variación de lat/lon"] == "FALLA"


def test_constant_accuracy_is_flagged():
    result = chk.analyse(gps_walk(constant_accuracy=True), "gps")
    assert levels(result["sections"]["datos_falsos"])["Precisión constante"] == "AVISO"
    assert levels(result["sections"]["paso"])["accuracy_m"] == "AVISO"


def test_shake_is_well_above_gravity():
    shaking = motion(
        3, accel=lambda t: (9 * math.sin(30 * t), 8 * math.cos(25 * t), 9.8 + 7 * math.sin(40 * t))
    )
    assert levels(chk.analyse(shaking, "shake")["sections"]["paso"])["Agitar"] == "OK"
    assert levels(chk.analyse(rest_readings(3), "shake")["sections"]["paso"])["Agitar"] == "FALLA"


def test_window_selects_a_part_of_the_measurement():
    readings = rest_readings(10) + [
        dict(r, seq=r["seq"] + 1000, t_ms=r["t_ms"] + 10_000, gyro_z_dps=36.0) for r in motion(10)
    ]
    # los primeros 10 s son reposo; los siguientes giran 36 °/s
    rest = chk.analyse(readings, "rest", window=(0, 9))
    assert levels(rest["sections"]["paso"])["Giro en reposo"] == "OK"
    turn = chk.analyse(readings, "turn", window=(10.5, 21))
    assert levels(turn["sections"]["paso"])["Giro de 360°"] == "OK"


# ------------------------------------------------------------------ informe, red y archivos


def test_report_is_readable_and_never_contains_a_token():
    result = chk.analyse(rest_readings(), "rest")
    text = chk.render(
        result, {"id": 7, "method": "gps", "source": "phone", "mount": "hand", "status": "finished"}
    )
    assert "RESULTADO: APTO" in text
    assert "Medición 7" in text
    assert "Bearer" not in text
    json.loads(chk.to_json(result))  # el JSON es válido


def test_main_reads_a_local_file_and_sets_the_exit_code(tmp_path, capsys):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"readings": rest_readings()}), encoding="utf-8")
    assert chk.main(["--file", str(good), "--step", "rest"]) == 0
    assert "RESULTADO" in capsys.readouterr().out
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([r for r in motion(5) if r["seq"] % 10]), encoding="utf-8")
    assert chk.main(["--file", str(bad), "--json"]) == 1


def test_http_to_a_remote_host_is_refused_so_the_token_is_not_sent_in_clear():
    with pytest.raises(chk.ApiError):
        chk._check_base_url("http://mi-api.example.com", allow_insecure=False)
    assert chk._check_base_url("http://127.0.0.1:8000/", False) == "http://127.0.0.1:8000"
    assert (
        chk._check_base_url("https://mi-api.onrender.com", False) == "https://mi-api.onrender.com"
    )


def test_main_without_arguments_is_a_usage_error(capsys):
    assert chk.main([]) == 2
    assert "Error" in capsys.readouterr().err


def test_token_is_read_from_the_environment_and_never_printed(monkeypatch, capsys):
    secret = "tok-secreto-de-prueba-123"
    monkeypatch.setenv("VELOCISTA_TOKEN", secret)
    seen = {}

    def fake_request(method, url, token, body=None):
        seen[url] = token
        return {"id": 3, "source": "phone", "reading_count": 0} if url.endswith("/3") else []

    monkeypatch.setattr(chk, "api_request", fake_request)
    chk.main(["http://127.0.0.1:8000", "3"])
    captured = capsys.readouterr()
    assert set(seen.values()) == {secret}
    assert secret not in captured.out + captured.err


# ------------------------------------------------------------------ --device / --list / --latest


def measurement_row(mid, device, started, method="steps", status="finished", count=100):
    return {
        "id": mid,
        "device_id": device,
        "method": method,
        "status": status,
        "reading_count": count,
        "started_at": started,
        "place_name": "LUGAR-SECRETO",
    }


UUID_A = "cel-a8b62dcb-1111-4222-8333-444455556666"
UUID_B = "cel-0f0f0f0f-1111-4222-8333-444455556666"
ROWS = [  # más recientes primero, como responde la API
    measurement_row(9, UUID_B, "2026-11-04T12:00:00Z"),
    measurement_row(8, UUID_A, "2026-11-04T11:00:00Z", count=2500),
    measurement_row(7, UUID_B, "2026-11-04T10:00:00Z"),
    measurement_row(6, UUID_A, "2026-11-04T09:00:00Z", method="gps", status="recording"),
]


def test_device_code_is_normalized():
    assert chk.normalize_device_code("A8B62DCB") == "a8b62dcb"
    assert chk.normalize_device_code(" cel-a8b62dcb ") == "a8b62dcb"
    for bad in ("", "abc", "a8b6 2dcb", "a8b6/../"):
        with pytest.raises(chk.ApiError):
            chk.normalize_device_code(bad)


def test_measurements_of_a_device_are_filtered_by_prefix():
    found = chk.measurements_of_device(ROWS, "a8b62dcb")
    assert [m["id"] for m in found] == [8, 6]
    assert chk.latest_measurement(found)["id"] == 8


def test_longer_code_and_prefix_also_match():
    assert len(chk.measurements_of_device(ROWS, "cel-a8b62dcb-1111")) == 2


def test_ambiguous_code_is_not_guessed():
    rows = ROWS + [
        measurement_row(10, "cel-a8b62dcb-9999-4222-8333-444455556666", "2026-11-04T13:00:00Z")
    ]
    with pytest.raises(chk.ApiError, match="coincide con 2 celulares"):
        chk.measurements_of_device(rows, "a8b62dcb")
    # con un código más largo ya no es ambiguo
    assert [m["id"] for m in chk.measurements_of_device(rows, "a8b62dcb-9999")] == [10]


def test_unknown_device_gives_no_measurements():
    assert chk.measurements_of_device(ROWS, "deadbeef") == []


def test_list_is_short_and_never_shows_place_or_coordinates():
    text = chk.render_device_list(chk.measurements_of_device(ROWS, "a8b62dcb"))
    assert "LUGAR-SECRETO" not in text
    assert "2500" in text and "recording" in text and "2026-11-04T11:00:00Z" in text
    assert "LUGAR-SECRETO" not in chk.device_list_json(ROWS)


def fake_api(monkeypatch, readings=None):
    calls = []

    def fake_request(method, url, token, body=None):
        calls.append((url, token))
        if "/api/measurements?" in url:
            return {"items": ROWS, "total": len(ROWS), "limit": 200, "offset": 0}
        if url.endswith("/readings"):
            return readings if readings is not None else rest_readings()
        return next(dict(r) for r in ROWS if url.endswith(f"/{r['id']}"))

    monkeypatch.setattr(chk, "api_request", fake_request)
    return calls


def test_main_device_list(monkeypatch, capsys):
    fake_api(monkeypatch)
    assert chk.main(["http://127.0.0.1:8000", "--device", "a8b62dcb", "--list"]) == 0
    out = capsys.readouterr().out
    assert "2 mediciones" in out and "LUGAR-SECRETO" not in out


def test_main_device_latest_analyses_the_newest_measurement(monkeypatch, capsys):
    calls = fake_api(monkeypatch)
    code = chk.main(["http://127.0.0.1:8000", "--device", "a8b62dcb", "--latest", "--step", "rest"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Medición 8" in out and "LUGAR-SECRETO" not in out
    assert calls[-1][0].endswith("/api/measurements/8/readings")


def test_main_device_errors(monkeypatch, capsys):
    fake_api(monkeypatch)
    base = "http://127.0.0.1:8000"
    assert chk.main([base, "--device", "deadbeef", "--list"]) == 2  # sin mediciones
    assert chk.main([base, "--device", "a8b62dcb"]) == 2  # falta --list o --latest
    assert chk.main([base, "--list"]) == 2  # falta --device
    assert chk.main([base, "--device", "a8b62dcb", "--list", "--latest"]) == 2
    assert chk.main([base, "5", "--device", "a8b62dcb", "--latest"]) == 2  # id y --device
    assert chk.main(["--file", "x.json", "--device", "a8b62dcb", "--list"]) == 2
    assert "Error" in capsys.readouterr().err


def test_main_ambiguous_device_does_not_analyse(monkeypatch, capsys):
    rows = ROWS + [
        measurement_row(10, "cel-a8b62dcb-9999-4222-8333-444455556666", "2026-11-04T13:00:00Z")
    ]
    monkeypatch.setattr(
        chk, "api_request", lambda m, u, t, b=None: {"items": rows, "total": len(rows)}
    )
    assert chk.main(["http://127.0.0.1:8000", "--device", "a8b62dcb", "--latest"]) == 2
    assert "usa un código más largo" in capsys.readouterr().err


def test_device_options_keep_the_token_safe(monkeypatch, capsys):
    secret = "tok-secreto-de-prueba-456"
    monkeypatch.setenv("VELOCISTA_TOKEN", secret)
    calls = fake_api(monkeypatch)
    chk.main(["http://127.0.0.1:8000", "--device", "a8b62dcb", "--latest"])
    captured = capsys.readouterr()
    assert {token for _, token in calls} == {secret}
    assert secret not in captured.out + captured.err
    with pytest.raises(chk.ApiError):  # http fuera de localhost sigue prohibido
        chk._check_base_url("http://mi-api.example.com", False)


def test_listing_pages_through_every_measurement_with_a_real_http_server():
    """urllib de verdad contra un servidor local de prueba: URL, paginación y cabecera."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlsplit

    rows = [
        measurement_row(i, UUID_B, f"2026-11-04T{i % 24:02d}:00:00Z") for i in range(450, 0, -1)
    ]
    rows[-3] = measurement_row(
        3, UUID_A, "2026-11-04T01:00:00Z"
    )  # el de a8b62dcb está en la última página
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parts = urlsplit(self.path)
            q = parse_qs(parts.query)
            limit, offset = int(q["limit"][0]), int(q["offset"][0])
            seen.append((parts.path, offset, self.headers.get("Authorization")))
            body = json.dumps({"items": rows[offset : offset + limit], "total": len(rows)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        items = chk.list_all_measurements(base, "tok-de-prueba")
    finally:
        server.shutdown()
        server.server_close()
    assert len(items) == 450
    assert [offset for _, offset, _ in seen] == [0, 200, 400]
    assert {auth for _, _, auth in seen} == {"Bearer tok-de-prueba"}
    assert [m["id"] for m in chk.measurements_of_device(items, "a8b62dcb")] == [3]


# ----- mount de cada lectura (informativo)


def with_mount(readings, mount):
    return [dict(r, mount=mount) for r in readings]


@pytest.mark.parametrize("mount", ["hand", "robot"])
def test_report_shows_the_mount_of_the_readings(mount):
    result = chk.analyse(with_mount(rest_readings(), mount), "rest")
    assert result["summary"]["mounts"] == [mount]
    assert f"Montaje de las lecturas: {mount}" in chk.render(result)


def test_old_readings_without_mount_still_work():
    result = chk.analyse(rest_readings(), "rest")  # sin el campo, como antes de EN-32 criterio 2
    assert result["summary"]["mounts"] == []
    assert "no informado" in chk.render(result)
    assert result["verdict"] == "APTO"


def test_mount_is_only_informative_and_never_changes_the_findings():
    def findings(result):
        return {k: [(f.level, f.name) for f in v] for k, v in result["sections"].items()}

    plain = chk.analyse(rest_readings(), "rest")
    for mount in ("hand", "robot"):
        other = chk.analyse(with_mount(rest_readings(), mount), "rest")
        assert other["verdict"] == plain["verdict"]
        assert findings(other) == findings(plain)


def test_mixed_mounts_are_listed_without_failing():
    readings = (
        with_mount(rest_readings(3), "hand")[:50] + with_mount(rest_readings(3), "robot")[50:]
    )
    assert chk.analyse(readings)["summary"]["mounts"] == ["hand", "robot"]


def test_main_file_with_and_without_mount(tmp_path, capsys):
    new = tmp_path / "new.json"
    new.write_text(json.dumps(with_mount(rest_readings(), "robot")), encoding="utf-8")
    old = tmp_path / "old.json"
    old.write_text(json.dumps(rest_readings()), encoding="utf-8")
    assert chk.main(["--file", str(new), "--step", "rest"]) == 0
    assert "Montaje de las lecturas: robot" in capsys.readouterr().out
    assert chk.main(["--file", str(old), "--step", "rest"]) == 0
    assert "no informado" in capsys.readouterr().out
    assert chk.main(["--file", str(new), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["mounts"] == ["robot"]
