# Design Document — Telemetry Ingestion

## Introduction

`SimulatorClient` keeps one managed WebSocket connection to the simulator and puts messages on a
bounded in-memory queue. A writer drains it in ordered batches (up to 100) and `Store.write` persists
each batch in one transaction. This design records how telemetry is stored today, why, and what is
missing (retention).

## Goals & Non-Goals

**Goals**

- Store telemetry only for active runs, sub-sampled and capped.
- Keep sessions, runs and laps independent from the telemetry switch.
- Make saturation and caps observable (`diagnostics`, `dropped_samples`).

**Non-Goals**

- A durable journal or replay (the queue is process memory; see `docs/SIMULATOR.md`).
- Multi-instance coordination (one instance and one worker).
- Changing the simulator contract v1.

## Architecture Overview

```
velocista-sim ─WS (50 Hz)─▶ SimulatorClient.receive ─▶ contract.validate ─▶ enqueue (bounded queue 5000)
                                                                        │ writer: batches ≤100, ordered
                                                                        ▼
                                                      Store.write ─ one transaction per batch ─▶ PostgreSQL
 kinds → tables:
   hello      → external_session
   config     → external_session.config (+ run.context_snapshot)
   event      → run (run_started / run_finished), lap (lap), setup (effective config, if different)
   telemetry  → external_telemetry   only if: run open AND SIM_STORE_TELEMETRY AND seq % stride == 0 AND rows < cap
   diagnostic → external_session.diagnostics
   disconnect → external_session closed; open runs → interrupted
```

## Component Design

### 3.1 Settings (`infrastructure/config/settings.py`)

| Variable | Default | Range | Effect |
|---|---|---|---|
| `SIM_STORE_TELEMETRY` | `true` | bool | Off ⇒ `telemetry` frames ignored |
| `SIM_TELEMETRY_STRIDE` | `5` | 1–100 | Store 1 of N frames |
| `SIM_MAX_TELEMETRY_ROWS_PER_RUN` | `20000` | ≥1 | Per-run cap |
| `SIM_QUEUE_SIZE` | `5000` | 32–100000 | In-memory queue |

At 50 Hz and stride 5 a run stores about 10 rows/s and reaches the cap after about 2,000 s (~33 min).

### 3.2 `Store._store_telemetry` (`velocista_sim/persistence.py`)

1. No run, or run closed ⇒ return (idle frames are never stored).
2. `frame["seq"] % stride` ≠ 0 ⇒ return.
3. Count rows of the run (cached in `_rows`, else `SELECT count(*)`); at or above the cap ⇒ record
   `telemetry_capped` once, return.
4. `INSERT ... ON CONFLICT DO NOTHING RETURNING seq`; count only when a row was inserted.
5. `write()` snapshots `_rows` and restores it if the batch raises, so retries do not double count.

### 3.3 Tables written by an Arrancar/Detener cycle

`external_session` (reused if the session already exists), `run` (+1), `lap` (one per completed lap),
`external_telemetry` (sub-sampled), and `setup` only when the effective parameters differ from the
selected setup. Observed on Render on 2026-10-28 after a 6 s run: 52 telemetry rows (≈10 rows/s).

### 3.4 Retention (pending)

No scheduled purge exists. Options to decide: (a) delete telemetry of runs older than N days on app
start, (b) a manual runbook only, (c) periodic task. Whatever is chosen must not touch `run`/`lap`.

## Data Flow

Run lifecycle: `run_started` ⇒ `RunModel` (`closure_status=active`) ⇒ frames stored (stride, cap) ⇒
`lap` events ⇒ `run_finished` ⇒ `closed_at`, `closure_status=finished`, summary. Disconnect or restart ⇒
`interrupted`.

## Design Decisions & Trade-offs

- **Idle frames are dropped, not sub-sampled.** They carry no run and were 99.2 % of the stored rows
  (986,794 of 994,636) at the time of the incident. Trade-off: no idle history.
- **Sub-sample by `seq`.** Deterministic and retry-safe. Trade-off: the stored rate follows the source
  rate, so a different simulator rate changes the stored rate.
- **Cap per run, not global.** Protects against one runaway run; a global size limit does not exist.
- **Live console still sees every frame.** Only persistence is reduced (comment in `settings.py`).
- **Drop+recreate for emergency cleanup.** With the disk full, `TRUNCATE` failed because it needs to
  create new relation files; dropping the table freed 845 MB at commit.

## Incident reference (2026-10-27)

`external_telemetry` 994,636 rows / 845 MB; 986,794 without run. `TRUNCATE` ⇒ `DiskFull: could not
extend file ... No space left on device`. Resolution: export the 7,842 run rows to CSV (local), `DROP`
and `CREATE` the table with the same constraints (PK `uq_external_sample`, FKs, index
`ix_external_telemetry_run_id`). Database size 854 MB → 9,614 kB.
