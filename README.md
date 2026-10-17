# RaceEngineerAI

Ingeniero de carrera para sim racing: captura telemetría del simulador, analiza
tus vueltas y te dice dónde y cómo mejorar, en vivo o después de la sesión.

> Estado: **Fase 1** (modelo de dominio, fuente sintética y grabación en SQLite). Todavía no hay integración con
> ningún simulador. Ver [docs/architecture.md](docs/architecture.md).

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
uv run pytest               # tests + cobertura
uv run ruff check .         # lint
uv run ruff format --check .
uv run mypy                 # tipos
```

## Flujo de trabajo

- Mac: diseño y desarrollo. PC Windows: pruebas reales con Assetto Corsa.
- Sincronización vía GitHub (`git push` en un equipo, `git pull` en el otro).
- Una rama por fase; la CI corre en Windows y macOS en cada push.
