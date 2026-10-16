# ROADMAP — lo que falta del backend

Estado a 2026-10-15. Clean Architecture; código/carpetas en inglés, comentarios en español.
Referencia de origen (a portar): `Proyecto_Taller/api/app`. Contrato: [`CONTRACT.md`](CONTRACT.md).

## Implementado (núcleo REST ejecutado; verificación detallada en Fase 0)

- Base: settings, motor BD + sesión, errores dominio→HTTP, logging + middleware, CORS, `/api/health`, registro de dispositivos.
- Verticales REST: **catalog, builder, config, events** (22 endpoints) en 4 capas.
- Alembic (env/ini), `create_all` de desarrollo, `docker-compose` (Postgres), `.env.example`.

---

## Fase 0 — Verificar el núcleo REST — backend verificado (2026-10-15)

- Entorno `.venv` con Python 3.12; dependencia `psycopg[binary]` declarada.
- PostgreSQL 16 de este repositorio aislado en `127.0.0.1:15432` (5432 ocupado;
  Windows bloqueó también 5433). Compose espera a que PostgreSQL esté disponible.
- Importación y OpenAPI correctos: 22 operaciones REST más `/api/health`.
- `bootstrap` crea el esquema; prueba real REST/PostgreSQL aprobada con datos temporales
  revertidos: componentes, búsqueda, inventario/revisión, robots, eventos y archivado.
- Corregidas las excepciones inexistentes del scaffold `runs` que impedían cargar pytest.
- Resultado: **1 passed, 13 skipped**; las omitidas son plantillas, no cobertura real.
- Pendiente: verificación del frontend mediante su proxy Vite a `:8000`.
- Tipos/ranuras y creación completa de versiones quedan para Fase 1; WS/comandos para Fase 2.

## Fase 1 — Migraciones + semillas

- **Objetivo:** esquema reproducible y datos de estructura mínimos.
- **Tareas:**
  - `alembic revision --autogenerate -m "initial schema"` (con la BD arriba) → revisar a mano.
  - Migración de **semillas** portada del backend viejo (migr. 0007/0008), en inglés:
    - `component_type` (14 tipos: mcu, exp, linea, … con sus `fields`/`capabilities`, claves EN,
      `type` del campo = `number`/`text`).
    - `slot` (ranuras: id, type_id, required, quantity_editable, rules_dependent).
  - Decidir: `create_all` solo para dev; en pista siempre Alembic.
- **Aceptación:** `alembic upgrade head` sobre BD limpia deja tipos y ranuras sembrados;
  `GET /api/component-types` y `GET /api/slots` devuelven las semillas; `createRobotVersion` ya
  puede validar ranuras.

## Fase 2 — Motor WebSocket + comandos  🔴 (pieza grande; desbloquea config real y prueba conjunta)

> Independiente de runs/optimization/rules → se puede hacer en paralelo a las fases 3–5.

- **Contrato** (`interface/websocket/contract/`): portar de `app/contract/`:
  - `manifest` (canales, parámetros, controladores, sensores, actuadores, frecuencias; validadores).
  - `messages` robot (`status`/`signals`/`lap`/`event`/`sync`/`ack`/`setup`/`mode`/`line`/`lap_close`)
    y timer (`hello`/`crossing`/`timer_status`/`rearm`).
  - `catalog` (quién envía cada tipo, modelo que valida, si requiere ack).
  - `validation` (canales vs manifiesto; setup vs manifiesto; completitud de setup).
  - Completar `translation.py` (`translate_payload`) y `envelope.py` (ya tienen las tablas).
- **Gateway** (`gateway.py`): `/ws/robot`, `/ws/timer`, `/ws/console`:
  - manifiesto obligatorio primero; ack + dedup por seq; descarte fuera de orden (`t_ms`);
  - avisos de canal; **traducción ES→EN en la frontera** antes de rebroadcast/persistir;
  - alta/baja en el registro de dispositivos (`realtime/registry`).
- **Comandos** (`POST /api/devices/{device}/commands`): validar contra manifiesto/estado vivos
  (`calibrate/start/stop/setup/mode/line/lap_close` + `rearm` al timer); orden de guardas:
  `invalid_command → no_manifest → unknown_command → competition_locked → busy → device_unavailable`.
- **Cablear reales:** `DeviceGateway` (reemplaza el provisional), `RobotActivity` (estado `running`
  vivo + corrida abierta), `apply_setup`/`apply_config` validados.
- **Aceptación:** robot simulado conecta por `/ws/robot`, manda `manifest`+`status`; la consola
  recibe en inglés por `/ws/console`; `setMode/setLine` reales funcionan; **prueba conjunta con el frontend**.

## Fase 3 — rules (reglamento / perfil)

- **Objetivo:** tabla `profile` (perfil_reglamento) + endpoints; la necesita `runs` por FK.
- Portar `app/modulos/reglamento` (models/schemas/service/router) a las 4 capas.
- **Aceptación:** CRUD/consulta de perfiles; FK de `runs` resoluble.

## Fase 4 — optimization (setup + optimizadores)

- **Objetivo:** tabla `setup` (id, version_id) + lógica de optimización (Twiddle/bayesiana).
- Portar `app/modulos/optimizacion` (models/schemas/service 195 + router 201 + puertos).
- Depende de builder (versión) y del `apply_setup` del gateway (fase 2).
- **Aceptación:** crear/listar setups; aplicar setup al robot (con gateway arriba); FK de `runs` resoluble.

## Fase 5 — runs (corridas)

- **Objetivo:** `GET /api/runs`, `GET /api/runs/{id}`, `/laps`, `PATCH` nota, corrida simulada.
- **Reescribir** el scaffold inicial de `runs` (es inconsistente: corridas es read-heavy, no "close_lap").
- Portar `app/modulos/corridas` (models corrida/vuelta/sector/segmento, service 195 con `J`,
  selección de mejor vuelta, snapshot de contexto) + **generador** de corridas simuladas (`generador.py`).
- Depende de builder (versiones), optimization (`setup`), rules (`profile`).
- **Aceptación:** listar/consultar corridas; crear corrida simulada; vueltas con sectores/segmentos.

## Fase 6 — auth

- Portar `app/modulos/auth` (models/schemas/service/router) + `core/seguridad` (tokens).
- **Aceptación:** login/validación de token según el diseño original.

## Fase 7 — Cierre

- Migración final consolidada + semillas completas; `render.yaml`/`Dockerfile` (despliegue);
  revisar `tests/` (hoy solo formato) y escribir los que el usuario pida; `GET /api/health` con
  `devices` reales (tras fase 2).

---

## Orden recomendado

1. **Fase 0** (verificar REST) → corrige la base.
2. **Fase 1** (migraciones+semillas) y **Fase 2** (WS/commands) en paralelo — la 2 da la prueba conjunta.
3. **Fase 3 → 4 → 5** (rules → optimization → runs), en ese orden por dependencias de FK.
4. **Fase 6** (auth) y **Fase 7** (cierre).

## Principio de verificación

Portar y **ejecutar vertical por vertical**: cada fase se arranca y prueba antes de la siguiente,
para no acumular código sin verificar. El entorno de ejecución (Python 3.12 + Docker Postgres) es
la máquina del usuario.
