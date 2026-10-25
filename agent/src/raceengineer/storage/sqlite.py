"""SQLite implementation of SessionRepository."""

import sqlite3
from collections.abc import Sequence
from dataclasses import astuple, fields
from datetime import datetime
from pathlib import Path

from raceengineer.domain.models import Lap, LapSignals, SessionInfo, SessionRecord, TelemetrySample

SCHEMA_VERSION = 8

_SAMPLE_COLUMNS = [f.name for f in fields(TelemetrySample)]

_LAPS_TABLE = """
CREATE TABLE IF NOT EXISTS laps (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    number     INTEGER NOT NULL,
    start_seq  INTEGER NOT NULL,
    end_seq    INTEGER NOT NULL,
    time_ms    INTEGER,
    official   INTEGER NOT NULL,
    complete   INTEGER NOT NULL,
    out_lap    INTEGER NOT NULL,
    in_lap     INTEGER NOT NULL,
    off_track  INTEGER NOT NULL,
    s1_ms      INTEGER,
    s2_ms      INTEGER,
    s3_ms      INTEGER,
    PRIMARY KEY (session_id, start_seq)
) WITHOUT ROWID;
"""
# The lap index as v5 created it; v8 adds the sector columns to it.
_LAPS_TABLE_V5 = "\n".join(
    line
    for line in _LAPS_TABLE.splitlines()
    if "s1_ms" not in line and "s2_ms" not in line and "s3_ms" not in line
)

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sim          TEXT NOT NULL,
    track        TEXT NOT NULL,
    track_config TEXT NOT NULL,
    car          TEXT NOT NULL,
    track_length_m REAL NOT NULL DEFAULT 0,
    tyre_compound TEXT NOT NULL DEFAULT '',
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    laps_sample_count INTEGER
);

{_LAPS_TABLE}
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
    f"SELECT {', '.join(_SAMPLE_COLUMNS)} FROM samples "
    "WHERE session_id = ? AND seq >= ? AND seq < ? ORDER BY seq"
)

_LAP_SIGNAL_COLUMNS = list(LapSignals._fields)
_SELECT_LAP_SIGNALS = (
    f"SELECT {', '.join(_LAP_SIGNAL_COLUMNS)} FROM samples WHERE session_id = ? ORDER BY seq"
)

_LAP_COLUMNS = (
    "number, start_seq, end_seq, time_ms, official, complete, out_lap, in_lap, off_track, "
    "s1_ms, s2_ms, s3_ms"
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

    def checkpoint(self) -> None:
        """Fold the write-ahead log into the main file (before copying the file)."""
        self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def __enter__(self) -> "SqliteSessionRepository":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def create_session(self, info: SessionInfo, started_at: datetime) -> int:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO sessions "
                "(sim, track, track_config, car, track_length_m, tyre_compound, started_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    info.sim,
                    info.track,
                    info.track_config,
                    info.car,
                    info.track_length_m,
                    info.tyre_compound,
                    started_at.isoformat(),
                ),
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
            "s.track_length_m, "
            "(SELECT COUNT(*) FROM samples WHERE session_id = s.id), s.tyre_compound "
            "FROM sessions s ORDER BY s.id"
        ).fetchall()
        return [
            SessionRecord(
                id=row[0],
                info=SessionInfo(
                    sim=row[1],
                    track=row[2],
                    track_config=row[3],
                    car=row[4],
                    track_length_m=row[7],
                    tyre_compound=row[9],
                ),
                started_at=datetime.fromisoformat(row[5]),
                ended_at=datetime.fromisoformat(row[6]) if row[6] else None,
                sample_count=row[8],
            )
            for row in rows
        ]

    def get_session(self, session_id: int) -> SessionRecord | None:
        return next((r for r in self.list_sessions() if r.id == session_id), None)

    def load_samples(
        self, session_id: int, start: int = 0, end: int | None = None
    ) -> list[TelemetrySample]:
        """Samples seq start..end-1 (all of them by default)."""
        stop = end if end is not None else 2**62
        rows = self._conn.execute(_SELECT_SAMPLES, (session_id, start, stop)).fetchall()
        return [_sample_from_row(row) for row in rows]

    def load_lap_signals(self, session_id: int) -> list[LapSignals]:
        rows = self._conn.execute(_SELECT_LAP_SIGNALS, (session_id,)).fetchall()
        return [
            LapSignals(t, int(lap), int(lap_ms), int(last), bool(pit), int(out), pos)
            for t, lap, lap_ms, last, pit, out, pos in rows
        ]

    def save_laps(self, session_id: int, laps: Sequence[Lap]) -> None:
        """Store the session's laps, valid while no samples are added."""
        with self._conn:
            self._conn.execute("DELETE FROM laps WHERE session_id = ?", (session_id,))
            self._conn.executemany(
                f"INSERT INTO laps (session_id, {_LAP_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        session_id,
                        lap.number,
                        lap.start,
                        lap.end,
                        lap.time_ms,
                        lap.official,
                        lap.complete,
                        lap.out_lap,
                        lap.in_lap,
                        lap.off_track,
                        *(lap.sector_ms if len(lap.sector_ms) == 3 else (None, None, None)),
                    )
                    for lap in laps
                ],
            )
            self._conn.execute(
                "UPDATE sessions SET laps_sample_count = ? WHERE id = ?",
                (self._sample_count(session_id), session_id),
            )

    def load_laps(self, session_id: int) -> list[Lap] | None:
        """The stored laps, or None if never indexed or samples were added since."""
        row = self._conn.execute(
            "SELECT laps_sample_count FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None or row[0] is None or row[0] != self._sample_count(session_id):
            return None
        rows = self._conn.execute(
            f"SELECT {_LAP_COLUMNS} FROM laps WHERE session_id = ? ORDER BY start_seq",
            (session_id,),
        ).fetchall()
        return [
            Lap(
                number=number,
                start=start,
                end=end,
                time_ms=time_ms,
                official=bool(official),
                complete=bool(complete),
                out_lap=bool(out_lap),
                in_lap=bool(in_lap),
                off_track=bool(off_track),
                sector_ms=(s1, s2, s3) if s1 is not None else (),
            )
            for (
                number,
                start,
                end,
                time_ms,
                official,
                complete,
                out_lap,
                in_lap,
                off_track,
                s1,
                s2,
                s3,
            ) in rows
        ]

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
    "ALTER TABLE sessions ADD COLUMN track_length_m REAL NOT NULL DEFAULT 0;",
    "ALTER TABLE sessions ADD COLUMN tyre_compound TEXT NOT NULL DEFAULT '';\n"
    + "\n".join(
        f"ALTER TABLE samples ADD COLUMN {name} REAL NOT NULL DEFAULT 0;"
        # Exactly the columns v4 introduced; later fields get their own migrations.
        for name in _SAMPLE_COLUMNS[
            _SAMPLE_COLUMNS.index("tyres_out") + 1 : _SAMPLE_COLUMNS.index("fuel") + 1
        ]
    ),
    "ALTER TABLE sessions ADD COLUMN laps_sample_count INTEGER;\n" + _LAPS_TABLE_V5,
    # v6: AC samples recorded before the fix stored the left wheels' tyre edges
    # swapped (see to_sample); swap them back. UPDATE reads the old values.
    """
    UPDATE samples SET
        tyre_temp_inner_fl = tyre_temp_outer_fl, tyre_temp_outer_fl = tyre_temp_inner_fl,
        tyre_temp_inner_rl = tyre_temp_outer_rl, tyre_temp_outer_rl = tyre_temp_inner_rl
    WHERE session_id IN (SELECT id FROM sessions WHERE sim = 'assetto_corsa');
    """,
    # v7: lap rules changed (mid-update read at the start, minimum lap time);
    # forget the stored lap indexes so they are rebuilt on next use.
    "UPDATE sessions SET laps_sample_count = NULL;",
    # v8: sector times in the lap index; rebuild the indexes to fill them in.
    """
    ALTER TABLE laps ADD COLUMN s1_ms INTEGER;
    ALTER TABLE laps ADD COLUMN s2_ms INTEGER;
    ALTER TABLE laps ADD COLUMN s3_ms INTEGER;
    UPDATE sessions SET laps_sample_count = NULL;
    """,
]


_INT_FIELDS = {f.name for f in fields(TelemetrySample) if f.type is int}
_BOOL_FIELDS = {f.name for f in fields(TelemetrySample) if f.type is bool}


def _sample_from_row(row: tuple[float, ...]) -> TelemetrySample:
    values: dict[str, float | int | bool] = {}
    for name, value in zip(_SAMPLE_COLUMNS, row, strict=True):
        if name in _INT_FIELDS:
            values[name] = int(value)
        elif name in _BOOL_FIELDS:
            values[name] = bool(value)
        else:
            values[name] = value
    return TelemetrySample(**values)  # type: ignore[arg-type]
