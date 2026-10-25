# RaceEngineerAI — Requisitos, arquitectura y plan

Plan aprobado el 2026-10-16. Este documento es la referencia viva: si una
decisión cambia, se actualiza aquí.

## Contexto

- **Mac:** diseño y desarrollo. No ejecuta simuladores.
- **PC Windows:** Assetto Corsa (original) + Logitech G923. Todas las pruebas reales.
- Ambos en la misma red local → modo "ingeniero de carrera a distancia".
- Código sincronizado vía GitHub; CI en Windows y macOS.
- Destino final: app instalable desde Steam, compatible con varios juegos mediante adaptadores.

## Interfaces de telemetría (investigadas, **no verificadas**)

| Simulador | Interfaz | Notas |
|---|---|---|
| Assetto Corsa | Memoria compartida (`acpmf_physics`, `acpmf_graphics`, `acpmf_static`) | Datos completos. Solo local en Windows. **Elegida para v1. Verificada el 2026-10-17** con AC 1.16.4 (SM 1.7): tiempos de vuelta ±10 ms frente al juego; volante -1 izq. / +1 der.; freno y embrague llegan a 1.0. AC original no marca vueltas inválidas en la memoria compartida: los cortes se detectan con `numberOfTyresOut`. |
| Assetto Corsa | UDP Remote Telemetry (puerto 9996) | Menos campos, un cliente. Alternativa para pruebas rápidas. |
| ACC | Memoria compartida (estructura distinta) | Fase 9+. |
| ACC | Broadcasting UDP | Sin entradas del piloto; solo complemento. |
| AC EVO | Memoria compartida (rehecha en v0.6) | En acceso anticipado; puede cambiar. |

Ninguna integración se considera funcional hasta verificarla en la PC con el juego.

## Requisitos funcionales (★ = v1)

- ★ RF1 Capturar telemetría del simulador en ejecución.
- ★ RF2 Detectar sesión, coche, circuito y segmentar vueltas (out lap, inválida, pit).
- ★ RF3 Guardar sesiones localmente y poder reproducirlas.
- ★ RF4 Comparar dos vueltas alineadas por distancia (delta, velocidad, acelerador, freno, marcha).
- ★ RF5 Dashboard web con sesiones, vueltas y gráficas; visible en vivo desde otro equipo de la red.
- RF6 Detectar pérdidas por curva/sector, frenadas tempranas/tardías, coasting, aceleración tardía.
- RF7 Medir consistencia (dispersión por sector y curva).
- RF8 Recomendaciones personalizadas (reglas propias; posible apoyo en notas de libros).
- RF9 Coach en tiempo real: overlay visual, luego voz.
- RF10 Más simuladores vía adaptadores.

## Requisitos no funcionales

- RNF1 Impacto mínimo en el simulador: captura < 5 % CPU, sin caída de FPS.
- RNF2 Sin pérdida de datos: escritura incremental.
- RNF3 Todo el núcleo se prueba sin simulador (fuentes simuladas y grabaciones).
- RNF4 Extensible: un simulador nuevo = un adaptador nuevo.
- RNF5 Offline y datos locales.
- RNF6 Calidad: tests, cobertura del núcleo ≥ 80 %, ruff, mypy estricto, CI Windows + macOS.
- RNF7 Latencia del coach en vivo < 200 ms.
- RNF8 Interfaz en español, preparada para i18n.
- RNF9 Dependencias con licencias compatibles con distribución comercial (evitar GPL).

## Arquitectura

Núcleo hexagonal (puertos y adaptadores) en Python, ejecutado como agente en la PC de juego.

```
 Adaptadores de entrada: ACSharedMem | ACUdp | ReplaySource | FakeSource
                │  puerto TelemetrySource → TelemetrySample normalizado
 NÚCLEO (Python puro, sin UI ni dependencias de Windows)
   domain/    Session, Lap, Sample, Track, Car
   capture/   Recorder, LapSegmenter
   analysis/  alineado por distancia, delta, curvas, consistencia
   coaching/  reglas → Insight / Recommendation
                │                               │
   puerto SessionRepository              puerto de eventos
   storage/ (SQLite)                     api/ (FastAPI + WebSocket)
                                                │  red local
                                         web/ (React + TypeScript + uPlot)
                                         navegador en Mac / iPad / celular
```

Distribución final: ejecutable Windows (PyInstaller) + ventana nativa (Tauri o
Electron) mostrando la misma interfaz web; publicación en Steam.

### Ventajas
- 90 % del desarrollo y tests en Mac con grabaciones.
- Añadir juegos = añadir adaptadores.
- Modo a distancia sin trabajo extra.

### Desventajas
- Más abstracción inicial.
- Dos lenguajes (Python + TypeScript).
- Captura y servidor deben aislarse para no afectar la frecuencia de muestreo.

## Tecnologías

| Área | Elección |
|---|---|
| Agente | Python 3.12, uv, ctypes/mmap |
| Calidad | pytest, pytest-cov, ruff, mypy |
| Almacenamiento | SQLite (Parquet si el volumen crece) |
| Análisis | numpy, pandas |
| API | FastAPI + WebSocket |
| Web | React + TypeScript + Vite + uPlot |
| CI | GitHub Actions (windows-latest, macos-latest) |
| Empaquetado | PyInstaller + Tauri/Electron |

## Fases

| Fase | Entregable | Verificación | ¿Requiere PC + juego? |
|---|---|---|---|
| F0 | Repo, estructura, uv, lint, tests, CI | CI en verde | No |
| F1 | Dominio, FakeSource, Recorder → SQLite | Tests ida y vuelta | No |
| F2 | Adaptador AC memoria compartida + volcador crudo | Sesión real grabada → fixture | **Sí** |
| F3 | Segmentación de vueltas | Tiempos = juego (±10 ms) con fixtures | No |
| F4 | Comparación de vueltas + informe CLI | Tests numéricos | No |
| F5 | API + dashboard web (local y remoto). F5a: sesiones grabadas; F5b: en vivo (WebSocket, delta contra la mejor vuelta) | Checklist manual + tests | Parcial |
| F6 | Curvas, frenadas, coasting, consistencia | Casos sintéticos + vueltas reales | No |
| F7 | Recomendaciones por reglas | Test por regla | No |
| F8 | Coach en vivo (overlay, luego voz) | Latencia medida | Sí |

F7–F8 (2026-10-21): "radio del ingeniero" con reglas propias en `capture/engineer.py` (sectores en tercios, tiempo de vuelta contra la referencia, la ventana de 250 m donde más se perdió con su causa: frenada antes, menor velocidad mínima, salida más lenta o acelerador tarde; incidentes espaciados 3 s). El servidor genera el texto y la frase hablada; el navegador la lee con `speechSynthesis` (sin dependencias, funciona en la PC y en el celular). Sin IA externa por ahora, por decisión del usuario.
| F9 | Más juegos (un adaptador por juego) | Fixtures por juego | Sí |
| F10 | Instalador, auto-actualización, Steam | Instalación limpia en Windows | Sí |

## Criterios de aceptación v1 (F0–F5)

1. Graba ≥ 10 vueltas de AC sin perder muestras (< 1 % huecos, medido).
2. Vueltas y tiempos coinciden con el juego (±10 ms); out lap e inválidas marcadas.
3. Si el proceso muere, se conservan las vueltas completas previas.
4. Comparar dos vueltas: delta y trazas alineadas por distancia.
5. Sesiones persistentes tras reiniciar.
6. Captura < 5 % CPU en la PC (medido).
7. Núcleo probado sin simulador; cobertura ≥ 80 %; CI verde en Windows y macOS.
8. El dashboard se ve en vivo desde el Mac mientras se conduce en la PC.
9. README con instalación, captura y análisis.

## Riesgos

1. Estructuras de telemetría sin documentación oficial completa y cambiantes por parche.
2. Segmentación de vueltas (reinicios, pit, cortes, salto en la línea de meta).
3. Rendimiento en tiempo real con Python (GIL, jitter).
4. Overlay sobre el juego requiere modo ventana sin bordes.
5. Validar la calidad de las recomendaciones.
6. Empaquetado en Windows (tamaño, antivirus) y requisitos de Steam.
7. Marcas y derechos de autor (logos de juegos, contenido de libros).


## Estilo visual: "Pit wall y cockpit" (2026-10-24)

- Dos modos con el mismo lenguaje. El garaje (análisis) usa carbono cálido (#1F1A17), texto blanco cálido y naranja papaya (#FF7A1A) para la marca y la pestaña activa. El cockpit (pestaña En vivo) es negro puro, como el display de un coche.
- Colores de cronometraje con un único significado: morado = mejor sector de la sesión, verde = mejoraste o ganas tiempo, amarillo = más lento que tu mejor, rojo = solo incidentes (fuera de pista) y grabación.
- Tipografía Archivo (OFL), incluida en el build para funcionar sin internet; los tiempos van en su ancho máximo (font-stretch 125 %).
- Sectores: tercios de la vuelta. Los tiempos por sector se guardan en el índice de vueltas (esquema v8); la vuelta ideal es la suma de los mejores sectores de las vueltas limpias. En vivo, el sector sale morado solo si es el mejor de la grabación y no más lento que la referencia.
