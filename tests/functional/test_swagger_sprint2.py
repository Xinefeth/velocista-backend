"""EN-38: functional tests of the Sprint 2 endpoints, one case per row of docs/PRUEBAS_SWAGGER.md.

Each case is what a tester does in Swagger (`/docs` → Try it out → Execute): a request, the
expected status and the key fields of the response. Cases continue the Sprint 1 numbering
(FUN-01 to FUN-16). Black box: only HTTP in and out, real PostgreSQL in an isolated schema.

With SWAGGER_EVIDENCE_DIR set, every case saves its request and response as `<FUN-id>.json`.
"""

from __future__ import annotations

import json
import os
import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from support.measurement_fixtures import RECT_10x6, still_fixes, walk_readings
from velocista.main import create_app

PHONE = "phone-fun"
RECT = [{"x": p.x, "y": p.y} for p in RECT_10x6]
L_POINTS = [{"x": x, "y": y} for x, y in [(0, 0), (6, 0), (6, 2), (2, 2), (2, 8), (0, 8)]]


# ------------------------------------------------------------------------------ helpers


def gyro_samples(bias=0.4, moving=False):
    rng = random.Random(7)
    if moving:
        return [{"t_ms": i * 20, "gyro_z_dps": 30.0 * (-1) ** i} for i in range(250)]
    return [{"t_ms": i * 20, "gyro_z_dps": bias + rng.gauss(0, 0.1)} for i in range(250)]


def reading_json(r):
    data = {"seq": r.seq, "t_ms": r.t_ms, "kind": r.kind}
    if r.gyro_z_dps is not None:
        data["gyro_z_dps"] = r.gyro_z_dps
    if r.accel is not None:
        data["accel"] = list(r.accel)
    return data


def calibrate(client, device=PHONE, bias=0.4, steps=(29, 28, 29)):
    client.post(f"/api/calibrations/{device}/gyro", json={"samples": gyro_samples(bias)})
    trials = [{"distance_m": 20, "step_count": n} for n in steps]
    client.post(f"/api/calibrations/{device}/step", json={"trials": trials})


def start(client, device=PHONE):
    body = {
        "method": "steps",
        "place_name": "Aula 204",
        "device_id": device,
        "reference": {"points": RECT},
    }
    return client.post("/api/measurements", json=body).json()


def walked(client, seed=1, device=PHONE):
    """A started measurement with all the readings of one walk around the classroom."""
    m = start(client, device)
    readings = [reading_json(r) for r in walk_readings(gyro_bias_dps=0.4, seed=seed)]
    for i in range(0, len(readings), 500):
        client.post(
            f"/api/measurements/{m['id']}/readings", json={"readings": readings[i : i + 500]}
        )
    return m


def finished(client, seed=1, device=PHONE):
    m = walked(client, seed, device)
    return client.post(f"/api/measurements/{m['id']}/finish").json()


def fixes(x, seed, sigma=3.0):
    return [
        {"t_ms": f.t_ms, "lat": f.lat, "lon": f.lon, "accuracy_m": f.accuracy_m}
        for f in still_fixes(x, 0, n=10, sigma=sigma, seed=seed)
    ]


def gps_trial_body(**overrides):
    return {
        "device_id": PHONE,
        "place_name": "Cancha",
        "environment": "open",
        "real_distance_m": 50,
        "start_fixes": fixes(0, 1),
        "end_fixes": fixes(50, 2),
        **overrides,
    }


def gps_trial(client):
    return client.post("/api/gps-trials", json=gps_trial_body()).json()


# ------------------------------------------------------------------------------ cases


@dataclass(frozen=True)
class Case:
    id: str
    title: str
    method: str
    path: str  # OpenAPI path template, as Swagger shows it
    status: int
    request: Callable  # (client) -> (url, json body or None)
    check: Callable | None = None  # (response json) -> None


def _no_setup(url, body=None):
    return lambda client: (url, body)


CASES: list[Case] = []


def case(id, title, method, path, status, check=None):
    def register(request):
        CASES.append(Case(id, title, method, path, status, request, check))
        return request

    return register


# --- calibración (EN-35)
case(
    "FUN-17",
    "Estado de calibración de un celular nuevo",
    "GET",
    "/api/calibrations/{device_id}",
    200,
    lambda b: b["ready"] == {"steps": False, "car": False, "gps": True},
)(_no_setup("/api/calibrations/new-phone"))

case(
    "FUN-18",
    "Calibrar el giroscopio con el celular quieto 5 s",
    "POST",
    "/api/calibrations/{device_id}/gyro",
    201,
    lambda b: b["kind"] == "gyro_bias" and abs(b["params"]["bias_dps"] - 0.4) < 0.05,
)(_no_setup(f"/api/calibrations/{PHONE}/gyro", {"samples": gyro_samples()}))

case(
    "FUN-19",
    "Calibrar el giroscopio con el celular en movimiento (inválido)",
    "POST",
    "/api/calibrations/{device_id}/gyro",
    422,
    lambda b: b["detail"]["reason"] == "calibration_phone_moved",
)(_no_setup(f"/api/calibrations/{PHONE}/gyro", {"samples": gyro_samples(moving=True)}))

case(
    "FUN-20",
    "Calibrar el largo del paso caminando 20 m tres veces",
    "POST",
    "/api/calibrations/{device_id}/step",
    201,
    lambda b: abs(b["params"]["step_length_m"] - 0.70) < 0.01,
)(
    _no_setup(
        f"/api/calibrations/{PHONE}/step",
        {"trials": [{"distance_m": 20, "step_count": n} for n in (29, 28, 29)]},
    )
)

case(
    "FUN-21",
    "Calibrar el paso con una distancia negativa (inválido)",
    "POST",
    "/api/calibrations/{device_id}/step",
    422,
)(_no_setup(f"/api/calibrations/{PHONE}/step", {"trials": [{"distance_m": -5, "step_count": 8}]}))

case(
    "FUN-22",
    "Calibrar la velocidad del carro (v = k·PWM + c)",
    "POST",
    "/api/calibrations/{device_id}/car",
    201,
    lambda b: abs(b["params"]["k"] - 0.01) < 1e-6,
)(
    _no_setup(
        f"/api/calibrations/{PHONE}/car",
        {
            "trials": [
                {"pwm": p, "distance_m": (0.01 * p + 0.05) * 4, "seconds": 4} for p in (30, 60)
            ]
        },
    )
)


@case(
    "FUN-23",
    "Historial de calibraciones de un celular",
    "GET",
    "/api/calibrations/{device_id}/history",
    200,
    lambda b: {r["kind"] for r in b} == {"gyro_bias", "step_length"},
)
def _fun23(client):
    calibrate(client)
    return f"/api/calibrations/{PHONE}/history", None


# --- mediciones (EN-32, EN-33, EN-34)
case(
    "FUN-24",
    "Empezar una medición por pasos con plano de referencia",
    "POST",
    "/api/measurements",
    201,
    lambda b: b["status"] == "recording" and b["source"] == "phone",
)(
    _no_setup(
        "/api/measurements",
        {
            "method": "steps",
            "place_name": "Aula 204",
            "device_id": PHONE,
            "reference": {"points": RECT},
        },
    )
)

case(
    "FUN-25",
    "Empezar una medición con un método que no existe (inválido)",
    "POST",
    "/api/measurements",
    422,
)(_no_setup("/api/measurements", {"method": "laser", "place_name": "Aula", "device_id": PHONE}))

case(
    "FUN-26",
    "Empezar una medición con el carro sin calibrarlo",
    "POST",
    "/api/measurements",
    422,
    lambda b: b["detail"]["reason"] == "measurement_not_calibrated",
)(
    _no_setup(
        "/api/measurements",
        {"method": "car", "mount": "robot", "place_name": "Pista", "device_id": "car-phone"},
    )
)


@case(
    "FUN-27",
    "Enviar un lote de lecturas del celular",
    "POST",
    "/api/measurements/{measurement_id}/readings",
    200,
    lambda b: b["accepted"] == 3 and b["duplicates"] == 0,
)
def _fun27(client):
    m = start(client)
    readings = [
        {"seq": i, "t_ms": i * 20, "kind": "motion", "gyro_z_dps": 0.1, "accel": [0, 0, 9.8]}
        for i in range(3)
    ]
    return f"/api/measurements/{m['id']}/readings", {"readings": readings}


@case(
    "FUN-28",
    "Reenviar el mismo lote no duplica lecturas e informa las inválidas",
    "POST",
    "/api/measurements/{measurement_id}/readings",
    200,
    lambda b: b["accepted"] == 0 and b["duplicates"] == 2 and sum(b["discarded"].values()) == 1,
)
def _fun28(client):
    m = start(client)
    readings = [
        {"seq": i, "t_ms": i * 20, "kind": "motion", "gyro_z_dps": 0.1, "accel": [0, 0, 9.8]}
        for i in range(2)
    ]
    client.post(f"/api/measurements/{m['id']}/readings", json={"readings": readings})
    bad = {"seq": 9, "t_ms": 999, "kind": "motion", "gyro_z_dps": 99999}
    return f"/api/measurements/{m['id']}/readings", {"readings": [*readings, bad]}


case(
    "FUN-29",
    "Enviar lecturas a una medición que no existe",
    "POST",
    "/api/measurements/{measurement_id}/readings",
    404,
    lambda b: b["detail"]["reason"] == "measurement_not_found",
)(
    _no_setup(
        "/api/measurements/999999/readings",
        {"readings": [{"seq": 1, "t_ms": 1, "kind": "corner"}]},
    )
)


@case(
    "FUN-30",
    "Terminar la medición: perímetro, área y error de cierre",
    "POST",
    "/api/measurements/{measurement_id}/finish",
    200,
    lambda b: (
        b["status"] == "finished"
        and b["result"]["quality"] == "green"
        and abs(b["result"]["perimeter_error_pct"]) < 3
    ),
)
def _fun30(client):
    calibrate(client)
    m = walked(client)
    return f"/api/measurements/{m['id']}/finish", None


@case(
    "FUN-31",
    "Enviar lecturas a una medición ya terminada",
    "POST",
    "/api/measurements/{measurement_id}/readings",
    409,
)
def _fun31(client):
    calibrate(client)
    m = finished(client)
    return f"/api/measurements/{m['id']}/readings", {
        "readings": [{"seq": 99999, "t_ms": 1, "kind": "corner"}]
    }


@case(
    "FUN-32",
    "Consultar una medición terminada",
    "GET",
    "/api/measurements/{measurement_id}",
    200,
    lambda b: b["result"]["area_m2"] > 0 and b["place_name"] == "Aula 204",
)
def _fun32(client):
    calibrate(client)
    m = finished(client)
    return f"/api/measurements/{m['id']}", None


case(
    "FUN-33",
    "Consultar una medición que no existe",
    "GET",
    "/api/measurements/{measurement_id}",
    404,
    lambda b: b["detail"]["reason"] == "measurement_not_found",
)(_no_setup("/api/measurements/999999"))


@case(
    "FUN-34",
    "Listar las mediciones de un celular",
    "GET",
    "/api/measurements",
    200,
    lambda b: b["total"] == 2 and all(m["device_id"] == PHONE for m in b["items"]),
)
def _fun34(client):
    start(client)
    start(client)
    start(client, device="other-phone")
    return f"/api/measurements?device_id={PHONE}&limit=10", None


@case(
    "FUN-35",
    "Ver las lecturas guardadas de una medición",
    "GET",
    "/api/measurements/{measurement_id}/readings",
    200,
    lambda b: len(b) > 100 and b[0]["seq"] == 0,
)
def _fun35(client):
    m = walked(client)
    return f"/api/measurements/{m['id']}/readings", None


@case(
    "FUN-36",
    "Borrar una medición equivocada",
    "DELETE",
    "/api/measurements/{measurement_id}",
    204,
)
def _fun36(client):
    m = walked(client)
    return f"/api/measurements/{m['id']}", None


case(
    "FUN-37",
    "Borrar una medición que no existe",
    "DELETE",
    "/api/measurements/{measurement_id}",
    404,
)(_no_setup("/api/measurements/999999"))

# --- error del GPS (SP-06)
case(
    "FUN-38",
    "Registrar una prueba de error del GPS frente a la cinta",
    "POST",
    "/api/gps-trials",
    201,
    lambda b: (
        set(b["result"]["methods"]) == {"single", "mean", "filtered"}
        and b["result"]["methods"]["mean"]["error_m"] < b["result"]["methods"]["single"]["error_m"]
    ),
)(_no_setup("/api/gps-trials", gps_trial_body()))

case(
    "FUN-39",
    "Registrar una prueba del GPS con solo dos lecturas (inválido)",
    "POST",
    "/api/gps-trials",
    422,
)(lambda client: ("/api/gps-trials", gps_trial_body(start_fixes=fixes(0, 1)[:2])))


@case(
    "FUN-40",
    "Resumen del error del GPS y lado mínimo del terreno",
    "GET",
    "/api/gps-trials/summary",
    200,
    lambda b: b["trials"] == 1 and b["min_side_m"] > 0,
)
def _fun40(client):
    gps_trial(client)
    return f"/api/gps-trials/summary?device_id={PHONE}", None


@case(
    "FUN-41",
    "Cambiar el nombre de una prueba del GPS",
    "PATCH",
    "/api/gps-trials/{trial_id}",
    200,
    lambda b: b["place_name"] == "Cancha sintética",
)
def _fun41(client):
    trial = gps_trial(client)
    return f"/api/gps-trials/{trial['id']}", {"place_name": "Cancha sintética"}


@case(
    "FUN-42",
    "Borrar una prueba del GPS equivocada",
    "DELETE",
    "/api/gps-trials/{trial_id}",
    204,
)
def _fun42(client):
    trial = gps_trial(client)
    return f"/api/gps-trials/{trial['id']}", None


case(
    "FUN-43",
    "Borrar una prueba del GPS que no existe",
    "DELETE",
    "/api/gps-trials/{trial_id}",
    404,
    lambda b: b["detail"]["reason"] == "gps_trial_not_found",
)(_no_setup("/api/gps-trials/999999"))


# --- modelo de precisión (SP-07)
def _repeated(client, n=3):
    calibrate(client, bias=0.0, steps=(26, 26, 26))  # paso y giroscopio mal calibrados
    return [finished(client, seed=s)["id"] for s in range(n)]


@case(
    "FUN-44",
    "Correr el modelo de precisión con mediciones repetidas",
    "POST",
    "/api/precision-model/runs",
    201,
    lambda b: b["result"]["final_cost"] < b["result"]["baseline_cost"],
)
def _fun44(client):
    return "/api/precision-model/runs", {"measurement_ids": _repeated(client), "max_attempts": 30}


case(
    "FUN-45",
    "Correr el modelo con mediciones que no existen",
    "POST",
    "/api/precision-model/runs",
    404,
)(_no_setup("/api/precision-model/runs", {"measurement_ids": [999998, 999999]}))


@case(
    "FUN-46",
    "Listar las corridas del modelo",
    "GET",
    "/api/precision-model/runs",
    200,
    lambda b: len(b) == 1 and len(b[0]["result"]["attempts"]) == 10,
)
def _fun46(client):
    client.post(
        "/api/precision-model/runs",
        json={"measurement_ids": _repeated(client, 2), "max_attempts": 10},
    )
    return "/api/precision-model/runs", None


@case(
    "FUN-47",
    "Evaluar el modelo frente al algoritmo solo (línea base)",
    "POST",
    "/api/precision-model/evaluations",
    200,
    lambda b: (
        b["model"]["mean_closure_error_pct"] < b["baseline"]["mean_closure_error_pct"]
        and len(b["curve"]) == 31
        and b["verdict"] in {"improves_green", "improves_not_green"}
    ),
)
def _fun47(client):
    return "/api/precision-model/evaluations", {
        "measurement_ids": _repeated(client),
        "max_attempts": 30,
    }


case(
    "FUN-48",
    "Evaluar el modelo con una sola medición (inválido)",
    "POST",
    "/api/precision-model/evaluations",
    422,
)(_no_setup("/api/precision-model/evaluations", {"measurement_ids": [1]}))

# --- contorno por lados y ángulos (EN-42)
case(
    "FUN-49",
    "Cerrar una figura en L con un ángulo y dos lados que faltan",
    "POST",
    "/api/polygons/solve",
    200,
    lambda b: abs(b["area_m2"] - 24) < 1e-6 and abs(b["angles_deg"][3] - 270) < 1e-6,
)(
    _no_setup(
        "/api/polygons/solve",
        {"sides_m": [6, 2, 4, None, None, 8], "angles_deg": [90, 90, 90, None, 90, 90]},
    )
)

case(
    "FUN-50",
    "Cerrar una figura con datos insuficientes",
    "POST",
    "/api/polygons/solve",
    422,
    lambda b: b["detail"]["reason"] == "polygon_underdetermined",
)(
    _no_setup(
        "/api/polygons/solve", {"sides_m": [10, None, None, None], "angles_deg": [90, 90, 90, 90]}
    )
)

case(
    "FUN-51",
    "Área y ángulos de una figura en L marcada por puntos",
    "POST",
    "/api/polygons/from-points",
    200,
    lambda b: abs(b["area_m2"] - 24) < 1e-6 and b["concave"] and b["warnings"] == [],
)(_no_setup("/api/polygons/from-points", {"points": L_POINTS}))

case(
    "FUN-52",
    "Puntos cuyos lados se cruzan: avisa",
    "POST",
    "/api/polygons/from-points",
    200,
    lambda b: b["warnings"] == ["self_crossing"],
)(
    _no_setup(
        "/api/polygons/from-points",
        {"points": [{"x": x, "y": y} for x, y in [(0, 0), (4, 4), (4, 0), (0, 4)]]},
    )
)

# --- perfiles de reglamento (HU-9)
case(
    "FUN-53",
    "Listar los perfiles de reglamento",
    "GET",
    "/api/profiles",
    200,
    lambda b: any(p["id"] == "club" for p in b),
)(_no_setup("/api/profiles"))

case(
    "FUN-54",
    "Consultar un perfil de reglamento que no existe",
    "GET",
    "/api/profiles/{profile_id}",
    404,
)(_no_setup("/api/profiles/no-such-profile"))


# ------------------------------------------------------------------------------ tests


EVIDENCE_LIST_MAX = 5  # long lists (readings, samples, attempts) are cut in the evidence


def _trim(value):
    if isinstance(value, list):
        items = [_trim(v) for v in value[:EVIDENCE_LIST_MAX]]
        if len(value) > EVIDENCE_LIST_MAX:
            items.append(f"... {len(value) - EVIDENCE_LIST_MAX} more ({len(value)} in total)")
        return items
    if isinstance(value, dict):
        return {k: _trim(v) for k, v in value.items()}
    return value


def _save_evidence(c: Case, url: str, body, response) -> None:
    folder = os.environ.get("SWAGGER_EVIDENCE_DIR")
    if not folder:
        return
    try:
        out = response.json()
    except ValueError:
        out = None
    record = {
        "id": c.id,
        "title": c.title,
        "request": {"method": c.method, "url": url, "body": _trim(body)},
        "expected_status": c.status,
        "response": {"status": response.status_code, "body": _trim(out)},
    }
    path = Path(folder) / f"{c.id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.mark.parametrize("c", CASES, ids=[c.id for c in CASES])
def test_functional_case(client, c: Case):
    url, body = c.request(client)
    response = client.request(c.method, url, json=body)
    _save_evidence(c, url, body, response)
    assert response.status_code == c.status, response.text
    if c.check:
        assert c.check(response.json()), response.text


@pytest.fixture(scope="module")
def spec():
    return create_app().openapi()


@pytest.mark.parametrize("c", CASES, ids=[c.id for c in CASES])
def test_case_is_documented_in_swagger(spec, c: Case):
    operation = spec["paths"][c.path][c.method.lower()]
    assert str(c.status) in operation["responses"], f"{c.id}: Swagger does not list {c.status}"
    assert operation["summary"] and operation["description"]


def test_case_ids_are_unique_and_consecutive():
    numbers = [int(c.id.split("-")[1]) for c in CASES]
    assert numbers == list(range(17, 17 + len(CASES)))
