"""Command-line entry point."""

import argparse
import logging
import signal
import socket
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
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
from raceengineer.analysis import lap_index
from raceengineer.analysis.compare import compare_laps, lap_trace, summarize, write_csv
from raceengineer.analysis.laps import best_clean_lap
from raceengineer.capture.recorder import Recorder
from raceengineer.domain.models import Lap, SessionInfo
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

    compare = commands.add_parser(
        "compare", help="comparar una vuelta con otra (por defecto, tu mejor vuelta limpia)"
    )
    compare.add_argument("session_id", type=int)
    compare.add_argument("lap", type=int, help="vuelta a analizar")
    compare.add_argument("--ref", type=int, help="vuelta de referencia")
    compare.add_argument(
        "--ref-session", type=int, help="sesión de la referencia (por defecto, la misma)"
    )
    compare.add_argument("--csv", type=Path, help="exportar la comparación metro a metro")

    serve = commands.add_parser("serve", help="abrir el dashboard web")
    serve.add_argument("--port", type=int, default=8000, help="puerto (por defecto 8000)")
    serve.add_argument(
        "--lan",
        action="store_true",
        help="permitir abrirlo desde otros equipos de tu red (Mac, celular)",
    )

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
        if args.command == "compare":
            return _compare(args)
        if args.command == "serve":
            return _serve(args)
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
                # Index the laps now so the dashboard opens the session instantly.
                laps = lap_index.session_laps(repository, result.session_id)
        finally:
            if reader is not None:
                reader.close()
    finished = sum(lap.time_ms is not None for lap in laps)
    print(
        f"Sesión {result.session_id} grabada: {result.sample_count} muestras, "
        f"{finished} vueltas terminadas, en {args.db}"
    )
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
        laps = lap_index.session_laps(repository, session_id)
    if not laps:
        print(f"La sesión {session_id} no tiene muestras.")
        return 1
    rows = [
        (str(lap.number), _lap_time(lap), _lap_kind(lap), "sí" if lap.off_track else "no")
        for lap in laps
    ]
    _print_table(("Vuelta", "Tiempo", "Tipo", "Fuera de pista"), rows)
    if any(not lap.official and lap.time_ms is not None for lap in laps):
        print("≈ tiempo estimado (sesión grabada antes de guardar el tiempo oficial del juego)")
    return 0


def _compare(args: argparse.Namespace) -> int:
    if not args.db.exists():
        print(f"No hay sesiones todavía ({args.db} no existe).")
        return 1
    ref_session = args.ref_session if args.ref_session is not None else args.session_id
    with SqliteSessionRepository(args.db) as repository:
        return _compare_in(repository, args, ref_session)


def _compare_in(
    repository: SqliteSessionRepository, args: argparse.Namespace, ref_session: int
) -> int:
    target = _load_session(repository, args.session_id)
    reference = target if ref_session == args.session_id else _load_session(repository, ref_session)
    if target is None or reference is None:
        print(f"No existe la sesión {args.session_id if target is None else ref_session}.")
        return 1

    target_lap = _find_lap(target.laps, args.lap)
    if target_lap is None or target_lap.time_ms is None:
        print(f"La vuelta {args.lap} no existe o no está terminada en la sesión {args.session_id}.")
        return 1
    if args.ref is not None:
        ref_lap = _find_lap(reference.laps, args.ref)
    else:
        exclude = target_lap if reference is target else None
        ref_lap = best_clean_lap(reference.laps, exclude)
    if ref_lap is None or ref_lap.time_ms is None:
        print("No hay vuelta de referencia terminada. Indica una con --ref.")
        return 1

    target_samples, target_local = lap_index.load_lap(repository, args.session_id, target_lap)
    reference_samples, reference_local = lap_index.load_lap(repository, ref_session, ref_lap)
    comparison = compare_laps(
        lap_trace(target_samples, target_local, target.info.track_length_m),
        lap_trace(reference_samples, reference_local, reference.info.track_length_m),
    )
    total = comparison.delta_s[-1]
    print(
        f"Vuelta {target_lap.number} ({_lap_time(target_lap)}) contra vuelta {ref_lap.number} "
        f"({_lap_time(ref_lap)}"
        + (f", sesión {ref_session}" if ref_session != args.session_id else "")
        + f") en {target.info.track}"
    )
    verdict = "más lenta" if total > 0 else "más rápida"
    print(f"Diferencia: {total:+.3f} s ({verdict})")
    if not (target_lap.complete and ref_lap.complete):
        print(
            f"Ojo: una de las vueltas no se grabó desde la meta (p. ej. salida de boxes). "
            f"Solo se compara de {comparison.distance_m[0]:.0f} a "
            f"{comparison.distance_m[-1]:.0f} m, así que la diferencia no es la del cronómetro."
        )
    print()
    segments = summarize(comparison)
    rows = [
        (
            f"{seg.start_m:.0f}-{seg.end_m:.0f} m",
            f"{seg.delta_s:+.3f} s",
            f"{seg.target_min_speed_kmh:.0f} / {seg.reference_min_speed_kmh:.0f}",
            f"{seg.target_avg_speed_kmh:.0f} / {seg.reference_avg_speed_kmh:.0f}",
        )
        for seg in segments
    ]
    _print_table(("Tramo", "Delta", "Vel. mín (km/h)", "Vel. media"), rows)
    print("(delta +: pierdes tiempo; velocidades: esta vuelta / referencia)")
    losses = sorted((s for s in segments if s.delta_s > 0), key=lambda s: -s.delta_s)[:3]
    if losses:
        print()
        print("Dónde pierdes más tiempo:")
        for i, seg in enumerate(losses, start=1):
            print(
                f"{i}. {seg.start_m:.0f}-{seg.end_m:.0f} m: {seg.delta_s:+.3f} s "
                f"(vel. mínima {seg.target_min_speed_kmh:.0f} vs "
                f"{seg.reference_min_speed_kmh:.0f} km/h)"
            )
    if args.csv is not None:
        write_csv(comparison, args.csv)
        print(f"\nComparación metro a metro guardada en {args.csv}")
    return 0


@dataclass(frozen=True, slots=True)
class _LoadedSession:
    info: SessionInfo
    laps: list[Lap]


def _load_session(repository: SqliteSessionRepository, session_id: int) -> _LoadedSession | None:
    record = repository.get_session(session_id)
    if record is None:
        return None
    return _LoadedSession(info=record.info, laps=lap_index.session_laps(repository, session_id))


def _find_lap(laps: Sequence[Lap], number: int) -> Lap | None:
    return next((lap for lap in laps if lap.number == number), None)


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


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from raceengineer.api.app import create_app

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    print(f"Dashboard en http://127.0.0.1:{args.port}")
    if args.lan:
        print(f"Desde otro equipo de tu red: http://{_lan_ip()}:{args.port}")
        print("Escribe la dirección completa con http:// (no https), o el navegador no conectará.")
        print("Si Windows pregunta por el firewall, permite el acceso en redes privadas.")
    print("Pulsa Ctrl+C para cerrarlo.")
    logging.getLogger("uvicorn.error").addFilter(_HttpsHint())
    uvicorn.run(create_app(args.db), host=host, port=args.port, log_level="warning")
    return 0


class _HttpsHint(logging.Filter):
    """Replace uvicorn's "Invalid HTTP request" (usually a browser trying https://) with a hint."""

    def __init__(self) -> None:
        super().__init__()
        self._shown = False

    def filter(self, record: logging.LogRecord) -> bool:
        if "Invalid HTTP request" not in record.getMessage():
            return True
        if not self._shown:
            self._shown = True
            print("Un navegador intentó entrar con https://. Escribe la dirección con http://")
        return False


def _lan_ip() -> str:
    """This machine's address on the local network (no packets are sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))  # TEST-NET address; connect() only picks a route
            address: str = probe.getsockname()[0]
        except OSError:
            address = "127.0.0.1"
    return address


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
