# Mediciones con el celular — backend (Sprint 2, semanas 8 a 10)

Ítems: **EN-32** (ingesta), **EN-33** (base de datos), **EN-34** (perímetro, área y cierre),
**EN-35** (odometría y calibración), **SP-06** (error del GPS), **SP-07** (modelo de precisión),
**EN-37 / EN-38** (pruebas). Casos de uso: CU-1, CU-2, CU-3, CU-4.

Todo en **metros** y **milisegundos** (las pistas de `tracks` siguen en cm).

---

## 1. Idea general

El celular **no calcula nada**: solo envía lo que miden sus sensores. El backend guarda las
lecturas crudas, aplica la calibración y calcula. Así:

- todos los cálculos se prueban en un solo lugar (pruebas automáticas en Python);
- se puede **recalcular** una medición vieja con una calibración mejor (lo usa SP-07);
- el frontend solo muestra resultados.

```
Celular (web)            Backend (FastAPI)                              PostgreSQL
─────────────            ─────────────────                              ──────────
calibrar  ───────────►  /api/calibrations/{celular}/gyro | step | car ─► sensor_calibration
empezar   ───────────►  /api/measurements                    (copia la calibración) ─► measurement
cada 0,5 s ──────────►  /api/measurements/{id}/readings      (valida, descarta)  ─► measurement_reading
terminar  ───────────►  /api/measurements/{id}/finish        (calcula EN-34)     ─► measurement.result
prueba GPS ──────────►  /api/gps-trials                      (SP-06)             ─► gps_trial
modelo    ───────────►  /api/precision-model/runs            (SP-07)             ─► precision_model_run
```

## 2. Base de datos (EN-33) — migración `0009`

| Tabla | Qué guarda | Claves |
|---|---|---|
| `measurement` | Una medición: método (`steps`, `gps`, `car`), fuente (`phone`, `simulator`, `robot`), montaje (`hand`, `robot`), lugar, plano de referencia (JSON, escala 1:N), lado medido con cinta, **copia de la calibración usada**, estado y resultado (JSON + columnas `perimeter_m`, `area_m2`, `closure_error_pct`, `quality` para listar). | `id`; índice por `device_id` |
| `measurement_reading` | Cada lectura: `seq`, `t_ms`, `kind` (`motion`, `gps`, `corner`), giroscopio, acelerómetro x/y/z, paso, PWM, lat, lon, precisión. | **único (`measurement_id`, `seq`)**: reenviar un lote no duplica |
| `sensor_calibration` | Calibraciones de cada celular: `gyro_bias`, `step_length`, `car_speed`; `origin` = `manual` o `model` (SP-07). La más reciente de cada tipo es la vigente. | índice por `device_id` |
| `gps_trial` | Pruebas de SP-06: lugar, entorno (`open`, `buildings`, `trees`, `indoor`), distancia con cinta, lecturas del inicio y del fin, errores calculados. | índice por `device_id` |
| `precision_model_run` | Corridas de SP-07: mediciones usadas, error por intento, parámetros antes y después, si se aplicaron. | índice por `device_id` |

Nombres en inglés como el resto del backend (backlog: `medicion` = `measurement`,
`lectura_medicion` = `measurement_reading`).

## 3. Ingesta (EN-32): qué envía el celular

`POST /api/measurements/{id}/readings` con hasta 1000 lecturas por envío. Lo recomendado es cada **0,5 s**.

```json
{ "readings": [
  { "seq": 0, "t_ms": 1730592000000, "kind": "motion",
    "gyro_z_dps": 0.42, "accel": [0.12, 0.31, 9.79] },
  { "seq": 1, "t_ms": 1730592000020, "kind": "gps",
    "lat": -8.11160, "lon": -79.02870, "accuracy_m": 4.8 },
  { "seq": 2, "t_ms": 1730592003000, "kind": "corner" }
]}
```

| Campo | De dónde sale en el navegador |
|---|---|
| `gyro_z_dps` | `DeviceMotionEvent.rotationRate.alpha` (°/s, giro con el celular plano; positivo = antihorario) |
| `accel` | `DeviceMotionEvent.accelerationIncludingGravity` `[x, y, z]` en m/s² |
| `lat`, `lon`, `accuracy_m` | `navigator.geolocation.watchPosition(..., {enableHighAccuracy: true, maximumAge: 0})` → `coords.latitude`, `coords.longitude`, `coords.accuracy` |
| `corner` | botón "Marcar esquina" |
| `pwm` | solo carro + celular: PWM del motor en % |

- `seq` empieza en 0 y sube de 1 en 1. Si un envío falla, **se reenvía igual**: lo repetido se ignora.
- Una lectura inválida no rechaza el lote: se descarta y la respuesta dice por qué:
  `{"accepted": 24, "duplicates": 0, "discarded": {"gps_out_of_range": 1}, "total_readings": 1573}`.
- Medido: un lote de 25 lecturas tarda **~31 ms** (máx. 38 ms), muy por debajo de 1 s.
- En iPhone hay que pedir permiso con `DeviceMotionEvent.requestPermission()` tras un toque. El
  GPS y los sensores solo funcionan con **HTTPS**.
- Comprobar las unidades una vez: girar el celular 90° a la izquierda sobre la mesa debe sumar
  unos +90 en `gyro_z_dps` integrado. Si da ~1,57, el navegador manda rad/s.

## 4. Cálculos

### 4.1 Calibración (EN-35), antes de medir

| Qué | Cómo | Fórmula |
|---|---|---|
| Sesgo del giroscopio | Celular quieto sobre la mesa ≥ 3 s (30+ lecturas) | `sesgo = promedio(giro)`; si la desviación > 1 °/s → "el celular se movió" |
| Largo del paso | Caminar 20 m medidos con cinta, **3 veces** | `paso = distancia / pasos`, promedio de los 3; aviso si varían > 2 cm |
| Velocidad del carro (sin encoders) | Recorrer distancias medidas con distintos PWM | mínimos cuadrados `v = k·PWM + c` |

Si se envían las lecturas de la caminata de calibración en vez del número de pasos, el backend
cuenta los pasos con **el mismo detector** que usará al medir. Así un error del detector se
compensa en el largo del paso.

### 4.2 Recorrido (odometría)

1. **Pasos**: picos de `|a| − g`, suavizado en 3 muestras. Cuenta un paso al pasar 1,2 m/s² y
   se vuelve a armar al bajar de −0,6 m/s² (histéresis), con al menos 300 ms entre pasos.
2. **Rumbo** θ: se integra el giroscopio menos el sesgo (regla del trapecio).
3. **Posición**: por cada paso, `x += L·cos θ`, `y += L·sin θ`. Con el carro, `L = (k·PWM + c)·Δt`.

### 4.3 Medidas (EN-34)

| Medida | Cálculo |
|---|---|
| Error de cierre | distancia entre el punto final y el inicial; **%** = cierre / largo recorrido × 100 |
| Semáforo | verde < 3 %, amarillo 3 a 6 %, rojo > 6 % |
| Corrección de deriva | si el giro total está a ±45° de 360°, el sobrante es deriva del giroscopio y se reparte **en proporción al tiempo**. Por eso, al terminar, la persona debe volver a mirar hacia donde empezó |
| Corrección de cierre | regla de **Bowditch**: el error que queda se reparte en proporción a la distancia caminada |
| Polígono | si se marcaron esquinas, los vértices son el inicio y las esquinas; si no, todo el trazo |
| Perímetro / área | suma de lados / **fórmula de Gauss** (sirve para figuras cóncavas, p. ej. en L) |
| Escala con cinta | si se midió el primer lado (inicio → primera esquina), todo se escala a esa medida |
| Plano 1:N | el plano dibujado se lleva a tamaño real × N y se compara (% de error de perímetro y área) |
| GPS → metros | plano local: `x = Δlon·R·cos(lat₀)`, `y = Δlat·R` (error < 1 cm en cientos de metros) |

### 4.4 GPS (SP-06)

Cómo **mejora la precisión el celular** (lo que pidió el profesor):

1. Se descartan las lecturas con precisión informada peor que 25 m o que 3 veces la mediana.
2. Quedarse quieto unos 20 s en cada punto y **promediar**.
3. **Promedio filtrado**: se usan las lecturas con precisión ≤ la mediana, ponderadas por 1/precisión².
4. En un recorrido se aplica un **filtro de Kalman con suavizado RTS**, que aprovecha que una
   persona no salta 10 m de golpe.

Cada prueba (`POST /api/gps-trials`) devuelve el error frente a la cinta con 3 métodos:
`single` (una lectura, como una app de taxi), `mean` y `filtered`. El resumen
(`GET /api/gps-trials/summary?target_pct=10`) da:

- error medio y máximo, y el % de mejora frente a una sola lectura;
- `min_side_m`: el **lado mínimo** de terreno para que el GPS se equivoque menos del 10 %.
  Se calcula como `error máximo / 0,10`. Ejemplo: con 5 m de error, hacen falta lados de 50 m.

Una medición GPS en un lugar más chico que eso avisa `gps_space_too_small`: hay que usar pasos.

**CU-4: desde qué tamaño sirve el GPS** (`GET /api/gps-trials/summary`, detalle en
[CONTRACT.md](CONTRACT.md)). Además del lado mínimo global, el resumen da:

- el **lado mínimo por entorno** (`environments`), con `enough_data` falso si hay menos de
  `min_trials` pruebas (por defecto 5) y avisos en `warnings`;
- el **error frente a la distancia** (`by_distance`, `error_trend`): comprueba si el error en
  metros no crece con la distancia, que es lo que supone la regla «error máximo ÷ 10 %»;
- el **umbral de precisión para esperar antes de medir** (`by_accuracy`, `recommended_accuracy_m`)
  y **cuánto quedarse quieto** (`by_wait`);
- la **precisión que informa el celular frente al error real** (`reported_vs_real`);
- una `conclusion` en español generada con los datos.

El error objetivo, el mínimo de pruebas y los umbrales no están fijos en el código: se cambian con
`GPS_TARGET_PCT`, `GPS_MIN_TRIALS`, `GPS_ACCURACY_THRESHOLDS_M`, `GPS_WAIT_SECONDS` y
`GPS_DISTANCE_BANDS_M` (ver `.env.example`) o con los parámetros `target_pct` y `min_trials`.
El giroscopio queda fuera por ahora. Para concluir con datos reales hacen falta pruebas en lugares
conocidos, de varias distancias, al menos 5 por entorno.

### 4.5 Modelo de precisión (SP-07)

Es un **ajuste por refuerzo simple** (prueba y error con castigo, del tipo Twiddle):

- **Acción**: subir o bajar un poco un parámetro (sesgo del giroscopio, largo del paso o `k` del carro).
- **Castigo**: error de cierre % + |error del perímetro frente al plano| %, promedio de todas
  las mediciones repetidas del mismo lugar, **recalculadas** con los parámetros nuevos.
- Si el castigo baja, se queda con el cambio y da pasos más grandes. Si sube, prueba la dirección
  contraria. Si tampoco mejora, achica el paso.
- **Validación**: la última medición no se usa para ajustar, se aparta para comprobar si el
  modelo generaliza (`generalizes`).
- El modelo **no cambia el cálculo base**: solo reajusta parámetros. Con `apply: true` los guarda
  como calibración (`origin: model`), y solo si mejoró.

> ⚠️ **Corrección importante sobre el prototipo**: el modelo del prototipo ajustaba el
> "factor de escala" (largo del paso) para bajar el **error de cierre**. Eso no funciona: el
> error de cierre en % **no cambia** con el largo del paso, porque estira por igual el recorrido
> y la distancia final. El largo del paso solo se corrige comparando con un plano o una cinta,
> y el error de cierre se corrige con el **sesgo del giroscopio**. Por eso el castigo usa los dos
> errores. Para SP-07 hace falta medir un lugar **con medidas conocidas**.

La **evaluación** (algoritmo solo frente a modelo, curva por intento y resultados con datos
reales) está en [EVALUACION_MODELO.md](EVALUACION_MODELO.md):
`POST /api/precision-model/evaluations`.

## 5. Precisión comprobada (simulador de pruebas, no datos reales)

| Prueba | Resultado |
|---|---|
| Aula 10 × 6 m por pasos, calibrado | perímetro +0,3 %, área −2,6 %, cierre 0,01 % → verde |
| Giroscopio con sesgo 0,5 °/s **sin** calibrar | cierre 4,7 % (amarillo); deriva detectada 15,7° y corregida |
| Paso mal calibrado (0,77 en vez de 0,70) | perímetro +10,7 % → con lado medido con cinta −4,2 % |
| Figura cóncava en L | perímetro 0,0 %, área +4,2 % |
| GPS en cancha 80 × 48 m (ruido 3 m) | perímetro +1,2 %, área +3,4 % |
| GPS en aula 10 × 6 m | avisa "lugar chico para el GPS" |
| Error GPS: 1 lectura frente a promedio filtrado | 6,0 m → 1,7 m (72 % menos) |
| Modelo SP-07 (paso y sesgo mal calibrados) | castigo 14,5 → 1,2; recupera paso 0,69 (real 0,70) y sesgo 0,42 (real 0,40); generaliza |

**Límite conocido**: cada lado se cuenta en pasos enteros (±1 paso ≈ ±0,7 m). En lados de
10 m eso es ~7 %, en lados de 30 m ~2 %. Conviene medir con cinta el lado más largo.

**Lo que falta: datos reales.** Estos números vienen del simulador. SP-06 y HU-39/HU-40 deben
repetirse con el celular en el aula y en la cancha, con medidas tomadas con cinta.

## 6. Pruebas

```bash
pytest tests/unit/domain/measurements             # 70 pruebas del dominio (sin base de datos)
pytest tests/integration/rest/measurements        # 17 pruebas de la API con PostgreSQL real
```

Resultado en la rama: **537 pruebas pasan, 0 fallan**. Las 2 que dan error (`test_external_persistence.py`,
`test_sim_integration.py`) también fallan en `main`, porque falta el paquete `jsonschema` en el
entorno local (`pip install -e ".[dev]"` lo instala).

## 7. Pendiente para el equipo

- **Jara (EN-32, HU-37)**: la página del celular debe enviar las lecturas con el formato de la
  sección 3 y mostrar el resultado de `/finish`.
- **Pedro (EN-34, HU-34, HU-42)**: revisar los cálculos de la sección 4 (son los de EN-34) y
  `GET /api/gps-trials/summary` para el gráfico de HU-42.
- **Equipo**: confirmar los umbrales (3 % y 6 %, 25 m de precisión, 10 % para el GPS); son
  propuestas pendientes del PO.
- **Aviso aparte**: `alembic check` encuentra diferencias que ya estaban antes de este cambio, en
  `external_telemetry` (único `session_id, seq`) y `lap_segment.accumulated_error`. No vienen de
  esta rama.
