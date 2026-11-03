# Implementation Plan — Testing Strategy

## Overview

`[x]` marks work done and verified (by reading files or running tests on 2026-10-28 and 2026-11-03);
`[ ]` marks pending work. Tasks marked `*` are optional. The full suite, database-backed tests included,
was run on 2026-11-03: 597 passed, 15 skipped, 0 failed.

## Tasks

- [x] 1. Test types and structure
  - [x] 1.1 Folders `unit/`, `integration/`, `contract/`, `e2e/`, `support/` exist — `tests/`
  - [x] 1.2 No-DB subset passes: 218 passed, 9 skipped (2026-11-03) — `tests/unit`, `tests/contract`, `tests/test_ws_engine.py`
  - [x] 1.3 Simulator tests pass without DB: 87 passed — `tests/test_sim_integration.py`
  - [x] 1.4 612 tests collected on 2026-11-03 (= 597 passed + 15 skipped of the full run the same day)
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Isolated PostgreSQL fixtures
  - [x] 2.1 `db`/`client` create `qa_<uuid>` and roll back — `tests/support/db_fixtures.py`
  - [x] 2.2 Contract fixtures from `velocista-sim` — `tests/fixtures/sim_contract/`
  - _Requirements: 2.1, 2.2, 3.2_

- [x] 3. Contract tests
  - [x] 3.1 OpenAPI, error format and documentation — `tests/contract/rest/`
  - [x] 3.2 WS message catalog and envelope — `tests/contract/websocket/`, `tests/contract/test_message_catalog.py`
  - [x] 3.3 Simulator frame validation against the official fixtures — `tests/test_sim_integration.py` (87 pass; `docs/SIMULATOR.md` says it also covers rejections, timeout, reconnection and write failures; individual tests not reviewed)
  - [x] 3.4 EN-28 tracks tests (241): domain and use cases, repository and constraints, migrations 0006/0007/0008, perimeter and area, routes, both 422 shapes, OpenAPI units, profiles with `rules.track` — `tests/unit/domain/tracks/`, `tests/unit/application/tracks/`, `tests/integration/persistence/test_tracks_repository.py`, `tests/integration/persistence/test_tracks_migration.py`, `tests/integration/rest/tracks/`, `tests/contract/rest/test_tracks_openapi_units.py`, `tests/support/track_fixtures.py` (full run 2026-11-03: 597 passed, 15 skipped, 0 failed)
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 4. Lint
  - [x] 4.1 `ruff check .` passes
  - _Requirements: 4.1_

- [ ] 5. Safety and hygiene
  - [ ] 5.1 Abort the run when `DATABASE_URL` is set (the test engine would connect to it) — `tests/conftest.py`
  - [ ] 5.2 Run `ruff format` on `src/velocista/infrastructure/integrations/velocista_sim/client.py` and `tests/test_sim_integration.py` (2 files would be reformatted)
  - [ ] 5.3 Remove or implement the 13 template skips (all 15 skips are now identified: 13 templates + 2 opt-in live tests, `SIM_LIVE_TEST` and `TRACKS_LIVE_TEST`)
  - _Requirements: 2.3, 4.2, 5.1_

- [x] 6. Re-run the database-backed suite
  - [x] 6.1 Started `docker compose up -d db` and ran `pytest -rs` on 2026-11-03: **597 passed, 15 skipped, 0 failed** (612 collected)
  - [x] 6.2 The timezone failure listed in `tests/PLAN_DE_PRUEBAS.md` §6 (#1) did not reproduce: 0 failures in the full run (the machine's timezone was not checked)
  - _Requirements: 2.4, 5.1_

- [ ] 7. Documentation accuracy
  - [ ] 7.1 Update `tests/README.md` §8 and `tests/PLAN_DE_PRUEBAS.md` §6 to the real counts
  - _Requirements: 5.3_

- [ ]* 8. Coverage
  - [ ]* 8.1 Measure coverage with `pytest-cov` (not installed; adding it needs approval) and set a floor for `domain` and `application`
  - _Requirements: 5.2_

- [ ]* 9. Gaps in coverage
  - [ ]* 9.1 Pure-rule tests for `domain/builder` and `domain/catalog` when rules exist
  - [ ]* 9.2 Tests for telemetry retention once implemented (see `telemetry-ingestion`)
  - _Requirements: 5.1_

## Notes

- `tests/PLAN_DE_PRUEBAS.md` and `tests/README.md` still carry old counts (task 7.1).
- Counts for the no-DB groups were obtained by running them; the totals by `pytest --collect-only`.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "2.1", "2.2", "3.1", "3.2", "3.3", "3.4", "4.1"] },
    { "id": 1, "tasks": ["5.1", "5.2", "6.1"] },
    { "id": 2, "tasks": ["5.3", "6.2", "7.1", "8.1", "9.1", "9.2"] }
  ]
}
```
