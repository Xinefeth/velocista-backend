"""Tokens de acceso firmados para la consola; las credenciales solo viven en el servidor."""

from datetime import UTC, datetime, timedelta

import jwt

from velocista.infrastructure.config.settings import settings


def create_access_token(username: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": username,
            "iat": now,
            "exp": now + timedelta(minutes=settings.token_expire_minutes),
            "iss": "velocista-backend",
            "aud": "velocista-console",
        },
        settings.secret_key,
        algorithm="HS256",
    )


def decode_access_token(token: str) -> dict:
    try:
        claims = jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"],
            issuer="velocista-backend",
            audience="velocista-console",
            options={"require": ["sub", "iat", "exp"]},
        )
        if claims["sub"] != settings.admin_username:
            raise ValueError("Invalid account")
        return claims
    except (jwt.PyJWTError, KeyError, TypeError) as exc:
        raise ValueError("Invalid or expired access token") from exc
