"""EN-38: prepara los datos de cada caso FUN en un backend vivo y escribe el plan para Swagger.

Uso (backend corriendo sobre una base de pruebas vacía, nunca la de producción):
    python scripts/swagger_evidence/make_plan.py http://127.0.0.1:8010 plan.json
    node scripts/swagger_evidence/capture.cjs <carpeta-frontend> http://127.0.0.1:8010 plan.json \
        docs/evidencias/swagger-sprint2

Los casos y su preparación son los mismos de tests/functional/test_swagger_sprint2.py.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import httpx

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tests"), str(REPO / "src"), str(REPO / "tests" / "functional")]

import test_swagger_sprint2 as fun  # noqa: E402


def path_params(template: str, path: str) -> dict[str, str]:
    names = re.findall(r"{(\w+)}", template)
    match = re.fullmatch(re.sub(r"{\w+}", r"([^/]+)", template), path)
    return dict(zip(names, match.groups(), strict=True))


def main() -> None:
    base, out = sys.argv[1], sys.argv[2]
    spec = httpx.get(f"{base}/openapi.json").json()
    plan = []
    with httpx.Client(base_url=base, timeout=60) as client:
        for c in fun.CASES:
            url, body = c.request(client)
            text = None if body is None else json.dumps(body, ensure_ascii=False, indent=2)
            parts = urlsplit(url)
            op = spec["paths"][c.path][c.method.lower()]
            plan.append(
                {
                    "id": c.id,
                    "title": c.title,
                    "status": c.status,
                    "tag": op["tags"][0],
                    "operationId": op["operationId"],
                    "params": {
                        **path_params(c.path, parts.path),
                        **dict(parse_qsl(parts.query)),
                    },
                    "body": text,
                }
            )
    Path(out).write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(plan)} cases")


if __name__ == "__main__":
    main()
