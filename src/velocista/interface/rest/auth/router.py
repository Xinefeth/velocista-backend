"""Inicio de sesión de la consola. La cuenta de operación se configura en el entorno."""

import hmac

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from velocista.infrastructure.config.settings import settings
from velocista.infrastructure.security import create_access_token, decode_access_token
from velocista.interface.rest.errors import error_responses

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)


@router.post(
    "/login",
    operation_id="login",
    summary="Log in and get an access token",
    description=(
        "Exchanges the admin username and password for a signed bearer token. "
        "Send it afterwards as `Authorization: Bearer <token>`. Only needed when "
        "the server runs with `AUTH_REQUIRED=true`."
    ),
    responses=error_responses(
        {
            401: "Wrong username or password (`invalid_credentials`)",
            503: "Server has no valid `SECRET_KEY` (`auth_unconfigured`)",
        }
    ),
)
def login(data: LoginInput):
    username_ok = hmac.compare_digest(data.username.encode(), settings.admin_username.encode())
    password_ok = hmac.compare_digest(data.password.encode(), settings.admin_password.encode())
    if not settings.admin_password or not (username_ok and password_ok):
        raise HTTPException(
            401, detail={"reason": "invalid_credentials", "detail": "Credenciales inválidas"}
        )
    if len(settings.secret_key) < 32:
        raise HTTPException(
            503, detail={"reason": "auth_unconfigured", "detail": "Configura SECRET_KEY"}
        )
    return {
        "access_token": create_access_token(data.username),
        "token_type": "bearer",
        "expires_in": settings.token_expire_minutes * 60,
    }


@router.get(
    "/me",
    operation_id="getCurrentUser",
    summary="Get the authenticated user",
    description=(
        "Returns the username stored in the bearer token. Useful to check that a "
        "saved token is still valid."
    ),
    responses=error_responses({401: "Missing, expired or tampered token (`unauthorized`)"}),
)
def current_user(request: Request):
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    try:
        if scheme.lower() != "bearer":
            raise ValueError("Bearer token required")
        return {"username": decode_access_token(token)["sub"]}
    except ValueError as exc:
        raise HTTPException(
            401, detail={"reason": "unauthorized", "detail": "Inicia sesión"}
        ) from exc
