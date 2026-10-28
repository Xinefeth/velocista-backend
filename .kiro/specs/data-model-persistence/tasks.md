# Implementation Plan — Data Model and Persistence

## Overview

`[x]` marks work done and verified (migration files, models, and read-only queries on Render on
2026-10-27/28); `[ ]` marks pending work; `*` is optional. No migration or model was changed.

## Tasks

- [x] 1. Versioned schema
  - [x] 1.1 Linear chain `0001`→`0005` — `src/velocista/infrastructure/persistence/migrations/versions/`
  - [x] 1.2 Migrate on start — `src/velocista/infrastructure/startup.py`
  - [x] 1.3 Render is at revision `0005` (`alembic_version` read-only query)
  - [x] 1.4 `0005` downgrade refuses to drop external data — `0005_external_sessions.py:62-65`
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Core, builder, rules, runs and log tables
  - [x] 2.1 19 tables present on Render (counted by query)
  - [x] 2.2 Reference seed in `0003` — `0003_reference_seed.py`, `0003_reference_data.json`
  - [x] 2.3 Run context snapshot stored at `run_started` — `src/velocista/infrastructure/integrations/velocista_sim/persistence.py:203-228`
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 3. External ingestion tables
  - [x] 3.1 `external_session`/`external_telemetry` models — `src/velocista/infrastructure/persistence/models/external.py`
  - [x] 3.2 Migration `0005` incl. nullable simulator columns and `uq_run_external` — `0005_external_sessions.py`
  - [x] 3.3 `run.ingestion_id` unique — `0004_simulation_ingestion.py`
  - [x] 3.4 Live `external_telemetry` constraints/indexes inspected: PK `uq_external_sample`, 2 FKs, index `ix_external_telemetry_run_id`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 4. Reconcile code and live database
  - [ ] 4.1 Decide and record: keep the live shape (single PK `uq_external_sample`) or restore two indexes
  - [ ] 4.2 Align `models/external.py` and `0005_external_sessions.py` (or a new migration `0006`) with the decision
  - [ ] 4.3 Verify on an empty local database what `alembic upgrade head` creates for `external_telemetry` (not verified)
  - _Requirements: 4.1, 4.2, 4.3_

- [ ] 5. Retention
  - [ ] 5.1 Purge policy for `external_telemetry` only — see `telemetry-ingestion` task 7
  - _Requirements: 5.2, 5.3_

- [ ]* 6. Housekeeping
  - [ ]* 6.1 Decide the fate of unused tables `event`, `lap_segment`, `lap_sector`, `robot_config` (empty on Render)
  - [ ]* 6.2 Add an index only if a query needs it; none is known today
  - _Requirements: 5.1_

## Notes

- Sizes and row counts are a snapshot (2026-10-28); they change as runs are recorded.
- Not verified: the output of a fresh local `alembic upgrade head`, and whether unused tables are
  referenced by code paths not exercised in tests.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "2.1", "2.2", "2.3", "3.1", "3.2", "3.3", "3.4"] },
    { "id": 1, "tasks": ["4.1", "4.3"] },
    { "id": 2, "tasks": ["4.2", "5.1", "6.1", "6.2"] }
  ]
}
```
