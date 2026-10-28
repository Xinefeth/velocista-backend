# CONTRACT — Glosario ES→EN (backend ↔ frontend ↔ firmware)

- **Versión:** v1 (congelada)
- **Fecha:** 2026-10-15
- **Contrato WS:** 2.0
- **Estado:** fuente de verdad única. Backend (`velocista-backend`), frontend (`velocista-frontend`) y firmware deben usar EXACTAMENTE estos nombres.

## Reglas

- Todas las claves JSON en **inglés** y **snake_case**.
- Los valores de enum también en inglés (salvo ids técnicos que se listan abajo).
- Nombres de carpetas/archivos/símbolos del código: inglés. Comentarios: español.

---

## WebSocket — Envelope

| ES | EN |
|---|---|
| tipo | `type` |
| datos | `data` |
| seq | `seq` (igual) |
| ts | `ts` (igual) |
| origen (broadcast a consola) | `sender` |
| recibido_ms | `received_ms` |

`sender` del dispositivo = `robot` (canal `/ws/robot`), `timer` (canal `/ws/timer`), `api`.

## WebSocket — Tipos de mensaje (campo `type`)

| ES | EN | Emisor |
|---|---|---|
| manifiesto | `manifest` | robot |
| estado | `status` | robot / timer |
| senales | `signals` | robot |
| vuelta | `lap` | robot |
| cierre_vuelta | `lap_close` | api→robot |
| modo | `mode` | api→robot |
| linea | `line` | api→robot |
| evento | `event` | robot |
| sync / ack / start / stop / setup / calibrate | igual | varios |
| hola (timer) | `hello` | timer |
| corte (timer) | `crossing` | timer |
| rearmar (timer) | `rearm` | api→timer |
| enlace (alta/baja de dispositivo) | `link` | api |
| hola (consola, inicial) | `hello` | api |

Mensajes de origen `api` (los genera el backend entero: `type` + `data`):
- `hello` (al conectar consola) → `data { devices }`
- `link` (enlace) → `data { device (dispositivo), connected (conectado) }`
- `event` (evento) → `data { code, level, message, data }` con códigos en inglés (`invalid_message`, `missing_manifest`, `invalid_channel`, …)

## WebSocket — Anti-corruption layer (traducción en la frontera)

El gateway WS del nuevo backend actúa como **anti-corruption layer**: traduce a inglés
el `type` y los **valores de enum** de los mensajes que llegan del robot/timer antes de
reenviarlos a `/ws/console` y antes de persistir. Por tanto:

- El **firmware puede seguir en español** en estos campos; el backend normaliza.
- El **frontend ve siempre inglés** y puede migrar TODO el WS salvo las claves de canal.
- **Única dependencia del firmware que queda:** las **claves de canal** dentro de
  `data.channels` (ver abajo). Son vocabulario abierto declarado por el manifiesto, por eso
  no se traducen en la frontera; el resto (type + enums) es vocabulario cerrado y sí se mapea.

## WebSocket — Campos por mensaje

**Status (robot → api):** `state` (estado) · `calibrated` (calibrado) · `mode` · `line` · `controller` (controlador) · `loop_hz` (lazo_hz) · `rssi_dbm` · `channels` (canales)

**Signals (robot → api):** `t_ms` · `channels` (canales)

**Lap (robot → api):** `lap_id` (id_vuelta) · `internal_time_ms` (tiempo_interno_ms) · `accumulated_error` (error_acumulado) · `lines_lost` (lineas_perdidas) · `battery_v` (bateria_v)

**Event (robot → api):** `code` (codigo) · `level` (nivel) · `message` (mensaje) · `data` (datos)

**Setup (api → robot):** `controller` (controlador) · `parameters` (parametros) · `setup_id` (id_setup)

**Mode:** `mode` · **Line:** `color` · **LapClose:** `lap_id` (id_vuelta)

### Claves de canal (dentro de `channels`)

> ⚠️ **Única dependencia del firmware.** Las claves de `channels` las declara el
> **manifiesto del firmware** (vocabulario abierto); la anti-corruption layer NO las traduce.
> Pasarlas a inglés requiere tocar el **firmware**. El backend las reenvía tal cual.

| ES | EN |
|---|---|
| bateria_v | `battery_v` |
| regleta | `line_array` (16 lecturas de la regleta de línea) |

El frontend consume hoy solo estas dos (hardcodeadas en `domain/strip.ts` y `domain/robotStatus.ts`); las actualizará en lockstep con el firmware. La **lista completa de canales** la define el firmware; cuando exista, se añade aquí.

---

## Enums (valores)

| Campo | ES | EN |
|---|---|---|
| mode | prueba / competencia | `test` / `competition` |
| line / color | negra / blanca | `black` / `white` |
| level (nivel) | info / aviso / error | `info` / `warning` / `error` |
| time_source (fuente_tiempo) | meta / telemetria | `finish` / `telemetry` |
| source (fuente) | sim / robot | igual |
| version status (estado) | Actual / Anterior / Descartada / Concepto / Borrador | `current` / `previous` / `discarded` / `concept` / `draft` |
| gate (barrera, timer) | ok / bloqueada / sin_senal | `ok` / `blocked` / `no_signal` |
| robot type (tipo) | velocista / minisumo | `racer` / `minisumo` |
| actuator type | motor_dc / servo / turbina / led / otro | … / `other` |
| start (arranque) | comando / modulo_arranque | `command` / `start_module` |
| component field type | n / t | `number` / `text` |
| aggregation (agregacion) | suma_por_cantidad / por_componente | `sum_by_quantity` / `per_component` |
| operation (operacion) | producto | `product` |

---

## REST

**GET /api/health:** `api` · `database` (base_de_datos) · `environment` (entorno) · `devices` (dispositivos). Llaves de `devices`: `{robot, timer}`.

**Run — GET /api/runs (CorridaSalida):**
`id` · `number` (numero) · `robot_id` · `version_id` · `setup_id` · `profile_id` (perfil_id) · `controller_id` (controlador_id) · `parameters` (parametros) · `date` (fecha) · `source` (fuente) · `mode` (modo) · `line` (linea) · `battery_compensation` (compensa_bateria) · `turbine_power_pct` (potencia_turbina_pct) · `time_s` (tiempo_s) · `finished` (termino) · `accumulated_error` (error_acumulado) · `battery_v` (bateria_v) · `sectors_s` (sectores_s) · `time_source` (fuente_tiempo) · `note` (nota) · `j` (función objetivo; se mantiene `j`)

**Lap (VueltaSalida)** *(aún no servido por REST; nombres reservados):*
`id` · `run_id` (corrida_id) · `number` (numero) · `time_s` (tiempo_s) · `duration_s` (duracion_s) · `internal_time_ms` (tiempo_interno_ms) · `accumulated_error` (error_acumulado) · `lines_lost` (lineas_perdidas) · `battery_v` (bateria_v) · `finished` (termino) · `time_source` (fuente_tiempo) · `reason` (motivo) · `sectors_s` (sectores_s) · `segments` (segmentos)
**Segment:** `type` (tipo) · `duration_s` (duracion_s) · `angle_degrees` (angulo_grados) · `accumulated_error` (error_acumulado)

**Robot (RobotApi):**
`id` · `name` (nombre) · `short_code` (codigo_corto) · `type` (tipo: `racer`/`minisumo`) · `firmware` · `current_version_id` (version_actual_id) · `archived` (archivado)

**RobotVersion:**
`id` · `robot_id` · `label` (etiqueta) · `date` (fecha) · `note` (nota) · `status` (estado) · `parts` (piezas) `{ component_id (componente_id), quantity (cantidad) }`

**Component (catálogo):**
`id` · `type_id` (tipo_id) · `name` (nombre) · `price` (precio) · `mass_g` (masa_g) · `store` (tienda) · `current_a` (consumo_a) · `specs` (especificaciones) · `stock` · `archived` (archivado)

**ComponentType (tipo de componente):**
`name` (nombre) · `color` · `fields` (campos) · `capabilities` (capacidades)
- **Field:** `key` (clave) · `label` (etiqueta) · `type` (tipo: `number`/`text`) · `unit` (unidad) · `required` (obligatorio)
- **Capability:** `key` (clave) · `unit` (unidad) · `aggregation` (agregacion) · `field` (campo) · `fields` (campos) · `operation` (operacion) · `min` · `max`

**Track (pista del trazador, EN-28) — `/api/tracks`:** todas las distancias en **centímetros**.
`id` (entero) · `name` · `board` `{ width_cm, height_cm }` · `closed` · `points` `{ x, y, radius, gap }` · `zones` `{ x, y, width, height, name }` · `start` `{ edge, t }` (`edge` = índice de tramo; `t` = fracción 0..1) · `profile_id` (nullable) · `length_cm` (lo calcula el frontend; el backend lo guarda tal cual) · `created_at` · `updated_at`.
- Rutas: `GET /api/tracks` (paginada) · `POST /api/tracks` (crea; también importa un JSON exportado e ignora `id`, `created_at`, `updated_at`) · `GET|PUT|DELETE /api/tracks/{id}` · `GET /api/tracks/{id}/export` (JSON con `Content-Disposition: attachment`).
- Límites *(supuestos pendientes del PO)*: nombre 1–80; puntos 2–500; zonas 0–100; tablero 50–2000 cm por lado; radio 0–200 cm; coordenadas ±10000 cm (pueden quedar fuera del tablero); zona `width`/`height` > 0 y ≤ 2000, nombre ≤ 80; `length_cm` > 0 y ≤ 100000; `start.edge` 0..(puntos−1) si `closed`, 0..(puntos−2) si abierta; `closed` exige ≥ 3 puntos.
- Errores: parseo de Pydantic → 422 con `detail` **lista** `[{type, loc, msg, input, ctx?}]`; regla de dominio → 422 con `detail` **objeto** `{reason, detail}`. Razones: `track_not_found` (404), `track_profile_unknown`, `track_name_invalid`, `track_points_count`, `track_zones_count`, `track_board_size`, `track_radius_range`, `track_coordinate_range`, `track_zone_size`, `track_zone_name`, `track_not_finite`, `track_length_invalid`, `track_start_invalid`, `track_closed_needs_three_points`.
- Reglas de pista en perfiles: `GET /api/profiles` devuelve `rules.track` cuando existe (`lgr2026`, `libre`): `line_width_mm` (mm), `gap_length_cm` (cm) y 13 reglas `{ enabled, value }`: `radius_min`, `angle_min` (grados), `no_sharp`, `separation_min`, `margin`, `zone_distance`, `closed`, `length_min`, `length_max`, `straight_min`, `straight_max`, `cross_max`, `gap_max` (todas las longitudes en cm). Los perfiles `club`, `mr4a`, `mr4s`, `mr4m` no traen bloque `track`.

### Query params (ya en inglés)

`limit` (renombrar `limite` donde quede) · `offset` · `q` · `type_id` · `robot_id` · `version_id` · `controller_id` · `source`

### Paginación

`items` · `total` · `limit` (limite) · `offset`

---

## Pendientes / futuro

- **Servicio de ingesta** aparte enviará datos más adelante → previsto como *adapter* en `infrastructure/`; NO se implementa en v1.
- **Frontend:** refactor para leer claves de canal desde el `manifest` en vez de hardcodearlas (post-v1).
- **Firmware:** gracias a la anti-corruption layer, para v1 **solo** necesita emitir las **claves de canal** en inglés (`battery_v`, `line_array`); `type` y enums los normaliza el backend. El renombrado del firmware deja de bloquear la migración del frontend.
