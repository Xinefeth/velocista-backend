"""Formato estándar de errores de la API y su registro en FastAPI.

Errores de negocio:     {"detail": {"reason": "...", "detail": "..."}}
Errores de validación:  formato de FastAPI (422)
No controlados:         500 sin detalles internos, registrados en el log

Mapea el TIPO de error de dominio a un código HTTP (el dominio no conoce HTTP).
"""

import logging
from collections.abc import Iterable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError, OperationalError

from velocista.domain.shared.errors import (
    Conflict,
    DeviceUnavailable,
    DomainError,
    Forbidden,
    NotFound,
    Validation,
)

log = logging.getLogger("velocista.errors")

# Tipo de error de dominio → código HTTP.
_HTTP_STATUS = {
    DeviceUnavailable: 503,
    NotFound: 404,
    Conflict: 409,
    Forbidden: 403,
    Validation: 422,
}


def _status_for(error: DomainError) -> int:
    for error_type, status in _HTTP_STATUS.items():
        if isinstance(error, error_type):
            return status
    return 400  # DomainError genérico


class ErrorDetail(BaseModel):
    """Cuerpo de `detail` en un error de negocio."""

    reason: str = Field(
        description="Código corto y estable; la consola decide el mensaje final.",
        examples=["not_calibrated"],
    )
    detail: str = Field(
        description="Texto legible para mostrar o registrar.",
        examples=["Calibra el robot antes de arrancar"],
    )


class BusinessError(BaseModel):
    """Formato estándar de error de negocio de la API."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"detail": {"reason": "not_calibrated", "detail": "Calibra el robot"}}
        }
    )
    detail: ErrorDetail


def error_responses(
    errors: dict[int, str], plain: Iterable[int] = ()
) -> dict[int | str, dict[str, Any]]:
    """Documents error responses in Swagger.

    Business errors use the standard `BusinessError` body. Status codes listed in `plain`
    come from `HTTPException`/middleware with a different body, so only a description is shown.
    """
    skip = set(plain)
    return {
        code: (
            {"description": text} if code in skip else {"model": BusinessError, "description": text}
        )
        for code, text in errors.items()
    }


def _response(status: int, reason: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"detail": {"reason": reason, "detail": detail}}
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_: Request, e: DomainError) -> JSONResponse:
        return _response(_status_for(e), e.reason, e.detail)

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, e: IntegrityError) -> JSONResponse:
        log.warning("Violación de integridad: %s", e.orig)
        return _response(409, "conflict", "El dato entra en conflicto con uno existente")

    @app.exception_handler(OperationalError)
    async def _db_down(_: Request, e: OperationalError) -> JSONResponse:
        log.error("Base de datos no disponible: %s", e.orig)
        return _response(503, "database_unavailable", "La base de datos no está disponible")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, e: Exception) -> JSONResponse:
        log.exception("Error no controlado en %s %s", request.method, request.url.path)
        return _response(500, "internal_error", "Ocurrió un error inesperado")
