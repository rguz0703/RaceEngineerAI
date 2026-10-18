"""SQLite implementation of SessionRepository."""

import sqlite3
from collections.abc import Sequence
from dataclasses import astuple, fields
from datetime import datetime
from pathlib import Path

from raceengineer.domain.models import SessionInfo, SessionRecord, TelemetrySample

SCHEMA_VERSION = 2

_SAMPLE_COLUMNS = [f.name for f in fields(TelemetrySample)]

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sim          TEXT NOT NULL,
    track        TEXT NOT NULL,
    track_config TEXT NOT NULL,
    car          TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    ended_at     TEXT
);

CREATE TABLE IF NOT EXISTS samples (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    seq        INTEGER NOT NULL,
    {", ".join(f"{name} REAL NOT NULL" for name in _SAMPLE_COLUMNS)},
    PRIMARY KEY (session_id, seq)
) WITHOUT ROWID;
"""

_INSERT_SAMPLE = (
    f"INSERT INTO samples (session_id, seq, {', '.join(_SAMPLE_COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in range(len(_SAMPLE_COLUMNS) + 2))})"
)

_SELECT_SAMPLES = (
    f"SELECT {', '.join(_SAMPLE_COLUMNS)} FROM samples WHERE session_id = ? ORDER BY seq"
)


class SqliteSessionRepository:
    """Stores sessions and samples in a single SQLite file.

    Each append_samples call commits, so samples written before a crash survive.
    """

    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()
        self._next_seq: dict[int, int] = {}

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SqliteSessionRepository":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def create_session(self, info: SessionInfo, started_at: datetime) -> int:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO sessions (sim, track, track_config, car, started_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (info.sim, info.track, info.track_config, info.car, started_at.isoformat()),
            )
        session_id = cursor.lastrowid
        assert session_id is not None
        self._next_seq[session_id] = 0
        return session_id

    def append_samples(self, session_id: int, samples: Sequence[TelemetrySample]) -> None:
        if not samples:
            return
        start = self._next_seq.get(session_id)
        if start is None:
            start = self._sample_count(session_id)
        rows = [(session_id, start + i, *astuple(sample)) for i, sample in enumerate(samples)]
        with self._conn:
            self._conn.executemany(_INSERT_SAMPLE, rows)
        self._next_seq[session_id] = start + len(samples)

    def finish_session(self, session_id: int, ended_at: datetime) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE sessions SET ended_at = ? WHERE id = ?",
                (ended_at.isoformat(), session_id),
            )

    def list_sessions(self) -> list[SessionRecord]:
        rows = self._conn.execute(
            "SELECT s.id, s.sim, s.track, s.track_config, s.car, s.started_at, s.ended_at, "
            "(SELECT COUNT(*) FROM samples WHERE session_id = s.id) "
            "FROM sessions s ORDER BY s.id"
        ).fetchall()
        return [
            SessionRecord(
                id=row[0],
                info=SessionInfo(sim=row[1], track=row[2], track_config=row[3], car=row[4]),
                started_at=datetime.fromisoformat(row[5]),
                ended_at=datetime.fromisoformat(row[6]) if row[6] else None,
                sample_count=row[7],
            )
            for row in rows
        ]

    def load_samples(self, session_id: int) -> list[TelemetrySample]:
        rows = self._conn.execute(_SELECT_SAMPLES, (session_id,)).fetchall()
        return [_sample_from_row(row) for row in rows]

    def _sample_count(self, session_id: int) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM samples WHERE session_id = ?", (session_id,)
        ).fetchone()
        return int(row[0])

    def _migrate(self) -> None:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema v{version} is newer than this app supports (v{SCHEMA_VERSION})"
            )
        # Each step runs in its own transaction, so a crash never leaves a half-upgraded file.
        if version == 0:
            self._conn.executescript(
                f"BEGIN; {_SCHEMA} PRAGMA user_version = {SCHEMA_VERSION}; COMMIT;"
            )
            return
        for target in range(version + 1, SCHEMA_VERSION + 1):
            self._conn.executescript(
                f"BEGIN; {_MIGRATIONS[target - 2]} PRAGMA user_version = {target}; COMMIT;"
            )


# Each entry upgrades the schema from version N - 1 to N (index 0 = to version 2).
_MIGRATIONS = [
    """
    ALTER TABLE samples ADD COLUMN last_lap_ms REAL NOT NULL DEFAULT 0;
    ALTER TABLE samples ADD COLUMN tyres_out REAL NOT NULL DEFAULT 0;
    """,
]


def _sample_from_row(row: tuple[float, ...]) -> TelemetrySample:
    values = dict(zip(_SAMPLE_COLUMNS, row, strict=True))
    return TelemetrySample(
        t=values["t"],
        lap_number=int(values["lap_number"]),
        lap_time_ms=int(values["lap_time_ms"]),
        normalized_position=values["normalized_position"],
        speed_kmh=values["speed_kmh"],
        throttle=values["throttle"],
        brake=values["brake"],
        clutch=values["clutch"],
        steering=values["steering"],
        gear=int(values["gear"]),
        rpm=values["rpm"],
        pos_x=values["pos_x"],
        pos_y=values["pos_y"],
        pos_z=values["pos_z"],
        in_pit=bool(values["in_pit"]),
        last_lap_ms=int(values["last_lap_ms"]),
        tyres_out=int(values["tyres_out"]),
    )
