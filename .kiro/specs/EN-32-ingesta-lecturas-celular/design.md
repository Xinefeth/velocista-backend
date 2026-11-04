# Design Document — EN-32 · Recibir las lecturas del celular en la API (ingesta)

DRAFT. Builds on EN-32/EN-33/EN-34/EN-35 (`docs/MEDICIONES.md` in branch `feat/EN-33-mediciones-celular`).
Clean Architecture as in the rest of the backend (domain ← application ← infrastructure/interface).

## 0. EN-32 on top of the teammate's branch

EN-32 is **already implemented** in `feat/EN-33-mediciones-celular` (PR #8). The work left for EN-32 is small:

| Item | Change | Where |
|---|---|---|
| Contract | Add a "Phone measurements" section to `docs/CONTRACT.md`: routes, `ReadingIn` fields and units (`gyro_z_dps` in °/s, `accel` in m/s², `t_ms` in ms, `accuracy_m` in m), `kind` values, mount, discard reasons, 409/422 errors | `docs/CONTRACT.md` |
| Latency | Test that a batch of 25 and a batch of 1000 readings is answered in under 1 s against local PostgreSQL | `tests/integration/rest/measurements/` |
| Message type | PO decides: REST is the contract of EN-32 (recommended, it already tolerates network cuts), or an additional WS message. The live relay of this spec is a separate WS type `phone` for the consoles | PO |
| Mount per reading | DONE 2026-11-04: `mount` stays on the measurement and is echoed in each reading output (inherited, no migration, `ReadingIn` unchanged) | `ReadingOut` |
| Discard log | Optional: keep discard counts in the measurement (`result` or a column) because Render logs are not durable | EN-33 |

Everything below extends EN-32 (phone as the sole data source) and is outside the EN-32 backlog item.

## 1. Decision

The **measurement** is the main entity; no `run` is created. The phone sends REST batches (EN-32) and the
backend relays each accepted batch to the consoles. The simulator contract and the `run` table are not
touched.

Alternatives discarded:
- Link the measurement to a `run`: `run` requires robot, version, setup and profile, which a car without
  electronics does not have, and `source` is limited to `sim` or `robot`.
- WebSocket from the phone as a new ingest path: it rebuilds the retry and dedupe that EN-32 already has.
- Imitate `velocista-sim`: its schema demands line sensors and motors the phone does not have.

## 2. Flow

```
Phone page (HTTPS)                 Backend (FastAPI)                          PostgreSQL
──────────────────                 ─────────────────                          ──────────
calibrate (car still) ───────────► POST /api/calibrations/{phone}/gyro ─────► sensor_calibration
start ───────────────────────────► POST /api/measurements                     measurement
                                     {method:car, mounting:robot, source:phone}
every 0.5 s ─────────────────────► POST /api/measurements/{id}/readings ────► measurement_reading
                                     └─ relay "phone" summary ─► consoles (WS /ws/console)
finish ──────────────────────────► POST /api/measurements/{id}/finish ─────► measurement.result
console ◄────────────────────────  GET /api/measurements/{id}
```

## 3. Changes on top of EN-33

| Area | Change | Notes |
|---|---|---|
| Prerequisite | Rebase PR #8 and renumber `0008_measurements` to `0009` after `0008_track_metrics` | One Alembic head |
| Domain | `source='phone'` accepted without robot or run; `abandoned` state; estimated laps | Pure Python |
| Calculation | Distance, speed (GPS `speed` when present), maximum lateral acceleration, path, laps | Reuses heading, Kalman and Bowditch of EN-34/EN-35 |
| Cap | EN-33 already has `READINGS_MAX = 200_000` (fixed in code, about 1 h at 50 Hz); `use_cases.ingest` rejects the whole batch with 409 `measurement_too_many_readings`. Make it configurable and lower (20,000 ≈ 6.6 min at 50 Hz) and add `readings_capped` | ADR-005 criterion; decide 409 vs silent cap with the PO; a flag column needs migration 0010 |
| Retention | Purge job or runbook SQL for old `measurement_reading` | Keeps `measurement` rows |
| Idle close | Mark `abandoned` after the configured idle time | Avoids open measurements forever |
| Live relay | After commit, `hub.broadcast("phone", "reading_batch", summary)` | One message per batch; summary only (last point, speed, heading, counters), never the raw batch |
| Console | WebSocket handler for `type:"phone"`; "Celular" card; optional path over the tracer plan | Anti-corruption mapping like the other channels |

The relay summary is small on purpose: the console does not need every raw reading, and 50 Hz raw data to
several consoles would waste bandwidth.

## 4. Calculations

- **Heading:** gyroscope minus bias, trapezoid integration. Optional absolute heading from
  `DeviceOrientationEvent` to correct drift when the magnetometer is reliable.
- **Outdoor (GPS):** local plane `x = Δlon·R·cos(lat₀)`, `y = Δlat·R`; Kalman filter with RTS smoothing
  (SP-06) over positions weighted by 1/accuracy²; speed from `coords.speed` when available.
- **Indoor (no GPS):** inertial estimate only. Acceleration integration drifts quickly, so speed uses
  zero-velocity checks (a still period resets speed) and the result carries `estimate:true, reason:no_gps`.
- **Laps:** a lap closes when the path returns to the start area or the accumulated heading completes
  360 ° ± 45 °. Times come from the single phone clock. Always `estimate:true`, never written to `lap`.
- **Quality:** gaps above 2 s, low GPS accuracy and uncalibrated bias lower the quality flag.

## 5. Phone page

**Already exists (verified 2026-11-03):** PR #6 of the frontend, branch `feature/SP-06-medicion-celular`
(open, not merged, author: a teammate), adds one file `public/celular/index.html` (1208 lines, plain HTML and
JavaScript, no React). It is served by the static site of the frontend at `/celular/`. It already does:
login (`/api/auth/login`), motion permission on iOS, GPS with `watchPosition`, Screen Wake Lock, gyro /
step / car calibration, measurement create / readings batches / finish, measurement history, GPS trials and
the precision model. It follows the console palette.

This design therefore **reviews and extends that page; it does not rewrite it**, and it must be agreed
with its author. Gaps against this spec:

| Gap | Needed change | Requirement |
|---|---|---|
| Uses `--dim` as a text colour (for example `.sub`), which fails contrast (3.39:1) | Replace with `--mid` | 6.6 |
| No indoor mode: it always asks for GPS | Add an indoor switch that skips `watchPosition` and sends `motion` only | 2.6, 7.5 |
| Token kept in `localStorage` (`store.set("token", ...)`) | Keep it in memory only, or document the decision | 7.2 |
| No live relay (backend and console not built yet) | Backend relay and console card, points B1 and F2 | 6.1 to 6.5 |
| Depends on the EN-33 endpoints (PR #8, open) | Merge order: PR #8, then PR #6 | prerequisite |
| Car calibration (`/api/calibrations/.../car`) assumes PWM, which a car without electronics lacks | Decide whether the average-speed method replaces it (see open question 6) | 4.3 |
| Plain HTML with no tests | Add jsdom tests for batching, resend, calibration and indoor mode | testing |

What stays as designed: `DeviceMotionEvent` (~60 Hz) downsampled to the agreed rate, permission after a tap
on iOS, HTTPS required, Screen Wake Lock with a warning on `visibilitychange`, local queue with `seq` and
unchanged resend, usable at 360 px.

## 6. Console

Card "Celular": connection, calibration, rate, discards, GPS accuracy. While measuring: speed, heading,
lateral acceleration and estimated path; optionally drawn over a tracer plan. Commands (start, stop, PID)
are hidden for the phone source. UI → application → domain, with no infrastructure imports from UI.

## 7. Security and privacy

Same JWT as the other REST routes; token in memory on the phone; GPS optional, off by default indoors,
deleted with the measurement; no other personal data (RNF-06).

## 8. Testing

- Domain: heading, distance, speed, lateral acceleration and laps with known figures (square lap,
  circular lap, drift, gaps, bad GPS accuracy).
- Repository (local PostgreSQL): cap, idempotent batches, `abandoned`, purge keeps `measurement`.
- API: batch resend does not duplicate; invalid reading discarded with reason; 422 above 1000; no `run`
  rows created; simulator schemas reject `source:"phone"`.
- WebSocket: relay sends one summary per batch and nothing to a disconnected console.
- Phone page: jsdom tests with simulated sensors; real-device test is a manual checklist.
- No test touches Render.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Indoor GPS is useless and inertial data drifts | Mark results as estimates; use zero-velocity checks; state it in the report |
| Phone vibration pollutes the accelerometer | Firm mount; smoothing; vibration noted in quality |
| Free database fills up again | Cap per measurement, retention, runbook |
| Browser throttles background pages | Wake Lock and visible warning |
| EN-33 migration clash | Rebase PR #8 first; renumber to 0009 |
| Render cold start delays the first batch | Resend logic; open the page before the run |
| Relay load on consoles | Summary only, one message per batch |

## 10. Real data and Render deployment

**Real data.** The automated test (batches of 25 and 1000) only proves that the API accepts and answers
fast. A manual guided check with a real phone proves that the data are real. Steps and expected values:

| Step | Action | Expected |
|---|---|---|
| Rest | phone still on a table, 10 s | acceleration magnitude about 9.8 m/s², `gyro_z_dps` about 0 |
| Turn | 360° in place | integral of `gyro_z_dps` about 360° (within 10 %) |
| Shake | 3 s | acceleration well above 9.8 |
| GPS | walk 20 m outdoors | `lat`/`lon` change along the path, plausible `accuracy_m` |
| Continuity | 60 s | no `seq` gaps, increasing `t_ms`, stable rate |
| Network cut | airplane mode 10 s | pending batches resent, no duplicates, no losses |
| Latency | compare phone time and reception time | under 1 s end to end |

A support script (outside the API code) reads `GET /api/measurements/{id}/readings` and computes the
magnitude, the accumulated angle, the `seq` gaps and the rate. Signs of fake or empty data: all zeros,
`null` motion values, constant `accuracy_m`, desktop user agent. Optional guard: quality flag
`no_motion_data` when every motion reading is null, constant or zero.

**Render.** The owner deploys the frontend (static site) and the backend on Render. The phone opens
`https://<frontend>/celular` (o `/celular/`). The page reads the backend address from `VITE_API_BASE_URL` (no `?api=`) and uses the console login (`AuthGate`, session token in `sessionStorage`).

| Need | Check |
|---|---|
| Page published | Done: React page `celular.html` (frontend PR #9) is the only phone page; the old `public/celular/index.html` was removed (frontend PR #16, merged 2026-11-04) |
| Rewrite does not hide the page | `render.yaml` has explicit rules `/celular/` and `/celular` before `/*`; Render's order of rules is not documented, so open both URLs after the deploy; if `/celular/` shows the console, fix the rule |
| CORS | `CORS_ORIGINS` has the exact frontend origin (page and API are different domains) |
| Schema | `SELECT version_num FROM alembic_version` returns `0009` |
| Login | the pilot types the password on the phone; nothing is stored in files or chat |
| Disk | short runs; delete the test measurements afterwards; retention still missing |

## 11. Rollout

1. Rebase and merge PR #8 (EN-33) with the migration renumbered.
2. Backend point: independent phone measurement, cap, retention, estimated laps, relay.
3. Phone page point: sensors, batches, calibration, Wake Lock.
4. Console point: card, live values, optional path over the plan.
5. Real-phone check (section 10) on Render, decided by the owner, with short runs; a local HTTPS tunnel is the alternative.
6. Render deployment is the owner's decision; check `alembic_version`, `CORS_ORIGINS` and the `/celular/` path first.
