# Implementation Plan — Telemetry Ingestion

## Overview

`[x]` marks work done and verified in the code (file and line evidence); `[ ]` marks pending work.
Tasks marked `*` are optional. The telemetry-limit tests are database-backed and were not run in the
documentation session; the observed Render behaviour comes from a manual run by the user.

## Tasks

- [x] 1. Store telemetry only for active runs
  - [x] 1.1 Return when there is no run or the run is closed — `src/velocista/infrastructure/integrations/velocista_sim/persistence.py:95`
  - [x] 1.2 Honour `SIM_STORE_TELEMETRY` — `persistence.py:181`; setting in `src/velocista/infrastructure/config/settings.py:19`
  - [x] 1.3 Ordered batches so `run_started` precedes its frames — `persistence.py` (`write`, `_write`)
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Sub-sampling
  - [x] 2.1 `seq % sim_telemetry_stride` filter — `persistence.py:98`; default 5, range 1–100 — `settings.py:21`
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 3. Cap per run
  - [x] 3.1 Cap check, warning and `telemetry_capped` diagnostic — `persistence.py:100-117`; default 20000 — `settings.py:22`
  - [x] 3.2 Counters restored on a failed batch — `persistence.py:83-90`
  - [x] 3.3 `INSERT ... ON CONFLICT DO NOTHING RETURNING seq` — `persistence.py:119-132`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Saturation and recovery
  - [x] 4.1 Bounded queue (5000) with loss counters — `client.py` (`queue`, `dropped`); `docs/SIMULATOR.md`
  - [x] 4.2 Open runs closed as `interrupted` on restart — `persistence.py:61-66` (`recover`)
  - _Requirements: 4.1, 4.3_

- [x] 5. Tests for the limits (database-backed; not re-run in this session)
  - [x] 5.1 Stride 2, cap 3, idle frames ignored, `telemetry_capped` — `tests/integration/test_external_persistence.py:170-245`
  - [x] 5.2 Idle fixture handling without DB — `tests/test_sim_integration.py` (87 pass)
  - _Requirements: 1.1, 2.1, 3.2, 3.3_

- [x] 6. Incident remediation on Render (2026-10-27)
  - [x] 6.1 `external_telemetry` dropped and recreated empty with PK `uq_external_sample`, two FKs and index `ix_external_telemetry_run_id`
  - [x] 6.2 Verified after a 6 s run: 52 rows in `external_telemetry` (≈10 rows/s, stride active)
  - _Requirements: 1.1, 2.1_

- [ ] 7. Retention and purge
  - [ ] 7.1 Decide the policy (age in days, trigger) and implement it without touching `run`/`lap`/`external_session`
  - [ ] 7.2 Log the number of deleted rows and add tests
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 8. Runbook in the repository
  - [ ] 8.1 `docs/OPERATIONS.md` is **missing** from the working tree (it was untracked at session start and is no longer present; `git status` is clean). Recreate and commit it, including the drop/recreate path for a full disk
  - _Requirements: 5.4, 5.5_

- [ ] 9. Configuration on Render
  - [ ] 9.1 `render.yaml` declares no `SIM_*` variable; declare `SIM_STORE_TELEMETRY`, `SIM_TELEMETRY_STRIDE`, `SIM_MAX_TELEMETRY_ROWS_PER_RUN` (or document the panel values). Panel values not verified
  - _Requirements: 1.3, 2.2, 3.1_

- [ ]* 10. Guardrails
  - [ ]* 10.1 Expose `external_telemetry` row count/size in `GET /api/simulator` or health to alert before the disk fills
  - [ ]* 10.2 Optional global size limit
  - _Requirements: 5.2_

## Notes

- The 7,842 run rows exported to CSV before the drop are at
  `C:\Users\Usuario\Desktop\backup_telemetria\external_telemetry_runs_2026-10-27.csv`; the user judged
  them re-recordable and the file optional.
- Not verified: the deployed commit on Render and the Render environment values.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "2.1", "3.1", "3.2", "3.3", "4.1", "4.2", "5.1", "5.2", "6.1", "6.2"] },
    { "id": 1, "tasks": ["8.1", "9.1"] },
    { "id": 2, "tasks": ["7.1", "7.2", "10.1", "10.2"] }
  ]
}
```
