# Design Document — Deployment and Operations

## Introduction

One Docker image runs on Render and locally. Render provides the PostgreSQL connection string through
`DATABASE_URL` (internal URL); administrators reach the database through the external URL. This design
lists the deployment pieces, the environment, the operating procedures and the disk-full incident.

## Goals & Non-Goals

**Goals**

- A predictable, migrate-then-serve start-up and a meaningful health check.
- A documented, safe procedure to inspect and clean the database.
- Lessons from the 2026-10-27 incident turned into requirements.

**Non-Goals**

- Multi-region or multi-instance deployment (single worker by design).
- Backups beyond what the Render plan provides (not verified).

## Architecture Overview

```
GitHub ─▶ Render build (Dockerfile) ─▶ velocista-backend (web, free, 1 instance, /api/health)
                                              │ internal DATABASE_URL
                                              ▼
                                   velocista-db (PostgreSQL, free, db "velocista")
                                              ▲ external URL (admin only)
   Operator PC ── pgAdmin / read-only scripts ┘        velocista-sim (Railway) ◀── WS client of the backend
Local dev: docker compose db (127.0.0.1:15432) · uvicorn · pytest (isolated schemas)
```

## Component Design

### 3.1 Files

| File | Role |
|---|---|
| `Dockerfile` | Image, non-root user, `CMD python -m velocista.infrastructure.startup` |
| `src/velocista/infrastructure/startup.py` | `alembic upgrade head`, then `uvicorn` (`workers=1`, `proxy_headers=True`) |
| `render.yaml` | Web service and database definitions |
| `docker-compose.yml` | Local PostgreSQL 16 on `127.0.0.1:${POSTGRES_PORT:-15432}` with healthcheck |
| `.env.example` | Variable template (no secrets) |
| `src/velocista/infrastructure/config/settings.py` | Environment parsing and production validation |
| `docs/SIMULATOR.md` | Simulator variables and persistence/recovery notes |

### 3.2 Environment variables

In `render.yaml`: `APP_ENV=production`, `AUTH_REQUIRED=true`, `DATABASE_URL` (from `velocista-db`),
`CORS_ORIGINS` (set by hand), `SECRET_KEY` (generated), `ADMIN_USERNAME=admin`, `ADMIN_PASSWORD` (set by
hand), `DEVICE_TOKEN_ROBOT`/`DEVICE_TOKEN_TIMER`/`SIMULATION_SERVICE_TOKEN` (generated).

Not in `render.yaml`: every `SIM_*` variable (`SIM_ENABLED`, `SIM_WS_URL`, `SIM_INTERNAL_ROBOT_ID`,
`SIM_SETUP_ID`, `SIM_PROFILE_ID`, `SIM_STORE_TELEMETRY`, `SIM_TELEMETRY_STRIDE`,
`SIM_MAX_TELEMETRY_ROWS_PER_RUN`). Their Render values are **not verifiable from the repository**;
observed behaviour on 2026-10-28 (≈10 stored rows/s) is consistent with stride 5.

### 3.3 Runbook (to be restored in the repository)

`docs/OPERATIONS.md` existed untracked at the start of the 2026-10-27 session and is absent from the
working tree on 2026-10-28 (`git status` clean). Its content, as it was used:

0. Check the target: `SELECT current_database(), inet_server_addr();`
1. Table sizes: `pg_total_relation_size` per table, top 10.
2. Telemetry size and rows without run: `count(*)`, `WHERE run_id IS NULL`.
3. Soft cleanup: `DELETE FROM external_telemetry WHERE run_id IS NULL;` (does not return disk to the
   OS; autovacuum reuses it).
4. (Added by the incident) Disk-full path: export rows with `run_id` locally, `DROP TABLE`, recreate with
   the real DDL, verify.

### 3.4 Real DDL used to recreate `external_telemetry` (2026-10-27)

```sql
CREATE TABLE external_telemetry (
    session_id  varchar(200) NOT NULL REFERENCES external_session(id),
    seq         bigint       NOT NULL,
    run_id      bigint       REFERENCES run(id),
    t_ms        bigint       NOT NULL,
    received_at timestamptz  NOT NULL,
    payload     jsonb        NOT NULL,
    CONSTRAINT uq_external_sample PRIMARY KEY (session_id, seq)
);
CREATE INDEX ix_external_telemetry_run_id ON external_telemetry (run_id);
```

## Data Flow

Incident timeline (2026-10-27):

```
telemetry stored at 50 Hz, idle included ─▶ external_telemetry 994,636 rows / 845 MB (986,794 without run)
─▶ database 854 MB, disk full ─▶ TRUNCATE failed: DiskFull "could not extend file ... base/16389/16887"
   (the file was a NEW relfilenode created by the TRUNCATE; <8 KB free)
─▶ export 7,842 rows with run_id to a local CSV ─▶ DROP TABLE (commit) ─▶ database 9,614 kB
─▶ CREATE TABLE + INDEX ─▶ ingestion limited (active runs, stride 5, cap 20,000) ─▶ 52 rows after a 6 s run
```

## Design Decisions & Trade-offs

- **Single worker/instance.** Hub and simulator session are in process; no distributed coordination.
- **Internal vs external URL.** The backend uses the internal URL (private network); humans use the
  external one. Trade-off: the external URL must be handled as a secret.
- **`DROP` over `TRUNCATE` on a full disk.** Dropping frees space at commit; trade-off: the table is
  missing between the two steps, so the simulator cannot store telemetry for a few seconds.
- **Two transactions (DROP, then CREATE)** so the space freed by the drop exists before the CREATE
  needs new files.
- **Run tests only against the local database.** The test engine reads `settings.database_url`; never
  export `DATABASE_URL` for Render when running `pytest`.
