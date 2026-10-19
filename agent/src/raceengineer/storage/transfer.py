"""Move one recorded session between databases (e.g. from the PC to the Mac).

An export is a gzip-compressed SQLite file in the normal schema that holds just
that session, so it can be inspected with any SQLite tool after decompressing.
"""

import gzip
import shutil
import tempfile
from pathlib import Path

from raceengineer.domain.ports import SessionRepository
from raceengineer.storage.sqlite import SqliteSessionRepository

_CHUNK = 20_000
"""Samples copied per batch, so long sessions never sit in memory at once."""


def copy_session(source: SessionRepository, session_id: int, target: SessionRepository) -> int:
    """Copy a session, its samples and its lap index; returns the id in ``target``."""
    record = source.get_session(session_id)
    if record is None:
        raise ValueError(f"No existe la sesión {session_id}")
    new_id = target.create_session(record.info, record.started_at)
    start = 0
    while True:
        chunk = source.load_samples(session_id, start, start + _CHUNK)
        if not chunk:
            break
        target.append_samples(new_id, chunk)
        start += len(chunk)
    if record.ended_at is not None:
        target.finish_session(new_id, record.ended_at)
    laps = source.load_laps(session_id)
    if laps is not None:
        target.save_laps(new_id, laps)
    return new_id


def export_session(db_path: Path, session_id: int, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        plain = Path(tmp) / "session.sqlite"
        with SqliteSessionRepository(db_path) as source, SqliteSessionRepository(plain) as target:
            copy_session(source, session_id, target)
            target.checkpoint()
        with plain.open("rb") as src, gzip.open(output, "wb", compresslevel=6) as dst:
            shutil.copyfileobj(src, dst)


def import_session(export: Path, db_path: Path) -> int:
    """Add the exported session to ``db_path``; returns its new id there."""
    with tempfile.TemporaryDirectory() as tmp:
        plain = Path(tmp) / "session.sqlite"
        try:
            with gzip.open(export, "rb") as src, plain.open("wb") as dst:
                shutil.copyfileobj(src, dst)
        except gzip.BadGzipFile as exc:
            raise ValueError(f"{export} no es una sesión exportada") from exc
        with SqliteSessionRepository(plain) as source, SqliteSessionRepository(db_path) as target:
            sessions = source.list_sessions()
            if len(sessions) != 1:
                raise ValueError(f"{export} no es una sesión exportada")
            return copy_session(source, sessions[0].id, target)
