# Requirements Document — EN-32 · Recibir las lecturas del celular en la API (ingesta)

Extended scope: the phone on the car as sole data source (see the Introduction).

## Introduction

The car has no sensors or electronics. A smartphone fixed on it is the only data source: gyroscope,
accelerometer and optionally GPS. The phone sends raw readings to the backend as a `measurement`
(method `car`, mounting `robot`, source `phone`) defined by EN-32/EN-33 (`docs/MEDICIONES.md`). The
backend computes heading, path, distance, speed, lateral force and estimated laps, and relays the data
live to the console. The phone does not use the wire contract of `velocista-sim`, does not create a `run`
(the `run` table requires a robot, setup and profile the car does not have) and does not receive commands.
The simulator stays as an alternative source for development.

DRAFT: depends on the open questions of the study in `study.md` (section 9) and on PR #8 (EN-33, merged)
being rebased first (its migration `0008_measurements` collides with `0008_track_metrics`).


## EN-32 acceptance criteria against the existing implementation

Source: backlog item EN-32 (Habilitador): "Canal por el que el celular envía GPS, giro y aceleración a la API,
ya sea encima del carro o en la mano de una persona." Verified on 2026-11-03 against branch
`feat/EN-33-mediciones-celular` (PR #8, head `123056d`, by a teammate).

| # | Criterion of EN-32 | State in the teammate's branch | Verdict |
|---|---|---|---|
| 1 | New message type "medicion" in the contract (lat, lon, accuracy, gyro, acceleration, time, sequence number) | Implemented as REST, not as a WebSocket message: `POST /api/measurements/{id}/readings` with `ReadingIn` (`seq`, `t_ms`, `kind` = `motion` / `gps` / `corner`, `gyro_z_dps`, `accel`, `step`, `pwm`, `lat`, `lon`, `accuracy_m`). GPS and motion travel in separate readings | **Partly**: all the fields exist; the channel is REST, not a WS type |
| 2 | Each reading says whether the phone is in hand or on the robot | `mount` (`hand` / `robot`) belongs to the **measurement**; since 2026-11-04 every reading returned by `GET /api/measurements/{id}/readings` also carries `mount`, inherited from its measurement (no migration; the phone does not send it and a `mount` inside a reading is ignored); `method=car` forces `mount=robot` | **Met** (merged in PR #17) |
| 3 | The gateway validates each message; invalid ones are discarded and logged | `reading_problem()` returns a reason (`gps_out_of_range`, `accel_out_of_range`, ...); invalid readings are discarded, the rest of the batch is stored, the response reports `discarded` by reason and `log.warning` records it | **Met** (logged in the application log only, not stored in the database) |
| 4 | Readings reach the backend in under 1 s | `docs/MEDICIONES.md` reports about 31 ms for a batch of 25 (max 38 ms); no automated test asserts it; end-to-end time also depends on the phone network | **Measured by hand, not tested** |
| 5 | Documented in Swagger and in the contract | Swagger: yes (OpenAPI descriptions and examples). `docs/CONTRACT.md` has **no** mention of measurements; `docs/MEDICIONES.md` documents it | **Partly**: Swagger yes, contract no |

Also verified: authentication on every route, `seq` unique per measurement (resend does not duplicate),
batch limit 1000, measurement limit `READINGS_MAX = 200_000` (409 `measurement_too_many_readings`), and a
backend suite of 693 passed against local PostgreSQL after the migration was renumbered to `0009`.

What EN-32 still needs: document the ingestion in `docs/CONTRACT.md`; a test that asserts the response time
of a batch; PO decision on row 1 (REST instead of a WS message type). Row 2 (mount on each reading) is done on output.

## Glossary

- **Medición (measurement)**: Sesión de lecturas del celular; método `car`, montaje `robot`, fuente `phone`.
- **Lectura (reading)**: Muestra con `seq`, `t_ms` y `kind` (`motion`, `gps`, `corner`).
- **Sesgo del giroscopio (gyro bias)**: Valor medio del giroscopio con el coche quieto.
- **Vuelta estimada (estimated lap)**: Vuelta detectada por el cierre de la trayectoria o por 360 ° de rumbo; es un diagnóstico, no el tiempo oficial.
- **Tope (cap)**: Máximo de lecturas guardadas por medición.
- **Retransmisión (relay)**: Reenvío de cada lote aceptado a las consolas por el WebSocket existente.
- **Página del celular (phone page)**: Página web servida por HTTPS que lee los sensores y envía lotes.

## Requirements

### Requirement 1: Montaje y calibración

**User Story:** As a pilot, I want to calibrate the phone while the car is still, so that gyroscope bias does not distort the heading.

#### Acceptance Criteria

1. WHEN the pilot starts a calibration, THE Phone page SHALL collect at least 30 `motion` readings while the car is still.
2. WHEN the standard deviation of the gyroscope exceeds 1 °/s during calibration, THE Backend SHALL reject it with a message saying the phone moved.
3. WHEN a calibration is accepted, THE Backend SHALL store the bias in `sensor_calibration` and SHALL copy it into each new measurement.
4. IF no calibration exists for the phone, THEN THE Phone page SHALL warn before starting and SHALL allow continuing.

### Requirement 2: Envío de lecturas

**User Story:** As a pilot, I want the phone to send readings reliably, so that a network cut does not lose or duplicate data.

#### Acceptance Criteria

1. THE Phone page SHALL send readings in batches every 0.5 s, with at most 1000 readings per batch.
2. WHEN a batch fails, THE Phone page SHALL resend it unchanged, and THE Backend SHALL ignore readings already stored for the same measurement and `seq`.
3. WHEN a reading is invalid, THE Backend SHALL discard it, SHALL accept the rest of the batch and SHALL report the discard reasons.
4. THE Phone page SHALL ask for the motion permission after a user tap on iOS and SHALL work only over HTTPS.
5. WHILE a measurement is running, THE Phone page SHALL keep the screen on (Screen Wake Lock) and SHALL warn if the page goes to the background.
6. WHERE GPS is not allowed or the pilot chose indoor mode, THE Phone page SHALL send `motion` readings only.

### Requirement 3: Medición independiente

**User Story:** As an owner, I want the phone to work without a robot, so that a car with no electronics can be measured.

#### Acceptance Criteria

1. THE Backend SHALL accept a `car` measurement with source `phone` without a robot, setup, profile or `run`.
2. THE Backend SHALL NOT create `run`, `lap` or `external_telemetry` rows for a phone measurement.
3. THE Backend SHALL NOT accept `source: "phone"` in the `velocista-sim` wire schemas, which stay unchanged.
4. THE Backend SHALL NOT offer commands to the car (start, stop, setup); the console SHALL NOT show them for a phone source.
5. IF a measurement stays open without readings for more than the configured idle time, THEN THE Backend SHALL close it as `abandoned`.

### Requirement 4: Cálculo

**User Story:** As a pilot, I want speed, path and laps computed from the phone, so that I know how the car moved.

#### Acceptance Criteria

1. THE Backend SHALL compute heading by integrating the gyroscope minus the stored bias with the trapezoid rule.
2. WHERE GPS readings exist, THE Backend SHALL compute distance and path from them and SHALL use `speed` when the phone provides it.
3. WHERE only `motion` readings exist, THE Backend SHALL compute an inertial estimate and SHALL mark the result `estimate: true` with the reason `no_gps`.
4. THE Backend SHALL compute maximum and mean speed, distance, maximum lateral acceleration and the path.
5. THE Backend SHALL detect estimated laps when the path returns to the start area or the accumulated heading completes 360 ° ± 45 °, and SHALL report lap times from the phone clock.
6. THE Backend SHALL mark laps as estimates and SHALL NOT replace the lap times of the timer (`/ws/timer`).
7. IF the readings contain gaps longer than 2 s, THEN THE Backend SHALL lower the quality of the result and SHALL report the gap count.
8. THE Backend SHALL discard GPS readings with reported accuracy worse than 25 m or than 3 times the median.

### Requirement 5: Almacenamiento acotado

**User Story:** As an operator, I want a hard storage limit, so that phone data never fills the free database again.

#### Acceptance Criteria

1. THE Backend SHALL store at most 20,000 readings per measurement (configurable) and SHALL record `readings_capped` when it is reached.
2. THE Backend SHALL reject a batch above 1000 readings with 422 and SHALL NOT store part of it.
3. WHERE a retention policy exists, THE Backend SHALL delete readings older than the configured age without deleting `measurement` rows or their results.
4. THE Backend SHALL NOT write to the production database from tests (local database only).

### Requirement 6: Vista en vivo

**User Story:** As a pilot, I want to see the car data live, so that I check the phone and the run while it happens.

#### Acceptance Criteria

1. WHEN the Backend accepts a batch, THE Backend SHALL relay a summary to the consoles as `type: "phone"` over the existing WebSocket, one message per batch.
2. THE Console SHALL show the phone state: connected, calibrated, readings per second, discarded count and GPS accuracy.
3. WHILE a measurement runs, THE Console SHALL show speed, heading, lateral acceleration and the estimated path.
4. WHERE a track from the tracer is selected, THE Console SHALL draw the estimated path over its plan.
5. WHEN the phone stops sending for more than 3 s, THE Console SHALL show the source as disconnected.
6. THE Console SHALL use the current palette and SHALL NOT use `--dim` for text.

### Requirement 7: Seguridad y privacidad

**User Story:** As an owner, I want only authorised phones to send data and location to stay private.

#### Acceptance Criteria

1. THE Backend SHALL require authentication on every measurement endpoint, with the same mechanism as the other REST routes.
2. THE Phone page SHALL keep the token only in memory.
3. THE Backend SHALL store no personal data other than the device identifier and the readings (RNF-06).
4. WHERE GPS is sent, THE Backend SHALL treat it as location data, SHALL NOT expose it to other users and SHALL delete it with the measurement.
5. THE Phone page SHALL make GPS optional and off by default in indoor mode.

### Requirement 8: Coexistencia con el simulador

**User Story:** As a developer, I want the simulator to keep working, so that I can develop without hardware.

#### Acceptance Criteria

1. THE Backend SHALL keep the simulator ingestion unchanged (`SIM_ENABLED`, wire contract, limits of ADR-005).
2. WHERE a simulator and a phone are both active, THE Console SHALL label each source.

### Requirement 9: Datos reales del celular

**User Story:** As a pilot, I want to be sure that the readings come from the real sensors of a real phone, so that the measurements can be trusted.

#### Acceptance Criteria

1. THE Backend SHALL store every reading of a `phone` measurement exactly as the phone sent it, without generating, completing or smoothing values.
2. WHEN a phone is at rest on a table for 10 s, THE readings SHALL show an acceleration magnitude of about 9.8 m/s² and a rotation rate near 0 °/s.
3. WHEN the phone turns 360° in place, THE integral of `gyro_z_dps` over time SHALL be within 10 % of 360°.
4. WHEN the phone is carried outdoors, THE `lat` and `lon` SHALL change along the real path and `accuracy_m` SHALL be within the range reported by the device.
5. WHEN a measurement lasts 60 s, THE `seq` values SHALL have no gaps after resends and THE `t_ms` values SHALL be increasing.
6. WHEN the network is cut for 10 s and restored, THE Phone page SHALL resend the pending batches and THE Backend SHALL store them without duplicates or losses.
7. IF all motion readings of a measurement are null, constant or all zero (typical of a desktop browser), THEN THE Backend SHALL mark the measurement quality as `no_motion_data` and THE Console SHALL show it.
8. THE real-phone check SHALL be recorded (date, device, browser, result of each step) in the study, section 13.

### Requirement 10: Despliegue en Render

**User Story:** As the owner, I want the phone to use the page and the API already deployed on Render, so that no tunnel is needed.

#### Acceptance Criteria

1. THE page SHALL be served by the Render static site at `/celular/` and SHALL work over HTTPS.
2. THE Backend on Render SHALL list the exact frontend origin in `CORS_ORIGINS`.
3. THE production database SHALL be at the Alembic revision that includes the measurements tables (`0009`) before the first phone measurement.
4. WHEN the rewrite `/*` to `/index.html` is active, THE path `/celular/` SHALL still show the phone page and not the console.
5. THE phone SHALL log in with a user account typed by the pilot; no credential SHALL be stored in files, in the chat or in the repository.
6. WHILE real-phone tests run on Render, THE tests SHALL be short and THE measurements created for them SHALL be deleted afterwards, because the free database is small.
7. Render deployment and changes of its variables are decided by the owner, never by an agent.

## Existing work

The phone page already exists in PR #6 of the frontend (`feature/SP-06-medicion-celular`, file
`public/celular/index.html`, open, by a teammate). Requirements 1, 2 and 7 describe behaviour that page
partly covers; points that need review are listed in `design.md` section 5 and `tasks.md` task 3.
Requirement 4.3 (inertial estimate without GPS) still needs the average-speed method for a car without
PWM (open question 6).

## Open questions

1. Indoor or outdoor track (decides whether GPS is used).
2. Live view: only speed and heading, or also the path drawn over the tracer plan (Requirement 6.4).
3. Estimated laps accepted as diagnostic only, or compared with the timer.
4. Retention age for raw readings.
5. Idle time before a measurement is closed as `abandoned`.
6. Speed of a car without PWM: average speed from the known track length divided by lap time (shape and angles only, scale comes from the plan), or GPS speed outdoors.
7. Who edits `public/celular/index.html`: the author of PR #6 or the agents of this plan.
8. Does the real-phone check (Requirement 9) run on Render or on a local HTTPS tunnel first? Recommended: Render, short runs, then delete the data.
9. Is the `no_motion_data` quality flag (Requirement 9.7) wanted in EN-32, or left for a later item?
