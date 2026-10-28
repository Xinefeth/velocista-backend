# Design Document — Authentication and Security

## Introduction

Security is implemented without a user database: one admin account and static tokens, all supplied by
environment variables. A middleware guards `/api/*`; the WS gateway and the ingestion endpoint carry
their own checks. Production start-up validates secrets so that an insecure deployment cannot boot.

## Goals & Non-Goals

**Goals**

- Protect operational endpoints with a signed, expiring token.
- Authenticate devices and the simulation service with separate secrets.
- Fail fast on weak production configuration.

**Non-Goals**

- Multi-user accounts, roles or a user table.
- OAuth/SSO.
- Rate limiting and token revocation (listed as risks, not implemented).

## Architecture Overview

```
Consola ──POST /api/auth/login──▶ auth/router.login ── hmac(user, password) ──▶ create_access_token (HS256)
Consola ──Bearer JWT──▶ middleware.require_authentication ──▶ decode_access_token ──▶ router
                         public: /api/health · /api/auth/login · /api/runs/ingest · OPTIONS
Simulation service ──Bearer SIMULATION_SERVICE_TOKEN──▶ POST /api/runs/ingest (require_simulation_service)
Robot / Cronómetro ──x-device-token──▶ /ws/robot · /ws/timer (hmac.compare_digest)
Consola WS ──Origin check + JWT (?token= or Authorization)──▶ /ws/console
```

## Component Design

### 3.1 Files

| Concern | File |
|---|---|
| Token create/decode | `src/velocista/infrastructure/security.py` |
| Login, `/me` | `src/velocista/interface/rest/auth/router.py` |
| REST guard | `src/velocista/interface/rest/auth/middleware.py` |
| Ingestion service token | `src/velocista/interface/rest/runs/router.py` (`require_simulation_service`) |
| WS device and console checks | `src/velocista/interface/websocket/gateway.py` |
| Production validation | `src/velocista/infrastructure/config/settings.py` (`validate_production_secrets`) |
| CORS | `src/velocista/main.py` (`CORSMiddleware`, `allow_credentials=True`, origins from settings) |
| Render secrets | `render.yaml` (`generateValue` for secret and tokens, `sync: false` for `ADMIN_PASSWORD`, `CORS_ORIGINS`) |

### 3.2 Environment variables

| Variable | Purpose | Production rule |
|---|---|---|
| `AUTH_REQUIRED` | Enables the REST/WS guard | must be `true` |
| `SECRET_KEY` | Signs the JWT | ≥ 32 chars |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Admin account | password ≥ 12 chars |
| `TOKEN_EXPIRE_MINUTES` | JWT lifetime (default 60) | 1–1440 |
| `DEVICE_TOKEN_ROBOT` / `DEVICE_TOKEN_TIMER` | Device auth | ≥ 24 chars, unique, not `dev-token-*` |
| `SIMULATION_SERVICE_TOKEN` | Ingestion endpoint | ≥ 32 chars |
| `CORS_ORIGINS` | Allowed origins | exact origins, no `*` |

Development defaults (`change-me`, `dev-token-robot`, `dev-token-timer`) exist and are rejected only in
production. `.env` is ignored by git (`.gitignore`); `.env.example` holds placeholders.

## Data Flow

Login → JWT (60 min) → every REST call sends `Authorization: Bearer` → middleware decodes with
issuer/audience/required-claims → `request.state.principal`. Expired or tampered token → 401
`{"detail":{"reason":"unauthorized","detail":"Inicia sesión"}}`.

## Design Decisions & Trade-offs

- **Single admin from environment.** No user table to leak; cost: one shared credential, no roles.
- **Separate secrets per audience** (console, devices, simulation service). A leaked device token does
  not grant console access.
- **Constant-time comparisons** (`hmac.compare_digest`) for passwords and tokens.
- **`/api/runs/ingest` public in the middleware but guarded in the router.** It needs a service token
  instead of a console JWT.
- **Known risks (accepted for now):**
  - No login rate limiting or lockout (grep for rate/lockout/attempt in the auth code found nothing).
  - JWT and device tokens may travel in the WS query string; URLs can appear in proxy or server logs
    (not verified for Render's logs).
  - No token revocation; a stolen JWT is valid until `exp`.
  - Console WS `Origin` check applies only when the header is present, so non-browser clients can omit it.
  - Credentials pasted in chats (e.g. the database password) must be rotated by the owner.
