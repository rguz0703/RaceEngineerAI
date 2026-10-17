"""Command-line entry point."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from raceengineer import __version__
from raceengineer.adapters.fake import FakeSource
from raceengineer.capture.recorder import Recorder
from raceengineer.storage.sqlite import SqliteSessionRepository

DEFAULT_DB = Path("data") / "sessions.sqlite"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="raceengineer",
        description="RaceEngineerAI: telemetría y coaching para sim racing.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB, help=f"base de datos (por defecto {DEFAULT_DB})"
    )
    commands = parser.add_subparsers(dest="command")

    record = commands.add_parser("record", help="grabar una sesión")
    record.add_argument("--source", choices=["fake"], default="fake", help="fuente de telemetría")
    record.add_argument("--laps", type=int, default=3, help="vueltas a generar (fuente fake)")
    record.add_argument("--seed", type=int, default=0, help="semilla (fuente fake)")

    commands.add_parser("sessions", help="listar sesiones grabadas")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "record":
        return _record(args.db, laps=args.laps, seed=args.seed)
    if args.command == "sessions":
        return _sessions(args.db)
    parser.print_help()
    return 0


def _record(db: Path, laps: int, seed: int) -> int:
    source = FakeSource(laps=laps, seed=seed)
    with SqliteSessionRepository(db) as repository:
        result = Recorder(source, repository).record()
    print(f"Sesión {result.session_id} grabada: {result.sample_count} muestras en {db}")
    return 0


def _sessions(db: Path) -> int:
    if not db.exists():
        print(f"No hay sesiones todavía ({db} no existe).")
        return 0
    with SqliteSessionRepository(db) as repository:
        records = repository.list_sessions()
    if not records:
        print("No hay sesiones todavía.")
        return 0
    print(f"{'ID':>4}  {'Inicio (UTC)':<19}  {'Sim':<6}  {'Circuito':<16}  {'Coche':<12}  Muestras")
    for r in records:
        started = r.started_at.strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"{r.id:>4}  {started:<19}  {r.info.sim:<6}  {r.info.track:<16}  "
            f"{r.info.car:<12}  {r.sample_count}"
        )
    return 0
