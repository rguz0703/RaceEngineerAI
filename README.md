# RaceEngineerAI

Ingeniero de carrera para sim racing: captura telemetría del simulador, analiza
tus vueltas y te dice dónde y cómo mejorar, en vivo o después de la sesión.

> Estado: **Fase 5a** (dashboard web de sesiones grabadas). La captura de Assetto Corsa por
> memoria compartida está verificada con el juego (AC 1.16.4). Ver
> [docs/architecture.md](docs/architecture.md) y la guía de la PC en
> [docs/pc-setup.md](docs/pc-setup.md).

## Estructura

```
agent/   Agente Python: captura, almacenamiento, análisis y servidor (corre en la PC de juego)
web/     Dashboard web (React + TypeScript + uPlot); su build vive en agent/src/raceengineer/api/static
docs/    Requisitos, arquitectura, fases y decisiones
```

## Desarrollo (agente)

Requisitos: [uv](https://docs.astral.sh/uv/) (instala Python 3.12 automáticamente).

```bash
cd agent
uv sync                     # crea el entorno e instala dependencias
uv run raceengineer --version
uv run raceengineer record --laps 3   # graba una sesión sintética (sin simulador)
uv run raceengineer sessions          # lista las sesiones guardadas en data/sessions.sqlite
uv run raceengineer laps 1            # vueltas de la sesión 1: tiempo, tipo, fuera de pista
uv run raceengineer compare 1 3       # vuelta 3 contra tu mejor vuelta limpia, tramo a tramo
uv run raceengineer compare 1 3 --ref 2 --csv data/cmp.csv   # contra la vuelta 2, y a CSV
uv run raceengineer serve             # dashboard en http://127.0.0.1:8000
uv run raceengineer serve --lan       # también accesible desde la Mac o el celular
```

Con Assetto Corsa en pista (solo en Windows, ver [docs/pc-setup.md](docs/pc-setup.md)):

```bash
uv run raceengineer record --source ac          # graba hasta Ctrl+C
uv run raceengineer dump-raw --seconds 30       # guarda los bytes crudos en data/dumps/
uv run raceengineer record --source ac-dump --input data/dumps/<archivo>.acraw.gz
```

Calidad:

```bash
uv run pytest               # tests + cobertura
uv run ruff check .         # lint
uv run ruff format --check .
uv run mypy                 # tipos
```

## Flujo de trabajo

- Mac: diseño y desarrollo. PC Windows: pruebas reales con Assetto Corsa.
- Sincronización vía GitHub (`git push` en un equipo, `git pull` en el otro).
- Una rama por fase; la CI corre en Windows y macOS en cada push.

## Desarrollo (dashboard)

Requisitos: Node.js 22. Solo hace falta para cambiar la web: el build ya está en
el repo y lo sirve `raceengineer serve`.

```bash
cd web
npm ci
npm run dev      # http://localhost:5173, con la API de `raceengineer serve` en el puerto 8000
npm run build    # regenera agent/src/raceengineer/api/static (hay que commitearlo; la CI lo comprueba)
```
