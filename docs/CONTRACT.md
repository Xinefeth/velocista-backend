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
`id` (entero) · `name` · `board` `{ width_cm, height_cm }` · `closed` · `points` `{ x, y, radius, gap }` · `zones` `{ x, y, width, height, name }` · `start` `{ edge, t }` (`edge` = índice de tramo; `t` = fracción 0..1) · `profile_id` (nullable) · `length_cm` (lo calcula el frontend; el backend lo guarda tal cual) · `perimeter_cm` (cm; **nulo** si la pista es abierta; lo calcula el frontend) · `area_cm2` (**cm²**; **nulo** si la pista es abierta o la línea se cruza; fórmula de Gauss; lo calcula el frontend) · `created_at` · `updated_at`. `perimeter_cm` y `area_cm2` son opcionales y se guardan tal cual *(supuesto pendiente del PO)*.
- Rutas: `GET /api/tracks` (paginada) · `POST /api/tracks` (crea; también importa un JSON exportado e ignora `id`, `created_at`, `updated_at`) · `GET|PUT|DELETE /api/tracks/{id}` · `GET /api/tracks/{id}/export` (JSON con `Content-Disposition: attachment`).
- Límites *(supuestos pendientes del PO)*: nombre 1–80; puntos 2–500; zonas 0–100; tablero 50–2000 cm por lado; radio 0–200 cm; coordenadas ±10000 cm (pueden quedar fuera del tablero); zona `width`/`height` > 0 y ≤ 2000, nombre ≤ 80; `length_cm` > 0 y ≤ 100000; `perimeter_cm` entre 0 y 400000; `area_cm2` entre 0 y 4 × (`width_cm` × `height_cm` del tablero); ambos deben ser nulos si `closed` es falso; `start.edge` 0..(puntos−1) si `closed`, 0..(puntos−2) si abierta; `closed` exige ≥ 3 puntos.
- Errores: parseo de Pydantic → 422 con `detail` **lista** `[{type, loc, msg, input, ctx?}]`; regla de dominio → 422 con `detail` **objeto** `{reason, detail}`. Razones: `track_not_found` (404), `track_profile_unknown`, `track_name_invalid`, `track_points_count`, `track_zones_count`, `track_board_size`, `track_radius_range`, `track_coordinate_range`, `track_zone_size`, `track_zone_name`, `track_not_finite`, `track_length_invalid`, `track_metrics_invalid`, `track_start_invalid`, `track_closed_needs_three_points`.
- Reglas de pista en perfiles: `GET /api/profiles` devuelve `rules.track` cuando existe (`lgr2026`, `libre`): `line_width_mm` (mm), `gap_length_cm` (cm) y 13 reglas `{ enabled, value }`: `radius_min`, `angle_min` (grados), `no_sharp`, `separation_min`, `margin`, `zone_distance`, `closed`, `length_min`, `length_max`, `straight_min`, `straight_max`, `cross_max`, `gap_max` (todas las longitudes en cm). Los perfiles `club`, `mr4a`, `mr4s`, `mr4m` no traen bloque `track`.

### Query params (ya en inglés)

`limit` (renombrar `limite` donde quede) · `offset` · `q` · `type_id` · `robot_id` · `version_id` · `controller_id` · `source`

### Paginación

`items` · `total` · `limit` (limite) · `offset`

## Mediciones del celular (ingesta) — EN-32 / EN-33

El celular (en la mano o fijado al coche) envía lecturas crudas por **REST**; el backend las guarda tal cual
las recibe y calcula el resultado al terminar. No usa el contrato WebSocket de `velocista-sim` ni crea `run`.
Detalle de cálculos y base de datos: `docs/MEDICIONES.md`. Swagger: `/docs`.

**Autenticación.** Todas las rutas de esta sección exigen `Authorization: Bearer <token>` (se obtiene con
`POST /api/auth/login`) cuando el servidor corre con `AUTH_REQUIRED=true`. Sin token válido: **401**
`{detail: {reason: "unauthorized", detail}}`.

**Unidades.** Distancias en **metros**, áreas en m², tiempos `t_ms` en **milisegundos epoch** del reloj del
celular, ángulos en **grados**, giro en **°/s**, aceleración en **m/s²**.

### Rutas

| Ruta | Qué hace | Respuestas |
|---|---|---|
| `POST /api/measurements` | Crea una medición en estado `recording` y congela la calibración vigente del celular | 201 · 401 · 422 |
| `GET /api/measurements` | Lista (más recientes primero, sin trayectorias). Query: `device_id`, `place_name`, `limit` (1–200, defecto 50), `offset` | 200 · 401 · 422 |
| `GET /api/measurements/{id}` | Medición con la calibración usada y, si terminó, `result` con `raw_path`, `corrected_path` y `polygon` | 200 · 401 · 404 · 422 |
| **`POST /api/measurements/{id}/readings`** | **Ingesta: envía un lote de lecturas** | 200 · 401 · 404 · 409 · 422 |
| `GET /api/measurements/{id}/readings` | Todas las lecturas guardadas, ordenadas por tiempo (auditoría y reproceso) | 200 · 401 · 404 · 422 |
| `POST /api/measurements/{id}/finish` | Calcula el resultado y marca `finished`; se puede repetir (recalcula). 422 `measurement_too_short` si hay muy pocos pasos o lecturas GPS | 200 · 401 · 404 · 422 |
| `DELETE /api/measurements/{id}` | Borra la medición **y todas sus lecturas** (204 sin cuerpo). Conserva calibraciones y pruebas de GPS | 204 · 401 · 404 · 422 |
| `GET /api/calibrations/{device_id}` | Calibración vigente de cada tipo y qué métodos pueden medir (`ready.steps`, `ready.car`; el GPS no necesita calibración) | 200 · 401 · 422 |
| `GET /api/calibrations/{device_id}/history` | Todas las calibraciones, la más nueva primero (`origin`: `manual` o `model`) | 200 · 401 · 422 |
| `POST /api/calibrations/{device_id}/gyro` | Sesgo del giroscopio con el celular quieto: `{samples:[{t_ms, gyro_z_dps}]}` (1–5000; hacen falta 30+ muestras en 3+ s; `gyro_z_dps` ±2000). 422 `calibration_phone_moved` si se movió | 201 · 401 · 422 |
| `POST /api/calibrations/{device_id}/step` | Largo del paso: `{trials:[{distance_m (0–200], step_count o readings}]}` (1–10 pruebas). Avisa `uneven_pace` si difieren más de 2 cm | 201 · 401 · 422 |
| `POST /api/calibrations/{device_id}/car` | Modelo de velocidad del coche `v = k·PWM + c`: `{trials:[{pwm (0–100], distance_m (0–100], seconds (0–600]}]}` (1–20 pruebas) | 201 · 401 · 422 |
| `POST /api/gps-trials` | Guarda una prueba de error de GPS contra una distancia medida con cinta: `device_id`, `place_name`, `environment` (`open` / `buildings` / `trees` / `indoor`), `real_distance_m` (0–10000 m; 0 = mismo punto), `start_fixes` y `end_fixes` (3–600 cada una, `{t_ms, lat, lon, accuracy_m}`) | 201 · 401 · 422 |
| `GET /api/gps-trials` · `GET /api/gps-trials/summary` | Lista (filtro `device_id`) y resumen del error por método y del tamaño mínimo de campo | 200 · 401 · 422 |
| `PATCH /api/gps-trials/{id}` | Cambia solo `place_name` | 200 · 401 · 404 · 422 |
| `DELETE /api/gps-trials/{id}` | Borra una prueba de GPS (204 sin cuerpo); el resumen deja de contarla | 204 · 401 · 404 · 422 |
| `POST /api/precision-model/runs` · `GET /api/precision-model/runs` | Ajusta sesgo del giro y largo del paso con mediciones repetidas del mismo lugar (`measurement_ids` 2–30, `max_attempts` 1–200, `apply`); lista las corridas | 201 / 200 · 401 · 404 · 422 |
| `POST /api/precision-model/evaluations` | Compara el algoritmo solo contra el algoritmo con el modelo (`measurement_ids` 2–30, `max_attempts`). No guarda nada | 200 · 401 · 404 · 422 |
| `POST /api/polygons/solve` · `POST /api/polygons/from-points` | Cierra una figura con lados y ángulos conocidos (`sides_m`, `angles_deg`; `null` = desconocido) o calcula lados, ángulos, perímetro y área de puntos marcados (`points` `{x, y}` en metros, 3–100). No guardan nada | 200 · 401 · 422 |

### Crear la medición — `MeasurementIn`

| Campo | Tipo / valores | Descripción |
|---|---|---|
| `method` * | `steps` · `gps` · `car` | Cómo se mide. `steps` usa el largo del paso; `car` exige calibración de velocidad (`measurement_not_calibrated`) |
| `source` | `phone` (defecto) · `simulator` · `robot` | Origen de las lecturas |
| `mount` | `hand` (defecto) · `robot` | **Montaje del celular, por medición** (no por lectura): en la mano o fijo en el coche. **`method: "car"` exige `mount: "robot"`** (422 `measurement_mount_invalid`) |
| `place_name` * | texto 1–80 | Lugar medido |
| `device_id` * | texto 1–64 | Identificador del celular (UUID) |
| `closed` | booleano, defecto `true` | `true` si el recorrido vuelve al punto de partida |
| `reference` | `{points:[{x,y}] (3–200), scale_n (>0, ≤10000, defecto 1), name (≤80)}` o `null` | Plano a comparar, en metros, escala 1:N |
| `tape_side_m` | número en (0, 1000] o `null` | Primer lado medido con cinta (salida → primera esquina), en metros |

Los campos no listados se rechazan con 422. `MeasurementOut` devuelve además `id`, `calibration`, `status`
(`recording` / `finished`), `reading_count`, `started_at`, `finished_at` y `result`.

### Enviar lecturas — `POST /api/measurements/{id}/readings`

Cuerpo: `{"readings": [ReadingIn, …]}` con **1 a 1000 lecturas por lote**. Lo recomendado es un lote cada
**0,5 s**. Un lote vacío o de más de 1000 lecturas se rechaza entero con **422** y no se guarda nada.

**`ReadingIn`** (los campos desconocidos se ignoran; en particular, un `mount` dentro de una lectura
se ignora: el montaje es de la medición):

| Campo | Tipo | Unidad | Descripción |
|---|---|---|---|
| `seq` * | entero ≥ 0 | — | Número de secuencia dentro de la medición. Empieza en 0 y sube de 1 en 1. Un `seq` ya guardado se ignora |
| `t_ms` * | entero, 0 a 4 102 444 800 000 | ms (epoch) | Hora del reloj del celular al tomar la muestra |
| `kind` * | `motion` · `gps` · `corner` | — | Tipo de lectura (ver abajo) |
| `gyro_z_dps` | número o `null` | °/s | Giro alrededor del eje de la pantalla, **positivo = antihorario**; valor absoluto ≤ 2000. En el navegador: `rotationRate.alpha` |
| `accel` | `[x, y, z]` o `null` | m/s² | Aceleración **incluida la gravedad**; exactamente 3 números, cada uno con valor absoluto ≤ 160 (±16 g). En el navegador: `accelerationIncludingGravity` |
| `step` | booleano, defecto `false` | — | `true` si el celular ya detectó un paso |
| `pwm` | número o `null` | % | PWM del motor (−100 a 100); solo celular sobre el coche |
| `lat` | número o `null` | grados (WGS84) | Latitud, −90 a 90 |
| `lon` | número o `null` | grados (WGS84) | Longitud, −180 a 180 |
| `accuracy_m` | número o `null` | m | Precisión horizontal que informa el celular; mayor que 0 y hasta 1000 |

**Valores de `kind`:**

| `kind` | Qué trae | Se exige |
|---|---|---|
| `motion` | giroscopio, acelerómetro y opcionalmente `step` o `pwm` | al menos uno de `gyro_z_dps`, `accel`, `step: true` o `pwm` |
| `gps` | posición | `lat`, `lon` y `accuracy_m` juntos |
| `corner` | marca de esquina (botón «Marcar esquina») | solo `seq` y `t_ms` |

**Los datos se guardan tal como llegan**: el backend no genera, completa ni suaviza valores. El sesgo del
giroscopio se resta al calcular, no al guardar.

**Respuesta 200 — `IngestReportOut`:**

| Campo | Descripción |
|---|---|
| `accepted` | Lecturas nuevas guardadas |
| `duplicates` | Lecturas válidas ignoradas porque su `seq` ya estaba guardado en esa medición |
| `discarded` | Objeto `{motivo: cantidad}` con las lecturas inválidas (no se guardan) |
| `total_readings` | Lecturas guardadas en la medición después de este lote |

**Reenvío idempotente.** `seq` es único por medición. Si un lote falla (corte de red), el celular lo
**reenvía igual**: lo ya guardado cuenta en `duplicates` y no se duplica ni se pierde nada.

**Una lectura inválida no rechaza el lote**: se descarta, el resto se guarda y la respuesta dice por qué.
El descarte también se anota en el log de la aplicación (no se guarda en la base de datos).

| Motivo de descarte | Cuándo |
|---|---|
| `kind_unknown` | `kind` no es `motion`, `gps` ni `corner` |
| `seq_or_time_invalid` | `seq` < 0 o `t_ms` fuera de 0 a 4 102 444 800 000 |
| `gps_incomplete` | `kind: "gps"` sin `lat`, `lon` o `accuracy_m` |
| `gps_out_of_range` | `lat` fuera de ±90, `lon` fuera de ±180 o valor no finito |
| `gps_accuracy_invalid` | `accuracy_m` ≤ 0, > 1000 o no finito |
| `motion_empty` | `kind: "motion"` sin giro, aceleración, paso ni PWM |
| `gyro_out_of_range` | `gyro_z_dps` no finito o con valor absoluto > 2000 |
| `accel_out_of_range` | `accel` sin 3 elementos o con algún valor absoluto > 160 |
| `pwm_out_of_range` | `pwm` no finito o fuera de −100 a 100 |

**Límites.**
- **1000 lecturas por lote**: más (o un lote vacío) → 422.
- **Tope por medición: `READINGS_MAX` = 200 000 lecturas** (constante del código, ≈ 1 h a 50 Hz). Si el lote
  haría pasar el tope, se rechaza **entero** con **409** `measurement_too_many_readings` y no se guarda nada.

**Errores:**

| Código | `reason` | Cuándo |
|---|---|---|
| 401 | `unauthorized` | Falta el token o está vencido o alterado |
| 404 | `measurement_not_found` | La medición no existe |
| 409 | `measurement_finished` | La medición ya terminó (`/finish`); hay que crear otra |
| 409 | `measurement_too_many_readings` | El lote superaría `READINGS_MAX` |
| 422 | — | Cuerpo inválido (lote vacío o de más de 1000, tipos incorrectos). `detail` es una **lista** `[{type, loc, msg, input}]` de Pydantic |
| 422 | `measurement_*` | Regla de dominio al crear o terminar (por ejemplo `measurement_mount_invalid`, `measurement_not_calibrated`, `measurement_too_short`). `detail` es un **objeto** `{reason, detail}` |

**Ejemplo de lote:**

```json
POST /api/measurements/42/readings
{ "readings": [
  { "seq": 0, "t_ms": 1730592000000, "kind": "motion",
    "gyro_z_dps": 0.42, "accel": [0.12, 0.31, 9.79] },
  { "seq": 1, "t_ms": 1730592000020, "kind": "gps",
    "lat": -8.11160, "lon": -79.02870, "accuracy_m": 4.8 },
  { "seq": 2, "t_ms": 1730592003000, "kind": "corner" },
  { "seq": 3, "t_ms": 1730592003020, "kind": "gps",
    "lat": 95.0, "lon": -79.0287, "accuracy_m": 5.0 }
]}
```

Respuesta (la lectura 3 tiene `lat` fuera de rango):

```json
{ "accepted": 3, "duplicates": 0, "discarded": { "gps_out_of_range": 1 }, "total_readings": 3 }
```

**`GET /api/measurements/{id}/readings`** devuelve una lista de `ReadingOut` con `seq`, `t_ms`, `kind`,
`gyro_z_dps`, `accel`, `step`, `pwm`, `lat`, `lon` y `accuracy_m` (los ausentes salen `null`) y **`mount`**
(`hand` o `robot`), ordenada por tiempo.

**`mount` en cada lectura (EN-32, criterio 2).** Cada lectura que devuelve la API indica si el celular iba
en la mano (`hand`) o sobre el robot (`robot`). El valor **se hereda de la medición** (`MeasurementIn.mount`):
no se guarda por lectura, el celular no lo envía y todas las lecturas de una medición devuelven el mismo
valor. `method: "car"` implica `mount: "robot"`. Si el celular manda `mount` dentro de una lectura, se
ignora. Es un campo añadido a la salida: los clientes que no lo conocen siguen funcionando.

**Tiempo de respuesta.** Un lote de 25 y uno de 1000 lecturas se responden en menos de 1 s; lo comprueba
`tests/integration/rest/measurements/test_ingest_latency.py` contra PostgreSQL local. El tiempo de punta a
punta también depende de la red del celular.

---

## Pendientes / futuro

- **Servicio de ingesta** aparte enviará datos más adelante → previsto como *adapter* en `infrastructure/`; NO se implementa en v1.
- **Frontend:** refactor para leer claves de canal desde el `manifest` en vez de hardcodearlas (post-v1).
- **Firmware:** gracias a la anti-corruption layer, para v1 **solo** necesita emitir las **claves de canal** en inglés (`battery_v`, `line_array`); `type` y enums los normaliza el backend. El renombrado del firmware deja de bloquear la migración del frontend.
