# Integración con velocista-sim

Cliente saliente del backend hacia `wss://velocista-sim-production.up.railway.app/ws`.
Contrato v1, revisión 1.2, obtenido de AlessoEngnr/velocista-sim, commit `ea74075`.
Los JSON Schemas en `src/velocista/infrastructure/integrations/velocista_sim/schemas`
y los ejemplos de `tests/fixtures/sim_contract` proceden de ese repositorio:
https://github.com/AlessoEngnr/velocista-sim/blob/ea74075/contract/contract-v1.md
No se modifica el simulador ni se requiere que envíe resultados por REST.

## Configuración

Instalar las dependencias del proyecto y ejecutar `python -m alembic upgrade head`.
Configurar en `.env` o en las variables del despliegue:

```dotenv
SIM_ENABLED=true
SIM_WS_URL=wss://velocista-sim-production.up.railway.app/ws
SIM_INTERNAL_ROBOT_ID=<robot registrado en este backend>
SIM_SETUP_ID=<setup PID de una versión del robot interno>
SIM_PROFILE_ID=club
SIM_STORE_TELEMETRY=true
```

`SIM_ROBOT_ID` y `SIM_TRACK_ID` son selecciones externas opcionales. Si se omiten,
se usan los valores anunciados por el servidor. Una selección distinta de la solicitada
se muestra como `mismatch` y bloquea comandos. No se necesitan credenciales para el
servicio actualmente desplegado. Los endpoints del backend mantienen su autenticación.

Sin referencias internas se puede observar la conexión y la telemetría, pero `start`
devuelve `sim_context_missing`. Nunca se deduce una versión o un setup del ID externo.
Al iniciar, se conserva el setup seleccionado y se crea un snapshot de setup efectivo
cuando sus parámetros difieren de los realmente anunciados por el simulador.

Ejecutar **una instancia y un worker**. Cada proceso abre una sesión externa;
no hay coordinación distribuida entre procesos. El arranque Docker existente aplica
las migraciones antes de servir y usa un worker. Habilitar SIM_ENABLED después de
configurar las referencias. El modo externo ocupa los comandos de robot y rechaza
conexiones entrantes a `/ws/robot` para evitar controlar fuentes ambiguas.

## API y consola

- `GET /api/simulator`: estado, hello, capacidades, configuración, última telemetría,
  corrida activa, salud de persistencia, pérdidas y último diagnóstico.
- `POST /api/devices/robot/commands`: comandos existentes con `type` y `data`.
- `/ws/console` y alias `/ws/consola`: mensajes con `sender: "sim"`. Tipos:
  `connection`, `hello`, `config`, `telemetry`, `event`, `catalog`, `error`,
  `diagnostic` y `command_result`. Al conectar se entrega un snapshot `connection`.
- `GET /api/runs` y `GET /api/runs/{id}`: historial persistente con identidad externa,
  `closure_status` (`finished` o `interrupted`), `summary`, `config_changed` y
  `optimization_eligible`. Las vueltas siguen en `/api/runs/{id}/laps`.

Ejemplos de cuerpos para el endpoint de comandos:

```json
{"type":"set_config","data":{"params":{"kp":0.045,"ki":0,"kd":0.9},"base_speed":80}}
{"type":"start","data":{}}
{"type":"stop","data":{}}
{"type":"set_rate","data":{"hz":50}}
{"type":"list","data":{}}
```

`setup` acepta `controller: "pid"` y `parameters` con `kp`, `ki`, `kd`, `base_speed`.
Un `setup_id` opcional se valida contra el robot interno antes de aplicarse.
La confirmación de comandos procede del evento o configuración externa, nunca de
un ACK inventado. Un timeout se informa como `command_uncertain`, se registra y
bloquea nuevos comandos hasta reconectar; no se reenvía `start` automáticamente.
Calibrar, cambiar modo/color y los comandos solo-sim no están soportados por este adaptador.

El frontend debe consumir estos mensajes de fuente `sim` y tolerar los campos nulos.
La forma de la telemetría incluye el mensaje externo, `channels` y `state`; `calibrated`,
`rssi_dbm`, `mode` y `line` son `null`. Los canales opcionales solo aparecen cuando
el último `hello` declara la capacidad. No se anuncia una frecuencia del lazo de
control a partir de la frecuencia de telemetría.

## Persistencia y recuperación

Migración `0005`: sesiones externas, identidad única de corrida por fuente/sesión/run,
estado de cierre, campos desconocidos anulables y tabla `external_telemetry`.
Se conservan `t_ms` relativo y `received_at` UTC por separado. Las muestras se escriben
en transacciones por lotes de hasta 100; los eventos mantienen su orden.
La cola tiene 5000 mensajes por defecto y reserva espacio para eventos.
Cuando se llena, se descartan muestras nuevas y se acumulan contadores de pérdida.
Los lotes fallidos se retienen y reintentan. No se inicia otra corrida con persistencia
averiada. Una cola de eventos saturada fuerza la desconexión y espera su vaciado.

La cola es **memoria del proceso**, no un journal durable: una terminación brusca
puede perder muestras o eventos aún no confirmados en PostgreSQL. Al reiniciar se
cierran como interrumpidas las corridas persistidas que seguían abiertas. Un apagado
normal intenta vaciar la cola durante diez segundos y registra lo que quede pendiente.
No hay replay del servicio externo. La retención/purga de telemetría debe definirse
según el volumen del despliegue; no se borra historial automáticamente.

Cada navegador tiene una cola acotada. Uno lento se desconecta con código 1013 y
puede reconectar para obtener el snapshot actual. No bloquea el lector ni PostgreSQL.
La lista de corridas muestra solo las cerradas; su aparición puede demorarse hasta
que se confirme el siguiente lote de persistencia.

Sin vueltas se conserva igualmente la corrida. `accumulated_error`, `battery_v`
por vuelta y `j` permanecen nulos: el contrato no entrega esas métricas por vuelta.
El resumen externo conserva tiempos y salidas de pista. El optimizador debe repetir
cada configuración y promediar una métrica explícita, descartando corridas con
`config_changed`, interrumpidas o con pérdidas. `optimization_eligible` es un filtro
conservador para resultados con vueltas; no ejecuta ni promedia evaluaciones por sí mismo.
El antiguo endpoint `/api/runs/simulated` es un generador sintético independiente y
no representa una corrida contra Railway; se bloquea cuando la integración está activa.

## Verificación

```powershell
python -m pytest tests -q --tb=short
$env:SIM_LIVE_TEST="1"
python -m pytest tests/integration/test_external_persistence.py -q --tb=short
```

Las pruebas de PostgreSQL usan esquemas temporales aislados. La prueba remota abre
su propia sesión en Railway, ejecuta cuatro corridas, interrumpe una, reconecta,
consulta historial y elimina únicamente el esquema temporal de prueba.
Los ejemplos oficiales cubren validación de campos y capacidades; el servidor local
controlado cubre rechazos, timeout, reconexión y fallos de escritura.

Para aceptación con frontend: comprobar `ready`, aplicar configuración, iniciar/parar,
consultar historial tras persistir, recargar y verificar identidad y resumen. La interfaz
visual pertenece a otro proyecto; este cambio entrega la API y el flujo de consola.
