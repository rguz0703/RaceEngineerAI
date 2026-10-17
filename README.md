# RaceEngineerAI

Ingeniero de carrera para sim racing: captura telemetría del simulador, analiza
tus vueltas y te dice dónde y cómo mejorar, en vivo o después de la sesión.

> Estado: **Fase 2** (adaptador de memoria compartida de Assetto Corsa y volcador
> crudo). El adaptador de AC **aún no está verificado con el juego**. Ver
> [docs/architecture.md](docs/architecture.md) y la guía de la PC en
> [docs/pc-setup.md](docs/pc-setup.md).

## Estructura

```
agent/   Agente Python: captura, almacenamiento, análisis y servidor (corre en la PC de juego)
web/     Dashboard web (Fase 5)
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
uv run raceengineer laps 1            # tiempos aproximados por vuelta de la sesión 1
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
