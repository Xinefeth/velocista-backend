# Design Document — Testing Strategy

## Introduction

The suite follows the pyramid by test type. Pure rules and use cases run in milliseconds with
in-memory doubles; REST and persistence run against a real PostgreSQL 16 in a throw-away schema; the
WebSocket contract and the simulator contract run without a database. This document describes the
structure, the measured state and the gaps.

## Goals & Non-Goals

**Goals**

- Fast feedback: `unit`, `contract` and WS-engine tests need no database.
- Realistic persistence tests: real PostgreSQL, isolated schema, automatic rollback.
- Contract tests that fail before the frontend breaks.

**Non-Goals**

- Load/performance testing.
- Tests against the Render database (never; see `deployment-operations`).
- Installing new tooling in the repo without approval (coverage, import-linter).

## Architecture Overview

```
                       ┌─────────────── e2e/flows (7) ───────────────┐   few, slow
                       │ operator journey · robot WS flow             │
                ┌──────┴───────── integration (291) ─────────────────┴──────┐
                │ rest/<context>/… · persistence/ · external persistence      │  needs PostgreSQL
        ┌───────┴──────────── contract (72) ────────────────────────────────┴───┐
        │ OpenAPI · error format · WS message catalog                              │  no DB
   ┌────┴────────────── unit (142) ─────────────────────────────────────────────┴───┐
   │ domain rules · use cases with InMemory* doubles                                   │  no DB
   └─────────────────────────────────────────────────────────────────────────────────┘
   + tests/test_ws_engine.py (13)  + tests/test_sim_integration.py (87, schema fixtures, no DB)
```

Isolation of the database (from `tests/support/db_fixtures.py`):

```
fixture db ─ BEGIN ─ CREATE SCHEMA qa_<uuid> ─ SET LOCAL search_path ─ create_all + seed ─▶ test
                                                                    └─ ROLLBACK (schema disappears)
```

## Component Design

### 3.1 Measured state (full run 2026-11-03, after EN-28 incl. perimeter/area)

| Group | Collected |
|---|---:|
| `tests/unit` | 142 |
| `tests/contract` | 72 |
| `tests/integration` | 291 |
| `tests/e2e` | 7 |
| `tests/test_sim_integration.py` | 87 |
| `tests/test_ws_engine.py` | 13 |
| **Total collected** | **612** |

**Full run against the local PostgreSQL (`127.0.0.1:15432`), 2026-11-03: 597 passed, 15 skipped, 0
failed** (597 + 15 = 612; 5 min 14 s). The no-DB subset (unit + contract + WS engine + simulator) ran
separately: 305 passed, 9 skipped. Earlier full run (2026-10-28, before the EN-28 commit): 540 passed,
15 skipped, 0 failed.

All 15 skips are identified: **13 template skips** marked `plantilla de formato` (4 in
`tests/contract/test_message_catalog.py`, 2 in `tests/e2e/test_ws_robot_flow.py`, 2 in
`tests/integration/persistence/test_runs_repository.py`, 2 in
`tests/unit/application/runs/test_close_lap_use_case.py`, 3 in `tests/unit/domain/runs/test_lap_rules.py`)
and **2 opt-in live tests** (`SIM_LIVE_TEST=1` in `tests/integration/test_external_persistence.py`;
`TRACKS_LIVE_TEST=1` in `tests/integration/test_tracks_live.py`).

EN-28 added 241 tests (184 for the tracks API plus 57 for perimeter and area): unit
(`tests/unit/domain/tracks`, `tests/unit/application/tracks`), repository and constraints and migrations
0006/0007/0008 (`tests/integration/persistence/test_tracks_*.py`), routes and the two 422 shapes
(`tests/integration/rest/tracks/`), OpenAPI units (`tests/contract/rest/test_tracks_openapi_units.py`),
profiles with `rules.track` (`tests/integration/rest/rules/test_profiles_api.py`) and the opt-in live
test.

### 3.2 Quality tools

- `ruff check .` → **All checks passed**.
- `ruff format --check .` → **2 files would be reformatted**:
  `src/velocista/infrastructure/integrations/velocista_sim/client.py` and `tests/test_sim_integration.py`.
- Coverage: **not measured** (`pytest-cov` is not in `pyproject.toml` or `requirements.lock`).

### 3.3 Fixtures and contract data

- `tests/conftest.py`: `InMemoryRunRepository` (implements the `RunRepository` port) and an autouse
  fixture that sets `settings.sim_enabled = False`.
- `tests/support/db_fixtures.py`: `db`, `client`, `build`, `service_headers`; seeds a component type, a
  slot, the `pid` controller and the `club` profile.
- `tests/support/track_fixtures.py`: `track_payload()` (valid JSON body), `make_track()` (domain entity)
  and `many_points()`, shared by the tracks tests.
- Migration tests use the pattern of `test_alembic_upgrade_and_empty_downgrade`: a rolled-back
  transaction in a temporary schema, driven through `config.attributes["connection"]`.
- `tests/fixtures/sim_contract/{valid,invalid}`: official simulator frames (hello, config, telemetry
  including `idle-no-run`, events, errors).

### 3.4 How to run

```powershell
docker compose up -d db        # Docker Desktop must be open; DB on 127.0.0.1:15432
pytest                         # everything
pytest tests/unit tests/contract tests/test_ws_engine.py   # no DB
pytest tests/integration/test_external_persistence.py      # external session + telemetry caps
```

## Data Flow

Test → `TestClient` → FastAPI app with `get_session` overridden to the isolated connection →
repositories → PostgreSQL schema `qa_<uuid>` → rollback.

## Design Decisions & Trade-offs

- **Real PostgreSQL instead of SQLite or mocks.** JSONB, constraints and `ON CONFLICT` behave as in
  production. Trade-off: Docker must be running; without it the database-backed tests cannot run.
- **Isolated schema + rollback.** No cleanup code and any order works. Trade-off: tests that need real
  commits (e.g. concurrent sessions) are harder to write.
- **Shared engine with the application.** Simple, but a defined `DATABASE_URL` (such as a Render URL)
  would redirect the tests; there is no guard today (see tasks 5.1).

## Known gaps

- Coverage is not measured; no `domain/builder` or `domain/catalog` pure-rule tests (no pure rules yet).
- `tests/README.md` §8 reports 219 new cases, 1 pre-existing failure and 13 skips; the real suite has
  612 collected tests and 15 skips (13 templates + 2 opt-in). `tests/PLAN_DE_PRUEBAS.md` §6 still lists a timezone failure
  (`test_version_lifecycle_snapshots_and_inventory`) that I could not re-verify without the database.
- No test covers retention/purge of old telemetry (the feature does not exist yet).
