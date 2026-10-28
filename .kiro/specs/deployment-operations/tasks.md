# Implementation Plan — Deployment and Operations

## Overview

`[x]` marks work done and verified (code read or action observed); `[ ]` marks pending work; `*` is
optional. Render panel values could not be read from this repository or session.

## Tasks

- [x] 1. Container and start-up
  - [x] 1.1 Dockerfile (slim image, lockfile, non-root user) — `Dockerfile`
  - [x] 1.2 Migrate then serve, one worker — `src/velocista/infrastructure/startup.py`
  - [x] 1.3 `DATABASE_URL` priority and scheme normalisation — `src/velocista/infrastructure/config/settings.py:63,75-99`
  - _Requirements: 1.1, 1.2, 1.4_

- [x] 2. Render blueprint and health
  - [x] 2.1 Web service + database, health check `/api/health`, 1 instance — `render.yaml`
  - [x] 2.2 Health returns 503 when the database is unreachable — `src/velocista/main.py` (`health`)
  - _Requirements: 1.3, 2.1, 2.2, 2.3_

- [x] 3. Local environment
  - [x] 3.1 Local PostgreSQL 16 with healthcheck on 15432 — `docker-compose.yml`
  - [x] 3.2 Variable template without secrets — `.env.example`
  - _Requirements: 1.1_

- [x] 4. Incident response (2026-10-27) — performed and verified
  - [x] 4.1 Diagnosed with read-only queries: `external_telemetry` 845 MB, 994,636 rows, 986,794 without run
  - [x] 4.2 `TRUNCATE` failed with `DiskFull`; no data changed
  - [x] 4.3 7,842 run rows exported to a local CSV (count matched) before dropping
  - [x] 4.4 `DROP TABLE` then `CREATE TABLE` + index with the real constraints; database 854 MB → 9,614 kB; `run`/`lap`/`external_session` untouched
  - [x] 4.5 Ingestion limits in code (`a0fed7c`); 52 rows observed after a 6 s run
  - _Requirements: 4.2, 4.3, 4.4_

- [ ] 5. Restore the runbook
  - [ ] 5.1 Recreate `docs/OPERATIONS.md` (size queries, soft cleanup, disk-full path with DROP/recreate and the DDL above) and commit it — file missing from the working tree
  - _Requirements: 4.1, 4.3, 4.4_

- [ ] 6. Make the simulator configuration explicit
  - [ ] 6.1 Add the `SIM_*` variables (including `SIM_STORE_TELEMETRY`, `SIM_TELEMETRY_STRIDE`, `SIM_MAX_TELEMETRY_ROWS_PER_RUN`) to `render.yaml` or document the panel values — `render.yaml`
  - [ ] 6.2 Confirm on the Render panel which commit is deployed (must include `a0fed7c`) — not verifiable here
  - _Requirements: 3.1, 3.2_

- [ ] 7. Credential hygiene (owner)
  - [ ] 7.1 Reset the `velocista-db` password (it was exposed in chat/screenshots) and refresh `DATABASE_URL` if needed
  - [ ] 7.2 Keep the external URL only in `$env:RENDER_DB_URL` for the session
  - _Requirements: 5.1, 5.3_

- [ ] 8. Prevent a repeat
  - [ ] 8.1 Retention/purge of old telemetry — see `telemetry-ingestion` task 7
  - [ ] 8.2 Periodic size check or alert (e.g. expose database size in `/api/health` or an admin endpoint)
  - [ ]* 8.3 Guard in `tests/conftest.py` that aborts when `DATABASE_URL` is set — see `testing-strategy` task 5.1
  - [ ]* 8.4 Evaluate a larger database plan or disk if volume grows (Render disks can only grow; plan limits not verified)
  - _Requirements: 4.5, 5.4_

## Notes

- Verified facts are from reading the repository and from the actions recorded on 2026-10-27/28.
- Not verified: Render free-plan limits, backup policy, the deployed commit, values of panel-only
  variables, and whether the database password has been reset.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "2.1", "2.2", "3.1", "3.2", "4.1", "4.2", "4.3", "4.4", "4.5"] },
    { "id": 1, "tasks": ["5.1", "6.1", "6.2", "7.1", "7.2"] },
    { "id": 2, "tasks": ["8.1", "8.2", "8.3", "8.4"] }
  ]
}
```
