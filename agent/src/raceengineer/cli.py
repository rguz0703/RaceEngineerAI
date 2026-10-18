"""Command-line entry point."""

import argparse
import signal
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from threading import Event
from types import FrameType

from raceengineer import __version__
from raceengineer.adapters import ac_shared_memory
from raceengineer.adapters.ac_raw_dump import RawDumpReader, dump_raw
from raceengineer.adapters.ac_shared_memory import (
    ACNotRunningError,
    ACSharedMemorySource,
    SharedMemoryReader,
)
from raceengineer.adapters.fake import FakeSource
from raceengineer.analysis.laps import segment_laps
from raceengineer.capture.recorder import Recorder
from raceengineer.domain.models import Lap
from raceengineer.domain.ports import TelemetrySource
from raceengineer.storage.sqlite import SqliteSessionRepository

DEFAULT_DB = Path("data") / "sessions.sqlite"
DEFAULT_DUMP_DIR = Path("data") / "dumps"

# Overridable in tests, where no game is running.
open_ac_reader: Callable[[], SharedMemoryReader] = ac_shared_memory.open_live_reader


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
    record.add_argument(
        "--source",
        choices=["fake", "ac", "ac-dump"],
        default="fake",
        help="fake: sintética; ac: Assetto Corsa en vivo; ac-dump: un volcado crudo",
    )
    record.add_argument("--laps", type=int, default=3, help="vueltas a generar (fuente fake)")
    record.add_argument("--seed", type=int, default=0, help="semilla (fuente fake)")
    record.add_argument(
        "--poll-hz", type=float, default=120.0, help="lecturas por segundo (fuente ac)"
    )
    record.add_argument("--input", type=Path, help="archivo de volcado (fuente ac-dump)")

    commands.add_parser("sessions", help="listar sesiones grabadas")

    laps = commands.add_parser(
        "laps", help="vueltas de una sesión: tiempo, tipo y si te saliste de pista"
    )
    laps.add_argument("session_id", type=int)

    dump = commands.add_parser(
        "dump-raw", help="guardar los bytes crudos de la memoria compartida de Assetto Corsa"
    )
    dump.add_argument("--seconds", type=float, default=60.0, help="duración (por defecto 60)")
    dump.add_argument("--poll-hz", type=float, default=200.0, help="lecturas por segundo")
    dump.add_argument(
        "--output",
        type=Path,
        help=f"archivo de salida (por defecto {DEFAULT_DUMP_DIR}/ac-<fecha>.acraw.gz)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "record":
            return _record(args)
        if args.command == "sessions":
            return _sessions(args.db)
        if args.command == "laps":
            return _laps(args.db, args.session_id)
        if args.command == "dump-raw":
            return _dump_raw(args)
    except ACNotRunningError as exc:
        print(f"Error: {exc}")
        return 1
    parser.print_help()
    return 0


@contextmanager
def _stop_on_ctrl_c() -> Iterator[Event]:
    """Turn Ctrl+C into a stop request so recordings finish and flush cleanly."""
    stop = Event()

    def handler(_signum: int, _frame: FrameType | None) -> None:
        stop.set()

    previous = signal.signal(signal.SIGINT, handler)
    try:
        yield stop
    finally:
        signal.signal(signal.SIGINT, previous)


def _record(args: argparse.Namespace) -> int:
    if args.source == "ac-dump" and args.input is None:
        print("Error: --source ac-dump necesita --input <archivo>")
        return 2
    with _stop_on_ctrl_c() as stop:
        reader: SharedMemoryReader | None = None
        source: TelemetrySource
        if args.source == "fake":
            source = FakeSource(laps=args.laps, seed=args.seed)
        elif args.source == "ac":
            reader = open_ac_reader()
            source = ACSharedMemorySource(reader, poll_hz=args.poll_hz, stop=stop)
            print("Grabando Assetto Corsa. Pulsa Ctrl+C para terminar.")
        else:
            dump = RawDumpReader(args.input)
            reader = dump
            source = ACSharedMemorySource(dump, stop=stop, clock=dump.clock, sleep=_no_sleep)
        try:
            with SqliteSessionRepository(args.db) as repository:
                result = Recorder(source, repository).record(stop)
        finally:
            if reader is not None:
                reader.close()
    print(f"Sesión {result.session_id} grabada: {result.sample_count} muestras en {args.db}")
    return 0


def _dump_raw(args: argparse.Namespace) -> int:
    output: Path = args.output or DEFAULT_DUMP_DIR / (
        f"ac-{datetime.now().strftime('%Y%m%d-%H%M%S')}.acraw.gz"
    )
    with _stop_on_ctrl_c() as stop:
        reader = open_ac_reader()
        print(f"Volcando memoria compartida durante {args.seconds:g} s (Ctrl+C para parar)...")
        try:
            stats = dump_raw(reader, output, args.seconds, poll_hz=args.poll_hz, stop=stop)
        finally:
            reader.close()
    size_kb = output.stat().st_size / 1024
    print(
        f"Volcado guardado en {output}: {stats.frames} lecturas en {stats.seconds:.1f} s "
        f"({size_kb:.0f} KB)"
    )
    return 0


def _laps(db: Path, session_id: int) -> int:
    if not db.exists():
        print(f"No hay sesiones todavía ({db} no existe).")
        return 0
    with SqliteSessionRepository(db) as repository:
        samples = repository.load_samples(session_id)
    if not samples:
        print(f"La sesión {session_id} no tiene muestras.")
        return 1
    laps = segment_laps(samples)
    rows = [
        (str(lap.number), _lap_time(lap), _lap_kind(lap), "sí" if lap.off_track else "no")
        for lap in laps
    ]
    _print_table(("Vuelta", "Tiempo", "Tipo", "Fuera de pista"), rows)
    if any(not lap.official and lap.time_ms is not None for lap in laps):
        print("≈ tiempo estimado (sesión grabada antes de guardar el tiempo oficial del juego)")
    return 0


def _lap_time(lap: Lap) -> str:
    if lap.time_ms is None:
        return "-"
    return ("" if lap.official else "≈") + _format_ms(lap.time_ms)


def _lap_kind(lap: Lap) -> str:
    if lap.time_ms is None:
        return "sin terminar"
    kinds = [k for k, flag in (("salida", lap.out_lap), ("entrada", lap.in_lap)) if flag]
    if kinds:
        return " + ".join(kinds)
    return "lanzada" if lap.complete else "incompleta"


def _format_ms(ms: int) -> str:
    minutes, rest = divmod(ms, 60_000)
    return f"{minutes}:{rest / 1000:06.3f}"


def _print_table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    widths = [max(len(row[i]) for row in [header, *rows]) for i in range(len(header))]
    for row in [header, *rows]:
        cells = (cell.ljust(width) for cell, width in zip(row, widths, strict=True))
        print("  ".join(cells).rstrip())


def _no_sleep(_seconds: float) -> None:
    pass


def _sessions(db: Path) -> int:
    if not db.exists():
        print(f"No hay sesiones todavía ({db} no existe).")
        return 0
    with SqliteSessionRepository(db) as repository:
        records = repository.list_sessions()
    if not records:
        print("No hay sesiones todavía.")
        return 0
    rows = [
        (
            str(r.id),
            r.started_at.strftime("%Y-%m-%d %H:%M:%S"),
            r.info.sim,
            r.info.track + (f" ({r.info.track_config})" if r.info.track_config else ""),
            r.info.car,
            str(r.sample_count),
        )
        for r in records
    ]
    _print_table(("ID", "Inicio (UTC)", "Sim", "Circuito", "Coche", "Muestras"), rows)
    return 0
