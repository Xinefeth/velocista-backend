"""Protege la API de operación cuando AUTH_REQUIRED está activo."""

from fastapi import Request
from starlette.responses import JSONResponse

from velocista.infrastructure.config.settings import settings
from velocista.infrastructure.security import decode_access_token


async def require_authentication(request: Request, call_next):
    public = {"/api/health", "/api/auth/login", "/api/runs/ingest"}
    if (
        settings.auth_required
        and request.method != "OPTIONS"
        and request.url.path.startswith("/api/")
        and request.url.path not in public
    ):
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        try:
            if scheme.lower() != "bearer":
                raise ValueError("Bearer token required")
            request.state.principal = decode_access_token(token)
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={"detail": {"reason": "unauthorized", "detail": "Inicia sesión"}},
                headers={"WWW-Authenticate": "Bearer"},
            )
    return await call_next(request)
