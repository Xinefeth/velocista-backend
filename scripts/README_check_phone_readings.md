# check_phone_readings.py — ¿las lecturas del celular son reales?

Script de apoyo de EN-32 (tarea 7.5). Vive fuera del código de la API: solo **lee**
`GET /api/measurements/{id}` y `GET /api/measurements/{id}/readings`, no escribe nada y usa solo la
biblioteca estándar de Python (no hace falta instalar nada).

Calcula: módulo medio de la aceleración, ángulo acumulado del giroscopio (integra `gyro_z_dps` sobre
`t_ms` con la regla del trapecio), huecos de `seq`, orden de `t_ms`, frecuencia de muestreo y variación
de `lat`/`lon`/`accuracy_m`. Avisa de señales de dato falso (todo ceros, `null`, valores constantes,
`seq` perfecto con el tiempo congelado, reloj demasiado perfecto, agente de escritorio) y da un veredicto
por paso de la guía.

## Cómo usarlo

```powershell
# 1) Contra la API local (con AUTH_REQUIRED=false no hace falta token)
python scripts/check_phone_readings.py http://127.0.0.1:8000 42 --step rest

# 2) Contra Render: la clave se escribe en el terminal y no se guarda en ningún sitio
python scripts/check_phone_readings.py https://TU-API.onrender.com 42 --login admin --step turn

# 3) Sin red, con un JSON local de lecturas (lista, o {"readings": [...]})
python scripts/check_phone_readings.py --file lecturas.json --step general
```

Pasos de la guía (`--step`), cada uno con su propia medición corta:

| `--step` | Qué se hizo con el celular | Qué se espera |
|---|---|---|
| `rest` | Quieto sobre la mesa, 10 s | módulo de aceleración ≈ 9,8 m/s² (± 0,5), giro ≈ 0 °/s |
| `turn` | Giro de 360° en su sitio | ángulo acumulado ±360° dentro de ±10 % (324° a 396°) |
| `shake` | Agitar 3 s | aceleración máxima ≥ 14,7 m/s² y variación clara |
| `gps` | Caminar 20 m al aire libre | `lat`/`lon` cambian (10 a 40 m), `accuracy_m` plausible y no constante |
| `continuity` | 60 s | duración ≥ 55 s, `seq` sin huecos, `t_ms` creciente, sin saltos de más de 2 s |
| `cut` | Modo avión 10 s | `seq` sin huecos ni repetidos tras reenviar, `t_ms` creciente |
| `general` (defecto) | cualquiera | solo integridad y señales de dato falso |

Opciones útiles: `--window INICIO FIN` (analiza un tramo, en segundos desde la primera lectura),
`--bias DPS` (sesgo del giroscopio a restar), `--user-agent "..."` (el `navigator.userAgent` del
celular; la API no lo guarda), `--json` (informe en JSON).

Código de salida: `0` apto (o con avisos), `1` alguna comprobación falló, `2` error de uso o de red.

## Contra Render sin guardar la contraseña

1. Usa `--login USUARIO`: el script pide la clave con `getpass` (no se ve al escribir), la envía solo a
   `POST /api/auth/login`, se queda con el token **en memoria** y descarta la clave. No imprime ni el
   token ni la clave.
2. Alternativa: pon el token en la variable de entorno `VELOCISTA_TOKEN` solo para esa sesión del
   terminal (`$env:VELOCISTA_TOKEN = "..."`) y ciérrala al terminar. Nunca lo escribas en un archivo, en
   la línea de comandos ni en el chat. Los tokens caducan (60 min por defecto).
3. El script rechaza `http://` fuera de localhost para que el token no viaje sin cifrar
   (`--allow-insecure` lo permite bajo tu responsabilidad).
4. Es de solo lectura, pero recuerda las reglas de EN-32: pruebas cortas en Render y borrar después las
   mediciones de prueba (`DELETE /api/measurements/{id}`).

## Qué marca cada resultado

`[OK]` cumple · `[AVISO]` sospechoso, revisar · `[FALLA]` no cumple · `[INFO]` dato para el lector.
`RESULTADO: NO APTO` si hay alguna `FALLA`; `APTO CON AVISOS` si solo hay avisos.

Las tolerancias salen de `requirements.md` (requisito 9) y están al principio del script como
constantes. Pruebas: `python -m pytest tests/unit/scripts -q`.
