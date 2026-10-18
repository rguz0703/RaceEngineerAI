import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from raceengineer.adapters.fake import FakeSource
from raceengineer.domain.models import SessionInfo
from raceengineer.storage.sqlite import SqliteSessionRepository

INFO = SessionInfo(sim="ac", track="monza", car="bmw_m3_e30", track_config="")
START = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
END = datetime(2026, 10, 17, 12, 30, tzinfo=UTC)


def test_samples_round_trip_exactly(tmp_path: Path) -> None:
    samples = list(FakeSource(laps=1).samples())
    with SqliteSessionRepository(tmp_path / "db.sqlite") as repo:
        session_id = repo.create_session(INFO, START)
        repo.append_samples(session_id, samples[:100])
        repo.append_samples(session_id, samples[100:])

        assert repo.load_samples(session_id) == samples


def test_data_persists_after_reopening(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    samples = list(FakeSource(laps=1).samples())[:50]
    with SqliteSessionRepository(db) as repo:
        session_id = repo.create_session(INFO, START)
        repo.append_samples(session_id, samples[:20])

    with SqliteSessionRepository(db) as repo:
        repo.append_samples(session_id, samples[20:])
        repo.finish_session(session_id, END)

    with SqliteSessionRepository(db) as repo:
        [record] = repo.list_sessions()
        assert record.id == session_id
        assert record.info == INFO
        assert record.started_at == START
        assert record.ended_at == END
        assert record.sample_count == 50
        assert repo.load_samples(session_id) == samples


def test_unfinished_session_has_no_end_time() -> None:
    with SqliteSessionRepository(":memory:") as repo:
        repo.create_session(INFO, START)
        [record] = repo.list_sessions()
        assert record.ended_at is None
        assert record.sample_count == 0


def test_sessions_are_isolated() -> None:
    samples = list(FakeSource(laps=1).samples())[:10]
    with SqliteSessionRepository(":memory:") as repo:
        a = repo.create_session(INFO, START)
        b = repo.create_session(INFO, START)
        repo.append_samples(a, samples)
        repo.append_samples(b, [])

        assert repo.load_samples(a) == samples
        assert repo.load_samples(b) == []


def test_refuses_database_from_newer_version(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 999")
    conn.close()

    with pytest.raises(RuntimeError, match="newer"):
        SqliteSessionRepository(db)


_V1_SCHEMA = """
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, sim TEXT NOT NULL, track TEXT NOT NULL,
    track_config TEXT NOT NULL, car TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT
);
CREATE TABLE samples (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    t REAL NOT NULL, lap_number REAL NOT NULL, lap_time_ms REAL NOT NULL,
    normalized_position REAL NOT NULL, speed_kmh REAL NOT NULL, throttle REAL NOT NULL,
    brake REAL NOT NULL, clutch REAL NOT NULL, steering REAL NOT NULL, gear REAL NOT NULL,
    rpm REAL NOT NULL, pos_x REAL NOT NULL, pos_y REAL NOT NULL, pos_z REAL NOT NULL,
    in_pit REAL NOT NULL,
    PRIMARY KEY (session_id, seq)
) WITHOUT ROWID;
INSERT INTO sessions VALUES (1, 'ac', 'monza', '', 'car', '2026-10-17T12:00:00+00:00', NULL);
INSERT INTO samples VALUES (1, 0, 0.5, 1, 1234, 0.1, 200, 1, 0, 0, 0, 5, 7000, 1, 2, 3, 0);
PRAGMA user_version = 1;
"""


def test_upgrades_version_1_database(tmp_path: Path) -> None:
    db = tmp_path / "v1.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(_V1_SCHEMA)
    conn.close()

    with SqliteSessionRepository(db) as repo:
        [sample] = repo.load_samples(1)

    assert (sample.lap_time_ms, sample.speed_kmh) == (1234, 200.0)
    assert (sample.last_lap_ms, sample.tyres_out) == (0, 0)
    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    conn.close()
