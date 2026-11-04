# Estudio v2: el celular como única fuente de datos del coche

Fecha: 2026-11-03. Estado: borrador para decidir. No se ha tocado ningún repositorio.

**Aclaración del usuario que cambia el diseño:** el coche no tiene sensores ni electrónica, solo corre. El celular, montado sobre él, aporta **todo** lo que tiene: giroscopio, acelerómetro y GPS. Esta versión reemplaza a la v1 (que suponía un robot con sensores al lado).

## 1. Cómo funciona hoy (verificado en el código)

- `velocista-sim` (Railway) emite `hello`, `telemetry` a 50 Hz, `event`, `catalog` y `config`. El backend se conecta **hacia afuera** como cliente y guarda `external_session`, `run`, `lap` y `external_telemetry`, con submuestreo (1 de cada 5), tope de 20.000 filas por corrida y solo con corrida abierta (ADR-005).
- Ese contrato está fijado y exige **sensores de línea** (`line_sensors >= 1`), motores y batería; `source` solo puede ser `sim` o `robot`.
- La tabla `run` exige robot, versión, ajuste PID y perfil, y `source` solo `sim` o `robot`.

## 2. Qué implica para el celular

- **No se puede imitar al simulador:** el celular no tiene sensores de línea, motores, batería ni PWM. Forzarlo obligaría a cambiar un contrato fijado y a inventar datos.
- **No se debe forzar una `run`:** necesitaría un robot, un ajuste PID y un perfil que el coche no tiene.
- **Sí existe el diseño correcto:** el PR #8 (EN-33, `docs/MEDICIONES.md`) define la **medición** (`measurement`) como entidad propia e independiente de la corrida: método `car`, montaje `robot`, fuente `phone`, lecturas crudas, calibración y cálculos en el backend. Es exactamente "celular sobre el coche".

## 3. Qué datos da un celular y para qué sirven

| Dato | API del navegador | Qué se calcula | Calidad |
|---|---|---|---|
| Giro (°/s) | `DeviceMotionEvent.rotationRate`, ~60 Hz | Rumbo por integración; curvas; vueltas | Buena en el corto plazo; deriva con el tiempo (se corrige, EN-35) |
| Aceleración (m/s²) | `DeviceMotionEvent.accelerationIncludingGravity` | Fuerza lateral y longitudinal, frenadas, vibración | Buena. La velocidad por integración **deriva** |
| Posición, velocidad, precisión | `Geolocation` con `enableHighAccuracy`, ~1 Hz | Trayectoria y distancia al aire libre; velocidad (`coords.speed`) | 3 a 10 m de error; peor bajo techo. La velocidad es más fiable que la posición |
| Orientación absoluta | `DeviceOrientationEvent` (brújula) | Rumbo sin deriva | Ruidosa cerca de metal o motores |

Qué se obtiene de todo eso: velocidad (máxima y media), distancia, trayectoria, rumbo, fuerza lateral en curvas, número de vueltas y **tiempo por vuelta**. Como el celular tiene un solo reloj, los tiempos por vuelta son consistentes entre sí.

Qué **no** se obtiene: error de línea, sensores de línea, PWM, batería, ni comandos al coche (arrancar, parar, PID). La consola no puede controlar un coche que no tiene electrónica.

## 4. Opciones

| | A. REST por lotes (EN-32) + retransmisión en vivo | B. WebSocket del celular al backend | C. Imitar el contrato del simulador |
|---|---|---|---|
| Reutiliza lo hecho | **Casi todo** (tablas, validación, cálculos) | Solo las tablas | Nada |
| Tolera cortes de red | **Sí** (reenvío sin duplicar por `seq`) | Hay que reconstruirlo | Hay que reconstruirlo |
| Ver en vivo | Sí, con retransmisión | Sí | Sí |
| Riesgo | Bajo | Medio | **Alto**: rompe un contrato fijado |

## 5. Recomendación

1. **Medición como entidad principal, sin `run`.** El celular crea una medición (`method=car`, `mounting=robot`, `source=phone`) y envía lotes. No se toca el contrato del simulador ni la tabla `run`.
2. **Ingesta por lotes cada 0,5 s (EN-32)** más **retransmisión en vivo** a la consola desde la fase 1, porque ahora el celular es la única fuente y la consola necesita verlo. Latencia esperada: de 0,5 s a 1 s.
3. **Cálculos en el backend**, no en el celular (EN-34 y EN-35): rumbo, trayectoria, distancia, velocidad, fuerza lateral y **vueltas estimadas**. El celular solo envía datos crudos.
4. **Fusión GPS + IMU** al aire libre (filtro de Kalman con suavizado, ya definido en SP-06). Bajo techo, solo IMU.
5. **Sin comandos al coche.** El celular solo mide.
6. El **simulador sigue** como fuente para desarrollar sin hardware.

## 6. Flujo de uso

1. Fijar el celular **plano** y alineado con el eje del coche, con soporte firme.
2. Abrir la página del celular por **HTTPS**. En iPhone, tocar para dar el permiso de movimiento.
3. **Calibrar:** coche quieto 3 s o más (sesgo del giroscopio).
4. **Iniciar medición** en el celular. La consola muestra el estado en vivo.
5. Correr. El celular envía lotes con giroscopio, acelerómetro y GPS.
6. **Terminar:** el backend calcula y guarda el resultado; la consola muestra velocidad, trayectoria, vueltas y tiempos por vuelta.

## 7. Riesgos y límites

- **Pista de interior:** con una pista de 3×2,5 m el GPS no sirve. Todo dependería del giroscopio y el acelerómetro, que derivan. Hay que decir en el informe que en interior el resultado es **estimado**.
- **GPS al aire libre:** 3 a 10 m de error. Para una pista pequeña solo es útil la velocidad.
- **Peso y vibración:** el celular debe ir muy bien sujeto; la vibración del coche ensucia el acelerómetro.
- **Pantalla y segundo plano:** el navegador frena las páginas ocultas. Hay que mantener la pantalla encendida (Screen Wake Lock) y no cambiar de aplicación.
- **Red:** el celular necesita datos móviles o WiFi hacia el backend. La base gratuita de Render **ya se llenó una vez**: tope y retención desde el inicio.
- **Render gratuito** tarda en despertar: abrir la página y esperar antes de correr.
- **Vueltas estimadas** no sustituyen al cronómetro oficial (ESP32): son un diagnóstico.
- **Choque de migraciones:** el PR #8 trae `0008_measurements`, que choca con la `0008_track_metrics` ya fusionada. Hay que renumerarla a `0009` antes de construir encima.
- **Privacidad:** el GPS es dato de ubicación. Debe ser opcional y borrarse con la medición.

## 8. Qué NO cambia

Simulador, contrato de `velocista-sim`, tabla `run`, ADR-005 de telemetría, la ingesta del robot real (`/ws/robot`) y el cronómetro (`/ws/timer`).

## 9. Preguntas pendientes

1. ¿La pista es de interior o de exterior? Define si se usa GPS.
2. ¿Qué debe ver el piloto en vivo: solo velocidad y rumbo, o también la trayectoria dibujada sobre el plano del trazador?
3. ¿Las vueltas y sus tiempos se aceptan como estimados (diagnóstico) o hay que compararlos con el cronómetro?
4. ¿Cuánto tiempo se guardan las lecturas crudas (retención)?

## 10. Casos de uso CU-1 a CU-5 con solo el celular (el coche solo desplaza)

| Caso | Con solo el celular | Qué lo lleva | Límite |
|---|---|---|---|
| CU-1 Aula y plano a escala | Sí | Persona caminando el borde con el celular (pasos + giroscopio) | GPS inútil en un aula; se usa el error de cierre |
| CU-2 Mapear la pista | Sí, en parte | Coche con el celular encima | Sin encoders ni PWM no se conoce el avance: sale bien el rumbo, los ángulos y el tiempo por vuelta; el largo de cada tramo no |
| CU-3 Áreas cóncavas | Sí | Puntos y ángulos marcados desde la web | No necesita coche |
| CU-4 Error del GPS | Sí | Celular quieto en sitios con distancia medida con cinta | No necesita coche; exterior |
| CU-5 Plano desde lados y ángulos | Sí, sin celular | Geometría en el backend | Nada que medir |

Salidas para el avance del coche (CU-2): (1) velocidad media = largo conocido de la pista ÷ tiempo de vuelta (da forma y ángulos; la escala la pone el plano); (2) GPS al aire libre con `coords.speed`; (3) sensor de rueda barato, fuera de este sprint.

Aviso: la optimización (Twiddle y bayesiana) del siguiente sprint necesita error de línea, sensores y PWM, que un coche sin electrónica no produce; solo valdrá con el robot real o el simulador.

Cambio pendiente en el spec: Requirement 4.3 debe incluir la velocidad media a partir del largo conocido de la pista, marcada como estimación.

## 11. La página del celular ya existe (verificado 2026-11-03)

PR #6 del frontend, rama `feature/SP-06-medicion-celular`, abierto y sin fusionar, de una compañera. Un solo archivo, `public/celular/index.html` (1208 líneas, HTML y JavaScript sin React), servido por el sitio estático del frontend en `/celular/`. Ya hace: inicio de sesión, permiso de movimiento en iPhone, GPS, Wake Lock, calibración (giroscopio, pasos y coche), medición con lotes y cierre, historial, pruebas de GPS y modelo de precisión. Usa la paleta de la consola.

Huecos frente a este spec: usa `--dim` para texto (no cumple contraste), no tiene modo interior, guarda el token en `localStorage`, no hay retransmisión en vivo, depende del PR #8 y no tiene pruebas. Su calibración del coche usa PWM, que un coche sin electrónica no tiene. El punto F1 pasa de "construir la página" a "revisar y extender la página existente", de acuerdo con su autora.

## 12. Corrección sobre el tope de lecturas (2026-11-03)

Mi revisión inicial dijo que la rama de EN-33 no tenía tope por medición. Era incorrecto: `READINGS_MAX = 200_000` (`src/velocista/domain/measurements/validation.py`) y `use_cases.ingest` rechaza el lote entero con 409 `measurement_too_many_readings`. Lo que falta frente al spec: tope configurable, valor de 20.000 (hoy 10 veces mayor), indicador `readings_capped` y retención (no existe nada). Esfuerzo estimado por el agente: tope configurable unos 0,5 día; retención entre 0,5 y 1 día.

## 13. EN-32 frente a la rama de la compañera (verificado 2026-11-03)

EN-32 ya está implementada en `feat/EN-33-mediciones-celular` (PR #8): por REST, con `POST /api/measurements/{id}/readings`. Cumple la validación con descarte y registro, la unicidad por `seq` y Swagger. No cumple del todo: el canal es REST y no un tipo de mensaje del WebSocket; el montaje (mano o robot) es de la medición y no de cada lectura; `docs/CONTRACT.md` no la menciona; el tiempo menor de 1 s está medido a mano (unos 31 ms por lote de 25) pero no hay prueba automática. Falta: documentarla en el contrato, añadir la prueba de tiempo y que el PO decida las dos diferencias. El resto de este estudio amplía EN-32 y queda fuera de ese ítem.

### 13.1 Revisión de las lecturas reales de una compañera (2026-11-04)

Origen: el volcado de datos de las mediciones de campo (19 mediciones, 30 257 lecturas, dos celulares), cargado en una base temporal aislada del contenedor local y revisado con `scripts/check_phone_readings.py`. Base temporal y API del puerto 8001 eliminadas al terminar. No se registran coordenadas ni nombres de lugares.

- Resultado: las 19 mediciones salen APTO, sin FALLA ni AVISO.
- Módulo medio de aceleración 9,94 a 10,11 m/s² en las 14 mediciones por pasos (gravedad más movimiento al caminar).
- Movimiento a 60 Hz; GPS a 0,6 a 2 Hz con precisión de 3 a 14,6 m; cero huecos y cero repetidos en `seq`; sin retrocesos de `t_ms`.
- Señales de dato real: desviación de la aceleración de 0,4 a 2,5 m/s², del giro de 9 a 34 °/s, intervalos con variación (no es un reloj perfecto), ninguna lectura de aceleración nula.
- Ángulos acumulados de −280° a −365° en las mediciones cerradas (recorrido cerrado en sentido horario); −614° y −1103° en las de 2 y 3 vueltas.
- Límite: son caminatas de campo. No evalúan el reposo de 10 s, la vuelta exacta de 360° ni la sacudida de la guía (paso `--step` del script), que requieren las pruebas cortas con el celular. El `user-agent` no se guarda en la API: no se puede confirmar solo con los datos.
- Estas lecturas vienen de la laptop de una compañera; no prueban el envío desde la página desplegada en Render (punto D del plan).
