"""Registro técnico: formato de logs y middleware que registra cada petición HTTP."""

import logging
import time

from fastapi import FastAPI, Request

log = logging.getLogger("velocista.http")


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def register_request_logging(app: FastAPI) -> None:
    @app.middleware("http")
    async def _log_request(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        if request.url.path.startswith("/api"):
            ms = (time.perf_counter() - start) * 1000
            log.info(
                "%s %s → %s (%.1f ms)",
                request.method,
                request.url.path,
                response.status_code,
                ms,
            )
        return response
