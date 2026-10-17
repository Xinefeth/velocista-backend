# velocista-backend

API REST y WebSocket para la consola, el robot velocista y el cronómetro. El código y los contratos de red están en inglés; la UI puede presentar etiquetas localizadas.

## Desarrollo local (Windows)

Requiere Python 3.12 o superior y Docker Desktop con contenedores Linux.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
Copy-Item .env.example .env # solo si aún no existe .env
docker compose up -d --wait db
.\.venv\Scripts\python.exe -m velocista.infrastructure.startup
```

El arranque aplica las migraciones y semillas antes de abrir el puerto 8000. PostgreSQL local escucha en `127.0.0.1:15432` para evitar colisiones con otros proyectos. `DATABASE_URL` tiene prioridad sobre `POSTGRES_*`.

- API y Swagger: `http://127.0.0.1:8000` y `/docs`
- Salud: `/api/health` informa estado de PostgreSQL y conexiones de robot/cronómetro.
- Consola: el desarrollo de Vite reenvía `/api` y `/ws` al backend en el puerto 8000.

## Integración con dispositivos y corridas

La API, el catálogo, robots, versiones, setups, perfiles e historial funcionan aunque el servicio de simulación, el robot y el cronómetro estén desconectados. La consola se autentica con `POST /api/auth/login`; en producción, las rutas REST requieren JWT.

Los dispositivos envían sus mensajes por `WS /ws/robot` y `WS /ws/timer`, autenticándose con `DEVICE_TOKEN_ROBOT` y `DEVICE_TOKEN_TIMER`. La consola usa `WS /ws/console`. `POST /api/devices/{robot|timer}/commands` entrega comandos y sus secuencias para ACK. La ingesta del dispositivo solo crea/actualiza corridas reales cuando recibe el estado de ejecución, vueltas y cruces oficiales; los mensajes ajenos a corridas no crean datos de corrida. El canal de batería acepta `battery_v` y `bateria_v`, y las vueltas aceptan `lost_lines` y `lines_lost`.

El adaptador saliente a `velocista-sim` y su configuración completa están descritos en [docs/SIMULATOR.md](docs/SIMULATOR.md). El backend mantiene una conexión WebSocket al servicio, valida contrato v1 y capacidades, guarda sesiones, corridas, vueltas y telemetría y publica el estado por `/api/simulator` y `/ws/console` (`/ws/consola`). La conexión está deshabilitada por defecto en `.env.example` (`SIM_ENABLED=false`); habilítala después de configurar un robot interno, un setup PID y un perfil existentes. El `.env` local se habilita al aplicar esta integración.

El endpoint sintético `POST /api/runs/simulated?robot_id=...` sigue disponible para QA con la integración apagada; queda bloqueado cuando `SIM_ENABLED=true` para que no se confunda con el simulador desplegado. Las métricas que el contrato no proporciona se conservan como nulas.

## Despliegue en Render

`render.yaml` crea un servicio Docker para el backend y PostgreSQL administrado. Despliega desde la carpeta `velocista-backend`. El servicio se configura con una instancia y un worker porque las conexiones WebSocket activas viven en memoria del proceso.

Configura `ADMIN_PASSWORD` (12 caracteres o más), `CORS_ORIGINS` con el origen exacto del frontend publicado y dos tokens de dispositivo distintos. Render genera `SECRET_KEY`, los tokens de dispositivos y `SIMULATION_SERVICE_TOKEN` desde el blueprint. Entrega ese token solo al servicio de simulación. La URL del backend para el frontend debe incluir `/api`, por ejemplo `https://velocista-backend.onrender.com/api`. En HTTPS, la consola deriva el WebSocket seguro `wss://.../ws/console`.

El frontend es un servicio estático independiente: antes de compilarlo, define `VITE_API_BASE_URL` con la URL HTTPS del backend y `/api`. Configura el mismo origen del frontend en `CORS_ORIGINS` del backend. No pongas secretos en variables `VITE_*`.

## Verificación

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests
```

Estado de verificación local: backend `43 passed, 13 skipped`; Ruff limpio. La prueba de Docker con PostgreSQL vacío pasó migraciones, seeds, login/CORS, CRUD de robot y configuración, corrida simulada y una corrida real con una vuelta enviada por WebSocket. Las migraciones también pasaron upgrade, comparación de modelos, downgrade y re-upgrade en una base temporal.

Las 13 pruebas omitidas son plantillas heredadas sin implementación. La simulación de protocolo comprueba el intercambio software; no sustituye la prueba con el robot y cronómetro físicos.
