# Implementation Plan — Authentication and Security

## Overview

`[x]` marks work done and verified in the code (file evidence); `[ ]` marks pending work; `*` is
optional. Auth tests (`tests/integration/test_authentication.py`,
`tests/integration/rest/auth/test_auth_api.py`) use the isolated PostgreSQL fixtures and were not run in
the documentation session (database down); the behaviour below was verified by reading the code.

## Tasks

- [x] 1. Login and JWT
  - [x] 1.1 Constant-time credential check, 401 `invalid_credentials`, 503 `auth_unconfigured` — `src/velocista/interface/rest/auth/router.py`
  - [x] 1.2 HS256 token with `iss`/`aud`/`exp`; strict decode and `sub` check — `src/velocista/infrastructure/security.py`
  - [x] 1.3 Lifetime from `TOKEN_EXPIRE_MINUTES` (1–1440) — `src/velocista/infrastructure/config/settings.py:34`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. REST protection
  - [x] 2.1 Middleware guards `/api/*` with public exceptions — `src/velocista/interface/rest/auth/middleware.py`
  - [x] 2.2 Service token for `/api/runs/ingest` (503 if unset, 401 if wrong) — `src/velocista/interface/rest/runs/router.py:36-47`
  - [x] 2.3 Public `GET /api/health` — `src/velocista/main.py`
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 3. WebSocket protection
  - [x] 3.1 Device tokens (constant-time) and close 1008 — `src/velocista/interface/websocket/gateway.py:86-89`
  - [x] 3.2 Console Origin check and JWT — `gateway.py:128-143`
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 4. Production configuration guard
  - [x] 4.1 Startup fails on weak secrets, missing `AUTH_REQUIRED`, equal device tokens, wildcard CORS — `src/velocista/infrastructure/config/settings.py:36-57`
  - [x] 4.2 `.env` ignored by git; Render generates secrets — `.gitignore`, `render.yaml`
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ] 5. Reduce known risks
  - [ ] 5.1 Login rate limiting / lockout — `src/velocista/interface/rest/auth/router.py`
  - [ ] 5.2 Console JWT out of the URL (first-message `auth`) — see `ws-gateway-contract` task 7
  - [ ] 5.3 Device tokens only in `x-device-token` — `src/velocista/interface/websocket/gateway.py:86`
  - [ ]* 5.4 Token revocation or shorter lifetime with refresh
  - [ ]* 5.5 Require `Origin` for console WS in production
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [ ] 6. Credential hygiene (owner actions, status unknown)
  - [ ] 6.1 Rotate the `velocista-db` password — it appeared several times in chat and screenshots on 2026-10-27/28
  - [ ] 6.2 After rotating, update `DATABASE_URL` of `velocista-backend` on Render if it is not propagated automatically
  - [ ] 6.3 Confirm on the Render panel that `ADMIN_PASSWORD`, `CORS_ORIGINS` are set (`sync: false`, not verifiable from the repo)
  - _Requirements: 4.5, 4.6_

- [ ]* 7. Tests
  - [ ]* 7.1 Add tests for the production validators and the service-token endpoint if missing (not reviewed in detail)
  - _Requirements: 4.1, 4.2, 2.3_

## Notes

- Not verified: the values configured on Render, whether URLs with tokens appear in Render's logs, and
  the auth tests' current result.
- No secret value is recorded in this spec.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "2.1", "2.2", "2.3", "3.1", "3.2", "4.1", "4.2"] },
    { "id": 1, "tasks": ["5.1", "5.2", "5.3", "6.1", "6.3"] },
    { "id": 2, "tasks": ["5.4", "5.5", "6.2", "7.1"] }
  ]
}
```
