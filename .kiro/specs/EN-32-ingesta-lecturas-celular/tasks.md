# Implementation Plan — EN-32 · Recibir las lecturas del celular en la API (ingesta) (DRAFT)

## Overview

Status (2026-11-04): the ingestion channel of EN-32 is **implemented and merged into `main`**. The phone
sends readings by REST (`POST /api/measurements/{id}/readings`, EN-33, PR #8). Merged since: the ingestion
contract in `docs/CONTRACT.md`, the response-time test (batch of 25 and of 1000 readings) and the support
script `scripts/check_phone_readings.py` (PR #15); the script option to find a measurement by the phone code
(`--device`, `--list`, `--latest`, PR #16); and `mount` (hand or robot) on every reading returned by the API
(PR #17, criterion 2). Verification: full suite against the local PostgreSQL = 910 passed, 15 skipped;
`ruff check` clean. Still `[ ]`: the PO decision on whether REST is accepted as the channel or a WebSocket
"medicion" message is also wanted, the guided check with a real phone (7.6, 7.7), the configurable reading
cap, retention and idle close, and the live relay to the console (backend point B1 and console point F2).
`docs/CONTRACT.md` and `docs/MEDICIONES.md` describe what is already built.

Order: decisions, prerequisite, backend, phone page, console. No agent commits or pushes; the user
commits one point at a time. No task touches Render or the production database.

## Tasks

- [ ] E. EN-32 proper (ingestion), on top of PR #8 of the teammate
  - [x] E.1 Verify the five criteria against `feat/EN-33-mediciones-celular` (done 2026-11-03: see `requirements.md`)
  - [x] E.2 Document the ingestion in `docs/CONTRACT.md` (routes, fields, units, discard reasons, errors) _criterion 5_ (done 2026-11-04, merged in PR #15, section «Mediciones del celular (ingesta)»; fields checked against the generated OpenAPI and against the API behaviour)
  - [x] E.3 Test that a batch of 25 and a batch of 1000 readings is answered in under 1 s _criterion 4_ (done 2026-11-04: `tests/integration/rest/measurements/test_ingest_latency.py`, local PostgreSQL; measured batch of 25: 27–56 ms, batch of 1000: 449–696 ms over 3 runs of 5; merged in PR #15)
  - [x] E.4a Criterion 2: every reading returned by the API carries the `mount` of its measurement, inherited from it (done 2026-11-04, merged in PR #17; no migration, `ReadingIn` unchanged)
  - [ ] E.4b PO decision: REST as the channel (criterion 1), or also a WebSocket "medicion" message
  - [ ] E.5 Optional: persist discard counts per measurement _criterion 3_
- [ ] 0. Decisions (owner / PO)
  - [ ] 0.1 Indoor or outdoor track (GPS yes or no) _Requirements: 2.6, 4.2, 4.3, 7.5_
  - [ ] 0.2 Live view: speed and heading only, or path over the tracer plan _Requirements: 6.3, 6.4_
  - [ ] 0.3 Estimated laps as diagnostic only or compared with the timer _Requirements: 4.5, 4.6_
  - [ ] 0.4 Retention age and idle time _Requirements: 3.5, 5.3_
- [x] 1. Prerequisite: renumber the EN-33 migration to `0009` after `0008_track_metrics` (done and merged: PR #8, `main` `cdbffbe`, 2026-11-03)
- [ ] 2. Backend (point B1)
  - [ ] 2.1 Domain: `source='phone'` without robot or run; `abandoned` state _Requirements: 3.1, 3.2, 3.5_
  - [ ] 2.2 Guard: simulator schemas reject `source:"phone"`; no `run`, `lap` or `external_telemetry` rows _Requirements: 3.2, 3.3, 8.1_
  - [ ] 2.3 Distance, speed, maximum lateral acceleration and path, with known-figure tests _Requirements: 4.2, 4.3, 4.4_
  - [ ] 2.4 Estimated laps and lap times from the phone clock _Requirements: 4.5, 4.6_
  - [ ] 2.5 Quality: gaps, GPS accuracy filter, uncalibrated bias _Requirements: 4.7, 4.8_
  - [ ] 2.6 Make the existing cap (`READINGS_MAX = 200_000`, 409 `measurement_too_many_readings`) configurable, lower it to 20,000 and add `readings_capped` (decide 409 vs silent cap with the PO) _Requirements: 5.1, 5.2_
  - [ ] 2.7 Retention runbook or job; idle close _Requirements: 3.5, 5.3_
  - [ ] 2.8 Relay summary to consoles after each accepted batch _Requirements: 6.1_
  - [ ] 2.9 OpenAPI and `docs/CONTRACT.md` for the new fields and the `phone` WebSocket type _Requirements: 3.1, 6.1_
  - [ ] 2.10 Full suite against local PostgreSQL, ruff clean, specs updated _Requirements: 5.4, 8.1_
- [ ] 3. Phone page (point F1) — the page already exists in PR #6 (`feature/SP-06-medicion-celular`, `public/celular/index.html`, by a teammate); this point reviews and extends it, agreed with its author
  - [ ] 3.0 Prerequisite: merge PR #8 (EN-33) first, then PR #6; confirm with the author who edits the file
  - [ ] 3.1 Verify what the page already covers: sensors, iOS permission, HTTPS, Wake Lock, batches every 0.5 s with `seq` and resend, gyro calibration _Requirements: 1.1 to 1.4, 2.1 to 2.5_ (review only, mark done with evidence)
  - [ ] 3.2 Add indoor mode: skip `watchPosition`, send `motion` only _Requirements: 2.6, 7.5_
  - [ ] 3.3 Replace `--dim` text colour with `--mid` (contrast 3.39:1 fails) _Requirements: 6.6_
  - [ ] 3.4 Keep the token in memory only, or document why `localStorage` stays _Requirements: 7.2_
  - [ ] 3.5 Warning when the page goes to the background _Requirements: 2.5_
  - [ ] 3.6 Decide the car-speed method for a car without PWM (replace the `/car` calibration with average speed from the known track length) _Requirements: 4.3_
  - [ ] 3.7 jsdom tests for batching, resend without duplicates, calibration and indoor mode; real-device test stays manual (5.1)
- [ ] 4. Console (point F2)
  - [ ] 4.1 "Celular" card: connection, calibration, rate, discards, GPS accuracy _Requirements: 6.2, 6.5_
  - [ ] 4.2 Live speed, heading, lateral acceleration and estimated path _Requirements: 6.3_
  - [ ] 4.3 Hide car commands for the phone source; label sources _Requirements: 3.4, 8.2_
  - [ ] 4.4 Optional path over the tracer plan _Requirements: 6.4_
- [ ] 5. Validation
  - [ ] 5.1 Manual test with a real phone on the car, outdoor and indoor (guided check in task 7)
  - [ ] 5.2 Visual validation by the PO with screenshots (desktop and 360 px)
  - [ ] 5.3 Coordinate automated tests with the testing teammate (EN-37 to EN-41)
- [ ] 6. Pre-deployment (owner decides): check `alembic_version` in Render first; never run automated tests against Render
- [ ] 7. Real data from a real phone on Render _Requirements: 9, 10_
  - [x] 7.1 Frontend PRs #8 to #16 merged (one React phone page `celular.html`; old page removed); backend PRs #10 to #14 merged. Pending: Render deploys the frontend _10.1_
  - [x] 7.2 `CORS_ORIGINS` contains the frontend origin (verified 2026-11-04 with a preflight from the frontend origin: allow-origin matches) _10.2_
  - [x] 7.3 Production revision is `0009` (confirmed by the teammate's load report, 2026-11-04) _10.3_
  - [x] 7.4 `/celular` and `/celular/` both show the phone page and `/` shows the console on Render (verified 2026-11-04) _10.4_
  - [x] 7.5 (done 2026-11-04: `scripts/check_phone_readings.py` + README + unit tests, merged in PR #15; option `--device` / `--list` / `--latest` to find a measurement by the phone code, PR #16; run on the 19 field measurements) Backend agent: support script that reads the readings of a measurement and reports magnitude, accumulated angle, `seq` gaps and rate (no API code changed) _9.2 to 9.5_
  - [ ] 7.6 Owner: guided check with the real phone (rest, turn, shake, GPS, 60 s, network cut, latency) _9.2 to 9.6_ — guide: the phone test guide (guía de prueba con celular); sensors already activated on the deployed page (gyro 0.0 deg/s, accel 9.30 m/s2 at rest)
  - [ ] 7.7 Record date, device, browser and results in the study, section 13 _9.8_ — a teammate's 19 field measurements already recorded in section 13.1
  - [ ] 7.8 Optional: quality flag `no_motion_data` _9.7_
  - [ ] 7.9 Owner: delete the test measurements afterwards _10.6_

## Proposed commits (one per point)

- B1: `feat(measurements): celular como fuente unica de datos del coche [EN-32]`
- F1: `feat(celular): pagina del celular con calibracion y envio por lotes [EN-32]`
- F2: `feat(consola): muestra en vivo los datos del celular [EN-32]`
