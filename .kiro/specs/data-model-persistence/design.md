# Design Document — Data Model and Persistence

## Introduction

SQLAlchemy 2.0 models (`infrastructure/persistence/models/`) are the ORM mapping; repositories
(`persistence/repositories/`) implement the application ports; Alembic (`persistence/migrations/`) owns
the schema. Facts below come from the migration files, the models and read-only queries against the
Render database on 2026-10-27/28, and (for migrations 0006/0007) from the code and the local
development database on 2026-11-03.

## Goals & Non-Goals

**Goals**

- A rebuildable schema through eight linear migrations (`0001`–`0008`).
- Clear ownership of each table by a bounded context.
- A documented difference between the code and the live database.

**Non-Goals**

- Partitioning or archiving (not needed at current volume once telemetry is limited).
- Changing the schema in this spec.

## Architecture Overview

```
models/*.py (ORM) ◀── repositories/*.py (implement application ports) ── Session (db.py, pool 5+10)
        │ metadata
        ▼
migrations/versions: 0001 core ─▶ 0002 profiles/setups/runs ─▶ 0003 reference seed ─▶ 0004 ingestion_id ─▶ 0005 external sessions
                                                          ─▶ 0006 tracks ─▶ 0007 track profiles ─▶ 0008 track metrics (EN-28)
        ▼
PostgreSQL: Render = 19 tables · alembic_version 0005 (as of 2026-10-28)
            local dev = 20 tables · alembic_version 0008
```

## Component Design

### 3.1 Tables by migration (20 with EN-28)

| Migration | Tables / changes |
|---|---|
| `0001_initial_core_schema` | `component_type`, `event`, `robot`, `component`, `robot_config`, `slot`, `version`, `inventory`, `version_part` |
| `0002_profiles_setups_and_runs` | `controller`, `profile`, `setup`, `run`, `lap`, `lap_sector`, `lap_segment` |
| `0003_reference_seed` | Data: component types, slots, controllers, profiles (`0003_reference_data.json`) |
| `0004_simulation_ingestion` | `run.ingestion_id` + unique `uq_run_ingestion_id` |
| `0005_external_sessions` | `external_session`, `external_telemetry`; `run.external_session_id`, `external_run_id`, `closure_status`, unique `uq_run_external`; nullable `run.mode/line/battery_compensation/turbine_power_pct` and `lap.accumulated_error/lost_lines/battery_v` |
| `0006_tracks` | `track` + index `ix_track_profile_id`; `CHECK`s `ck_track_name`, `ck_track_board`, `ck_track_points`, `ck_track_zones`, `ck_track_start_edge`, `ck_track_start_t`, `ck_track_length` |
| `0007_track_profiles` | Data: profiles `lgr2026` and `libre` with `rules.track` (lengths in cm) |
| `0008_track_metrics` | `track.perimeter_cm`, `track.area_cm2` (nullable) + `CHECK`s `ck_track_perimeter`, `ck_track_area`, `ck_track_metrics_closed` |
| (Alembic) | `alembic_version` |

### 3.2 Sizes and rows on Render (2026-10-28, read-only)

Database total **9,614 kB**. Largest: `run` 272 kB (30 rows), `external_session` 264 kB (18), `setup` 192 kB
(61), `version` and `version_part` 96 kB each (4 and 44), `lap` 64 kB (24), `external_telemetry` 24 kB (0
rows, structure and two indexes). Empty and unused by the ingestion: `event`, `lap_segment`,
`robot_config`, `lap_sector`. (A later manual run raised `run` to 31 and `lap` to 27, and
`external_telemetry` to about 50 rows.)

### 3.3 `external_telemetry` — declared vs real

| Aspect | Model and migration 0005 | Live Render table |
|---|---|---|
| Columns | `session_id varchar(200)`, `seq bigint`, `run_id bigint NULL`, `t_ms bigint`, `received_at timestamptz`, `payload jsonb` | same; all NOT NULL except `run_id` |
| Primary key | `PRIMARY KEY (session_id, seq)` **and** `UniqueConstraint(session_id, seq, name="uq_external_sample")` | one constraint: `uq_external_sample` is the **PRIMARY KEY** `(session_id, seq)` |
| Indexes | PK index + `uq_external_sample` + `ix_external_telemetry_run_id` | `uq_external_sample` (the PK index, 60 MB at 994,636 rows) and `ix_external_telemetry_run_id` (6.4 MB) |
| Foreign keys | `session_id → external_session(id)`, `run_id → run(id)` | same two |
| Others | — | no triggers, no RLS policies, no dependent views, owner `velocista` |

The cause of the merge is not established. Whether a fresh `alembic upgrade head` on an empty local
database yields one or two unique indexes was **not verified**. Functional behaviour is identical (one
unique btree on `(session_id, seq)`); the live shape saves one index.

### 3.4 `track` table (EN-28)

`id` bigint identity PK; `name` varchar(80); `board_width_cm`, `board_height_cm`, `start_t`, `length_cm`
float; `closed` boolean; `start_edge` integer; `points` JSONB (array of 2–500) and `zones` JSONB (array of
0–100, default `[]`); `profile_id` varchar(40) NULL → `profile(id)` `ON DELETE RESTRICT` (indexed);
`created_at`/`updated_at` timestamptz; since `0008` also `perimeter_cm` and `area_cm2` float NULL. The `CHECK`s cover scalar columns and array lengths; the array
length check is written as `CASE WHEN jsonb_typeof(col) = 'array' THEN ... ELSE false END` because `AND`
does not fix the evaluation order. Per-element limits live in the domain and the schemas. The `0006`
downgrade refuses while rows exist; the `0007` downgrade refuses while a track uses `lgr2026`/`libre`.
Verified by `tests/integration/persistence/test_tracks_repository.py` and `test_tracks_migration.py`
(full run 2026-11-03: 597 passed, 15 skipped). The `0008` downgrade drops the two derived columns without
refusing (the frontend can recompute them). Render has **not** received these migrations (deployment pending).

### 3.5 Heap, index and TOAST at the incident

`external_telemetry` 845 MB = heap 778 MB + indexes 66 MB + TOAST 0 (payload JSONB stayed inline).
~99.2 % of rows had `run_id IS NULL`.

## Data Flow

Ingestion writes: `hello` → `external_session`; `run_started` → `run` (+ optional `setup`);
`lap` event → `lap`; sub-sampled `telemetry` → `external_telemetry`; `run_finished` → `run.closed_at`,
`closure_status`, `context_snapshot.summary`.

## Design Decisions & Trade-offs

- **JSONB `payload` per frame.** Flexible with the simulator contract; larger than a typed column set.
- **Primary key `(session_id, seq)`.** Makes replays idempotent (`ON CONFLICT DO NOTHING`).
- **Alembic downgrade refuses to drop external data** unless exported (`0005`).
- **Align or accept?** Recommended: keep the live shape (single PK named `uq_external_sample`) and
  align the model/migration to it, or recreate with two indexes; decide explicitly (tasks 4).
