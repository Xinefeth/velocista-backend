# Requirements Document — Data Model and Persistence

## Introduction

The backend persists to PostgreSQL through SQLAlchemy models and Alembic migrations `0001`–`0008`
(`0006`–`0008` were added by EN-28 and are applied only to the local development database so far).
The Render database `velocista` held 19 tables at revision `0005` (9,614 kB on 2026-10-28); the local
development database has 20 tables at revision `0008`. This spec records the model,
the migration chain, the real shape of the ingestion tables (including a difference with migration
`0005`) and the rules for evolving the schema.

## Glossary

- **Migración (Alembic)**: Script versionado que cambia el esquema (`migrations/versions/000N_*.py`).
- **Semilla (seed)**: Datos de referencia sembrados por la migración `0003`.
- **Sesión externa**: Fila de `external_session`; una conexión del simulador.
- **Telemetría externa**: Filas de `external_telemetry`; tramas `(session_id, seq)`.
- **Snapshot**: Copia JSON del contexto (controlador, perfil, config) guardada en `run`/`setup`.
- **Esquema real**: Estado observado en Render, no el declarado en el código.
- **JSONB**: Tipo PostgreSQL usado para `payload`, `hello`, `config`, `diagnostics`.

## Requirements

### Requirement 1: Esquema versionado

**User Story:** As a maintainer, I want every schema change in a migration, so that any database can be
rebuilt identically.

#### Acceptance Criteria

1. THE schema SHALL be created only by Alembic migrations in production; `create_all` SHALL be limited to tests and local bootstrap.
2. WHEN the container starts, THE service SHALL apply `alembic upgrade head`.
3. THE database SHALL record its revision in `alembic_version` (`0008` in local development; `0005` on Render at last check, until the EN-28 migrations are deployed).
4. WHEN a migration would destroy external acquisition history, THE downgrade SHALL refuse unless the data is exported first (`0005`).

### Requirement 2: Modelo de dominio persistido

**User Story:** As a developer, I want the main entities and relations to be explicit.

#### Acceptance Criteria

1. THE schema SHALL hold the catalog (`component_type`, `component`, `inventory`), the builder (`robot`, `slot`, `version`, `version_part`, `robot_config`), optimisation (`controller`, `setup`), rules (`profile`), runs (`run`, `lap`, `lap_sector`, `lap_segment`), tracks (`track`) and the log (`event`).
2. THE schema SHALL link `run` to `robot`, `version`, `setup` and `profile`, and `lap` to `run`.
3. THE reference data (component types, slots, controllers, profiles) SHALL be seeded by migration `0003` from `0003_reference_data.json`.
4. WHEN a run starts from the simulator, THE system SHALL store a snapshot of the controller, profile, hello and initial config in `run.context_snapshot`.

### Requirement 3: Ingesta externa

**User Story:** As an operator, I want external sessions and their telemetry stored with stable identity.

#### Acceptance Criteria

1. THE table `external_session` SHALL have `id` (`"<source>:<session_id>"`) as primary key and keep `hello`, `config`, `lost_samples` and `diagnostics`.
2. THE table `external_telemetry` SHALL have primary key `(session_id, seq)`, foreign keys to `external_session(id)` and `run(id)`, `t_ms`, `received_at` (UTC) and `payload` JSONB.
3. THE table `external_telemetry` SHALL have an index on `run_id`.
4. THE table `run` SHALL carry `external_session_id`, `external_run_id` and `closure_status`, unique per `(source, external_session_id, external_run_id)`, and `ingestion_id` unique (`0004`).
5. WHEN the simulator does not provide a measurement, THE columns `run.mode`, `run.line`, `run.battery_compensation`, `run.turbine_power_pct` and `lap.accumulated_error`, `lap.lost_lines`, `lap.battery_v` SHALL accept NULL.

### Requirement 4: Coherencia entre código y base real

**User Story:** As a maintainer, I want the model, the migration and the live database to agree.

#### Acceptance Criteria

1. THE model, the migration and the live `external_telemetry` SHOULD declare the same constraints and indexes.
2. IF they differ, THEN THE difference SHALL be documented and a decision recorded (align the code or the database).
3. WHEN a table is recreated outside Alembic, THE operator SHALL reproduce the real constraints and verify them.

### Requirement 5: Tamaño y retención

**User Story:** As an operator, I want the data volume to stay within the free plan.

#### Acceptance Criteria

1. THE only high-volume table SHALL be `external_telemetry`; every other table SHALL stay in the kB range at current usage.
2. WHEN a retention policy exists, THE purge SHALL be limited to `external_telemetry`.
3. THE persistence of telemetry SHALL be bounded as defined in `telemetry-ingestion`.

### Requirement 6: Pistas del trazador (EN-28)

**User Story:** As a pilot, I want my tracks stored in the database, so that they survive the browser.

#### Acceptance Criteria

1. THE table `track` SHALL have an identity primary key `id`, scalar columns for name, board sides, `closed`, start, `profile_id` and `length_cm`, JSONB columns `points` and `zones`, and `created_at`/`updated_at`, with `CHECK` constraints on the scalar limits and on the array lengths, and a foreign key `profile_id → profile(id)` with `ON DELETE RESTRICT`.
2. THE migration `0006` SHALL create `track`, and its downgrade SHALL refuse while rows exist; THE migration `0007` SHALL seed the profiles `lgr2026` and `libre` with a `rules.track` block (lengths in cm), and its downgrade SHALL delete only those two rows and refuse while a track references them.
3. THE per-element limits (coordinates, radius, zone size and name, `start.edge` against the point count) SHALL be enforced by the domain and the REST schemas, not by the database.
4. THE migration `0008` SHALL add the nullable columns `perimeter_cm` and `area_cm2` to `track` with `CHECK`s (perimeter 0..400000, area 0..4 × board area, both null when `closed` is false); existing rows SHALL keep NULL and its downgrade SHALL drop the columns.
