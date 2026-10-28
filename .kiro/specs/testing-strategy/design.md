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
                ┌──────┴───────── integration (164) ─────────────────┴──────┐
                │ rest/<context>/… · persistence/ · external persistence      │  needs PostgreSQL
        ┌───────┴──────────── contract (52) ────────────────────────────────┴───┐
        │ OpenAPI · error format · WS message catalog                              │  no DB
   ┌────┴────────────── unit (48) ──────────────────────────────────────────────┴───┐
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

### 3.1 Measured state (2026-10-28)

| Group | Collected | Result in this session |
|---|---:|---|
| `tests/unit` + `tests/contract` + `tests/test_ws_engine.py` | 113 | **104 passed, 9 skipped** (2.39 s) |
| `tests/test_sim_integration.py` | 87 | **87 passed** (4.10 s) |
| `tests/integration` | 164 | not run (database down) |
| `tests/e2e` | 7 | not run (database down) |
| **Total collected** | **371** | — |

The previous full run reported by another session was **357 passed, 14 skipped** (357 + 14 = 371,
consistent with the collection). I did not reproduce the database-backed part. Of the 14 skips, 12
are identified: 9 template skips counted above, `tests/e2e/test_ws_robot_flow.py` (1),
`tests/integration/persistence/test_runs_repository.py` (1) and the opt-in live simulator test
`tests/integration/test_external_persistence.py` (`SIM_LIVE_TEST=1`) (1). Two skips are not identified.

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
  371 collected tests and 14 skips. `tests/PLAN_DE_PRUEBAS.md` §6 still lists a timezone failure
  (`test_version_lifecycle_snapshots_and_inventory`) that I could not re-verify without the database.
- No test covers retention/purge of old telemetry (the feature does not exist yet).
