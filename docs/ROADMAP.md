# ROADMAP — estado real del backend

Estado a **2026-11-11**, verificado contra el código de `main` (`4fa85f3`), las migraciones, el
OpenAPI generado y la suite de pruebas. Clean Architecture; código y carpetas en inglés,
comentarios en español. Contrato: [`CONTRACT.md`](CONTRACT.md). Mediciones: [`MEDICIONES.md`](MEDICIONES.md).

> Cada afirmación de este documento se puede comprobar en el repositorio (ruta o comando entre
> paréntesis). Lo que no está comprobado no aparece como hecho.

## 1. Qué está hecho

| Área | Estado | Dónde se comprueba |
|---|---|---|
| Base: settings, motor y sesión, errores dominio→HTTP, logging, CORS, `/api/health` | Hecho | `src/velocista/infrastructure/`, `interface/rest/errors.py`, `middleware.py` |
| Catálogo e inventario, armador de robots y versiones, configuración, eventos | Hecho (REST: `catalog`, `builder`, `control`, `events`) | `interface/rest/{catalog,builder,config,events}` |
| **Reglamento / perfiles** (`rules`) | Hecho: `GET /api/profiles`, `GET /api/profiles/{id}` | `interface/rest/rules`, migraciones `0002` y `0003` (semillas) |
| **Setups y controladores** (`optimization`: almacenar y aplicar) | Hecho: CRUD de setups, aplicar setup, aplicar preset, controladores, configuración vigente | `interface/rest/optimization` (9 operaciones) |
| **Corridas** (`runs`) | Hecho: listar, leer, vueltas, nota, corrida simulada e ingesta del simulador | `interface/rest/runs` (6 operaciones), migraciones `0002`, `0004`, `0005` |
| **WebSocket / gateway** | Hecho: `/ws/robot`, `/ws/timer`, `/ws/console` (alias `/ws/consola`), contrato con manifiesto, validación y capa de traducción ES→EN; comandos por `POST /api/devices/{device}/commands` | `interface/websocket/`, `infrastructure/realtime/`, `tests/e2e/test_ws_robot_flow.py` |
| **Autenticación** | Hecho: `POST /api/auth/login`, `GET /api/auth/me`, middleware activo con `AUTH_REQUIRED` (obligatorio en producción) | `interface/rest/auth`, `infrastructure/config/settings.py` |
| **Dispositivos** | Hecho: manifiesto del robot, comandos, registro de conexiones vivas | `interface/rest/devices`, `infrastructure/realtime/registry.py` |
| **Pistas del trazador** (`tracks`) | Hecho: CRUD, exportar, perfil, `perimeter_cm` y `area_cm2` | `interface/rest/tracks` (6 operaciones), migraciones `0006`, `0007`, `0008` |
| **Mediciones con el celular** (EN-32 a EN-35) | Hecho: ingesta por lotes, calibración, cálculo al terminar, `mount` por lectura, `turn_total_deg`, borrado | `interface/rest/measurements`, migración `0009`, [`MEDICIONES.md`](MEDICIONES.md) |
| **Error del GPS** (SP-06) | Hecho el registro y el resumen; el límite está en la sección 3 | `POST /api/gps-trials`, `GET /api/gps-trials/summary` |
| **Modelo de precisión** (SP-07) | Hecho: ajuste por refuerzo simple y evaluación contra el algoritmo solo | `POST /api/precision-model/{runs,evaluations}`, [`EVALUACION_MODELO.md`](EVALUACION_MODELO.md) |
| **Contorno por lados y ángulos / por puntos** (EN-42) | Hecho | `POST /api/polygons/{solve,from-points}`, [`POLIGONOS.md`](POLIGONOS.md) |
| Migraciones | Una sola cabeza, revisión `0009` | `src/velocista/infrastructure/persistence/migrations/versions/` |
| Despliegue | `Dockerfile` y `render.yaml` (web + base, plan gratuito) | raíz del repositorio |

Total de la API: **73 operaciones REST** (`GET /openapi.json`) y 3 rutas WebSocket.

## 2. Casos de uso del profesor (estado de la API)

| CU | Qué pide | Con qué se cubre | Estado |
|---|---|---|---|
| CU-1 | Medir un espacio y compararlo con su plano a escala | `POST /api/measurements` (con `reference` y `scale_n`), `readings`, `finish` | Cubierto |
| CU-2 | Mapear la pista con una vuelta del celular y compararla con la diseñada | `/api/tracks` + mediciones con `reference` + `turn_total_deg` | Cubierto en la API; la optimización (Twiddle/bayesiana) es el siguiente sprint |
| CU-3 | Medir áreas de cualquier forma, también cóncavas | `/api/polygons/from-points`, mediciones (fórmula de Gauss) | Cubierto |
| CU-4 | Error del GPS frente a cinta y desde qué tamaño sirve | `/api/gps-trials`, `/summary`, `min_gps_size_m`, `/precision-model/evaluations` | **Parcial** (sección 3) |
| CU-5 | Plano desde lados y ángulos | `/api/polygons/solve` | Cubierto |

## 3. Qué falta de verdad

### Optimización real (siguiente sprint)
- No existe un optimizador de parámetros del **robot** (Twiddle o bayesiano). Hoy `optimization`
  solo **guarda y aplica** setups. El único ajuste automático del repositorio es el de la precisión
  de las mediciones (`domain/measurements/tuning.py`).

### CU-4: concluir «desde qué tamaño sirve el GPS» con datos reales
- El resumen da un solo `min_side_m` global (error **máximo** del mejor método ÷ 10 %). Por
  entorno solo devuelve los errores por método, no un tamaño mínimo, y no relaciona el error con
  la distancia de la cinta.
- Las correcciones que se comparan son tres: una lectura, promedio y promedio ponderado por
  precisión. «Esperar a que mejore la precisión» y el giroscopio no se prueban.
- Faltan pruebas reales cargadas: lugares conocidos, varias distancias, varias repeticiones.

### Decisiones del dueño del producto de EN-32
Pendientes en `.kiro/specs/EN-32-ingesta-lecturas-celular/tasks.md`:
- Confirmar que **REST** es el canal definitivo o si también se quiere un mensaje WebSocket (E.4b).
- Guardar el conteo de descartes por medición (E.5, opcional).
- Pista de interior o exterior (GPS sí o no), vista en vivo, vueltas estimadas, retención e
  inactividad (0.1 a 0.4).
- Hacer configurable el tope de lecturas por medición (hoy `READINGS_MAX = 200000`, error 409
  `measurement_too_many_readings`).
- Prueba guiada con un celular real (7.6 y 7.7) y borrar después las mediciones de prueba.
- Umbrales de 3 % y 6 % (semáforo), 25 m de precisión y 10 % del GPS: propuestas pendientes del PO.

### Tiempo real
- **Claves de canal del WebSocket**: el backend las reenvía tal cual; el firmware debe emitirlas
  en inglés (`battery_v`, `line_array`) y el frontend leerlas del manifiesto. Esperan al firmware
  ([`CONTRACT.md`](CONTRACT.md), «Claves de canal» y «Pendientes / futuro»).
- Reenviar un resumen del celular a las consolas tras cada lote (tarea 2.8 de EN-32): no existe.

### Calidad y operación
- `alembic check` marca diferencias anteriores en `external_telemetry` (único `session_id, seq`) y
  `lap_segment.accumulated_error` ([`MEDICIONES.md`](MEDICIONES.md), sección 7).
- Retención y cierre por inactividad de las mediciones: sin implementar.
- Despliegue en Render: decisión del dueño; antes de cualquier cambio de esquema se comprueba
  `alembic_version`. Las pruebas automáticas **nunca** se ejecutan contra Render.

## 4. Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -q          # suite completa (necesita PostgreSQL local)
.\.venv\Scripts\python.exe -m ruff check .       # estilo
```

PostgreSQL local: `docker compose up -d` (puerto `127.0.0.1:15432`).

Última corrida completa (2026-11-11, `main` `4fa85f3`, PostgreSQL local): **910 pasaron, 0 fallaron,
15 omitidas** en 13 min 15 s. En la prueba de latencia, un lote de 25 lecturas tardó 24–32 ms y uno
de 1000 tardó 449–665 ms.

## 5. Principio de verificación

Cada pieza se ejecuta y se prueba antes de la siguiente: unitarias del dominio sin base de datos,
integración con PostgreSQL real en un esquema aislado, contrato (OpenAPI y errores) y flujos
extremo a extremo. Nunca se prueba contra la base de producción.
