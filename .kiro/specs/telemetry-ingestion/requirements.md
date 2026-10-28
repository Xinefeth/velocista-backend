# Requirements Document — Telemetry Ingestion

## Introduction

The backend connects as a client to the external simulator (`velocista-sim`) and persists its
messages: sessions, runs, laps and telemetry frames. The simulator emits telemetry at about 50 Hz even
when no run is active. Storing every frame filled the free Render database: on 2026-10-27
`external_telemetry` held 994,636 rows (845 MB of an 854 MB database), 986,794 of them with no run, and
a `TRUNCATE` failed with `No space left on device`. The table was dropped and recreated (empty), and
the ingestion was already limited to active runs with sub-sampling and a per-run cap (commit
`a0fed7c`). This spec states those requirements and the pending retention work.

## Glossary

- **Ingesta**: Recepción y persistencia de mensajes del simulador (`infrastructure/integrations/velocista_sim`).
- **Sesión externa (external_session)**: Conexión del simulador; clave `"<source>:<session_id>"`.
- **Corrida activa**: Corrida (`run`) con `closed_at` nulo, creada por el evento `run_started`.
- **Trama (frame)**: Mensaje `telemetry` del simulador, con `seq` y `t_ms`.
- **Submuestreo (stride)**: Se guarda 1 de cada N tramas por `seq` (`SIM_TELEMETRY_STRIDE`).
- **Tope por corrida**: Máximo de filas de telemetría por corrida (`SIM_MAX_TELEMETRY_ROWS_PER_RUN`).
- **Retención**: Política de borrado de filas antiguas.
- **Runbook**: Procedimiento manual de operación para limpiar la base.

## Requirements

### Requirement 1: Guardar solo con corrida activa

**User Story:** As an operator, I want idle frames to be discarded, so that the database does not fill
up while the robot is stopped.

#### Acceptance Criteria

1. WHEN a `telemetry` frame arrives and there is no open run for it, THE Store SHALL NOT insert any row.
2. WHEN a run is closed (`closed_at` is set), THE Store SHALL stop inserting telemetry for it.
3. WHEN `SIM_STORE_TELEMETRY` is `false`, THE Store SHALL ignore every `telemetry` frame and SHALL keep persisting sessions, runs and laps.
4. THE Store SHALL process a batch in order, so that `run_started` creates the run before its first frames.

### Requirement 2: Submuestreo

**User Story:** As an operator, I want a bounded write rate, so that one run does not produce 50 rows
per second.

#### Acceptance Criteria

1. THE Store SHALL insert a frame only when `seq % SIM_TELEMETRY_STRIDE == 0`.
2. THE default stride SHALL be 5 (about 10 stored rows per second at 50 Hz) and SHALL be validated to the range 1–100.
3. WHEN a batch is retried, THE Store SHALL select the same frames, because the choice depends only on `seq`.

### Requirement 3: Tope por corrida

**User Story:** As an operator, I want a hard cap per run, so that a very long run cannot exhaust disk.

#### Acceptance Criteria

1. THE default cap SHALL be 20,000 rows per run (`SIM_MAX_TELEMETRY_ROWS_PER_RUN`).
2. WHEN a run reaches the cap, THE Store SHALL stop inserting telemetry for that run and SHALL keep recording its laps and events.
3. WHEN a run reaches the cap for the first time, THE Store SHALL log a warning and record `telemetry_capped` in `external_session.diagnostics`.
4. IF a batch fails, THEN THE Store SHALL restore its per-run counters before the batch is retried.
5. WHEN a frame is a duplicate (`session_id`, `seq`), THE Store SHALL ignore it without counting it.

### Requirement 4: Resistencia a la saturación

**User Story:** As an operator, I want persistence problems to be visible and not corrupt runs, so that
I can trust the history.

#### Acceptance Criteria

1. WHEN the in-memory queue is full, THE client SHALL drop new samples and count the loss (`dropped_samples`).
2. WHEN persistence is failing, THE client SHALL NOT start a new run.
3. WHEN the backend restarts, THE Store SHALL close runs left open as `interrupted` with reason `backend_restart`.

### Requirement 5: Retención y limpieza

**User Story:** As an operator, I want old telemetry to be removed on a schedule, so that the free-tier
disk never fills again.

#### Acceptance Criteria

1. WHERE no purge policy is defined, THE system SHALL NOT delete history automatically (current behaviour).
2. WHEN a retention policy exists, THE system SHALL delete telemetry older than the configured age without touching `run`, `lap` or `external_session` rows.
3. WHEN the purge runs, THE system SHALL log how many rows were deleted.
4. THE operations runbook SHALL describe how to inspect table sizes and how to clean `external_telemetry` manually, and SHALL be versioned in the repository.
5. WHILE the database disk is nearly full, THE runbook SHALL prefer `DROP`/recreate over `TRUNCATE`/`DELETE`, because `TRUNCATE` needs free space for new relation files.
