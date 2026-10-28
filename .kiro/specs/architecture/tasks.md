# Implementation Plan — Architecture (Clean Architecture)

## Overview

This plan records the state of the architecture, verified on 2026-10-28 by reading the code and
running import greps (no tests were needed for the structural checks). `[x]` marks work done and
verified in the code; `[ ]` marks pending work. Tasks marked `*` are optional.

## Tasks

- [x] 1. Dependency rule in the pure layers
  - [x] 1.1 `domain/` imports no framework — grep over `src/velocista/domain` returned no match
  - [x] 1.2 `application/` imports nothing from `infrastructure`/`interface` — grep over `src/velocista/application` returned no match
  - [x] 1.3 Ports declared per context — `src/velocista/application/<context>/ports.py`
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Composition root
  - [x] 2.1 Services and adapters wired — `src/velocista/composition.py`
  - [x] 2.2 Test doubles injected via `dependency_overrides` — `tests/support/db_fixtures.py`
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 3. Contexts and entry point
  - [x] 3.1 Eight REST routers registered in `MODULE_ROUTERS` — `src/velocista/main.py`
  - [x] 3.2 `GET /api/health` returns 503 when the database is unreachable — `src/velocista/main.py`
  - _Requirements: 3.1, 3.2_

- [x] 4. WebSocket gateway as ACL
  - [x] 4.1 Legacy `tipo` frames translated before validation — `src/velocista/interface/websocket/gateway.py`, `contract/translation.py`
  - [x] 4.2 Robot messages dropped until the manifest arrives (`no_manifest`) — `gateway.py`
  - [x] 4.3 `/ws/robot` rejected while the simulator source is enabled — `gateway.py`
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 5. Deployment
  - [x] 5.1 Migrate-then-serve, one worker — `src/velocista/infrastructure/startup.py`
  - [x] 5.2 Docker image, non-root user — `Dockerfile`
  - [x] 5.3 Render blueprint with health check `/api/health` — `render.yaml`
  - [x] 5.4 Production refuses weak/missing secrets and wildcard CORS — `src/velocista/infrastructure/config/settings.py`
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ] 6. Close the known deviations
  - [ ] 6.1 Route `events`, `optimization`, `rules` and `runs` routers through use cases wired in `composition.py` (today they import `infrastructure.persistence` directly) — `src/velocista/interface/rest/{events,optimization,rules,runs}/router.py`
  - [ ] 6.2 Remove `infrastructure → interface` imports (move the contract models/validators to a neutral package or make the gateway port-based) — `src/velocista/infrastructure/realtime/device_gateway.py`, `registry.py`
  - [ ] 6.3 Give `auth` a `domain`/`application` home or document it as infrastructure-only — `src/velocista/{domain,application}/auth/`
  - _Requirements: 1.5, 1.6, 3.4_

- [ ] 7. Update `docs/ARCHITECTURE.md` to the real state (ingestion implemented, no `commands.py`, no `timer` context, real test suite)
  - _Requirements: 1.5, 3.1_

- [ ]* 8. Enforce the rule automatically
  - [ ]* 8.1 Add an import-rule check (e.g. a pytest that parses imports, or `import-linter`) so deviations cannot grow — not installed in the repo today; adding a dependency needs approval
  - _Requirements: 1.1, 1.2, 1.3, 1.5_

## Notes

- Structural facts come from grep and file reads; none of them depend on the database.
- Not verified: behaviour of the Render service itself (no access to the panel), and the contents of
  `docs/ARCHITECTURE.md` beyond the statements compared in design §3.3.
- `render.yaml` has no `SIM_*` variables, so the simulator integration on Render depends on values set
  by hand in the panel (not verified).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "2.1", "2.2", "3.1", "3.2", "4.1", "4.2", "4.3", "5.1", "5.2", "5.3", "5.4"] },
    { "id": 1, "tasks": ["6.1", "6.2", "6.3"] },
    { "id": 2, "tasks": ["7", "8.1"] }
  ]
}
```
