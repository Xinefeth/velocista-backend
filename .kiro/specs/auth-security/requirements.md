# Requirements Document — Authentication and Security

## Introduction

The API protects three kinds of caller: the console operator (JWT from a single admin account), the
physical devices (static `x-device-token` per device) and the simulation service (a service token for
`POST /api/runs/ingest`). Secrets come only from environment variables. This spec records the
behaviour verified in the code on 2026-10-28 and the known risks. No credential values appear here.

## Glossary

- **JWT de consola**: Token HS256 firmado con `SECRET_KEY` (iss `velocista-backend`, aud `velocista-console`).
- **Cuenta admin**: Única cuenta de operación, definida por `ADMIN_USERNAME` y `ADMIN_PASSWORD`.
- **Token de dispositivo**: `DEVICE_TOKEN_ROBOT` / `DEVICE_TOKEN_TIMER`, enviados en `x-device-token`.
- **Token de servicio del simulador**: `SIMULATION_SERVICE_TOKEN`, enviado como `Authorization: Bearer`.
- **AUTH_REQUIRED**: Interruptor que activa la protección de `/api/*`.
- **CORS**: Lista de orígenes permitidos (`CORS_ORIGINS`).
- **Producción**: `APP_ENV=production`.

## Requirements

### Requirement 1: Inicio de sesión y JWT de consola

**User Story:** As an operator, I want to log in once and use a short-lived token, so that the console
can call the API securely.

#### Acceptance Criteria

1. WHEN the credentials match `ADMIN_USERNAME`/`ADMIN_PASSWORD` (compared in constant time), THE API SHALL return a bearer token and `expires_in`.
2. IF the credentials do not match or `ADMIN_PASSWORD` is empty, THEN THE API SHALL answer 401 `invalid_credentials`.
3. IF `SECRET_KEY` is shorter than 32 characters, THEN THE API SHALL answer 503 `auth_unconfigured` on login.
4. THE token SHALL carry `sub`, `iat`, `exp`, `iss=velocista-backend`, `aud=velocista-console`, and expire after `TOKEN_EXPIRE_MINUTES` (default 60, range 1–1440).
5. WHEN a token is decoded, THE API SHALL require `sub`, `iat` and `exp` and SHALL reject a `sub` different from `ADMIN_USERNAME`.

### Requirement 2: Protección de la API REST

**User Story:** As an owner, I want every operational endpoint protected, so that only the signed-in
operator can change data.

#### Acceptance Criteria

1. WHILE `AUTH_REQUIRED` is true, THE API SHALL require a valid `Authorization: Bearer` token for every `/api/*` request except `OPTIONS`, `/api/health`, `/api/auth/login` and `/api/runs/ingest`.
2. IF the token is missing, malformed or expired, THEN THE API SHALL answer 401 `unauthorized` with `WWW-Authenticate: Bearer`.
3. WHEN `/api/runs/ingest` is called, THE API SHALL require `Bearer <SIMULATION_SERVICE_TOKEN>` (constant-time compare) and SHALL answer 503 if the token is not configured and 401 if it is wrong.
4. THE `GET /api/health` endpoint SHALL stay public.

### Requirement 3: Dispositivos y consola WebSocket

**User Story:** As an operator, I want only my devices and my console to connect.

#### Acceptance Criteria

1. WHEN a device connects, THE Gateway SHALL require its own token (`x-device-token` header or `?token=`) and SHALL close with 1008 otherwise.
2. WHEN a console connects with an `Origin` not in `CORS_ORIGINS`, THE Gateway SHALL close with 1008.
3. WHILE `AUTH_REQUIRED` is true, THE console WebSocket SHALL require a valid JWT.

### Requirement 4: Secretos y producción

**User Story:** As an owner, I want the service to refuse to start with weak configuration in production.

#### Acceptance Criteria

1. WHILE `APP_ENV=production`, THE API SHALL fail at startup unless `AUTH_REQUIRED=true`.
2. WHILE `APP_ENV=production`, THE API SHALL require `SECRET_KEY` ≥ 32 chars, `SIMULATION_SERVICE_TOKEN` ≥ 32 chars and `ADMIN_PASSWORD` ≥ 12 chars.
3. WHILE `APP_ENV=production`, THE API SHALL require device tokens ≥ 24 chars, not starting with `dev-token-`, and different from each other.
4. WHILE `APP_ENV=production`, THE API SHALL reject a wildcard (`*`) in `CORS_ORIGINS`.
5. THE `.env` file SHALL be excluded from version control and secrets SHALL NOT be written to logs, specs or chat.
6. IF a credential is pasted into a chat, log or screenshot, THEN THE owner SHALL rotate it.

### Requirement 5: Riesgos conocidos a reducir

**User Story:** As a security-minded maintainer, I want known weaknesses tracked.

#### Acceptance Criteria

1. THE login endpoint SHOULD limit repeated failed attempts (no limiter exists today).
2. THE console JWT SHOULD NOT travel in the WebSocket URL (see `ws-gateway-contract`, requirement 7).
3. THE device tokens SHOULD be accepted only in the `x-device-token` header.
4. THE API SHOULD allow revoking a token before it expires (no revocation exists today).
