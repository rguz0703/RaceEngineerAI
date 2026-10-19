import gzip
from datetime import UTC, datetime
from pathlib import Path

import pytest

from raceengineer.adapters.fake import FakeSource
from raceengineer.analysis.lap_index import session_laps
from raceengineer.capture.recorder import Recorder
from raceengineer.cli import main
from raceengineer.storage.sqlite import SqliteSessionRepository
from raceengineer.storage.transfer import export_session, import_session

STARTED = datetime(2026, 10, 18, 10, tzinfo=UTC)


def _db_with_sessions(path: Path, count: int = 2) -> None:
    with SqliteSessionRepository(path) as repo:
        for seed in range(count):
            Recorder(FakeSource(laps=2, seed=seed), repo, clock=lambda: STARTED).record()
            session_laps(repo, seed + 1)


def test_round_trip_keeps_everything(tmp_path: Path) -> None:
    pc = tmp_path / "pc.sqlite"
    mac = tmp_path / "mac.sqlite"
    _db_with_sessions(pc)
    _db_with_sessions(mac, count=1)  # the Mac already has a session
    export = tmp_path / "out" / "s2.rese.gz"

    export_session(pc, 2, export)
    new_id = import_session(export, mac)

    assert new_id == 2
    with SqliteSessionRepository(pc) as a, SqliteSessionRepository(mac) as b:
        original = a.get_session(2)
        copy = b.get_session(new_id)
        assert original is not None and copy is not None
        assert copy.info == original.info
        assert (copy.started_at, copy.ended_at) == (original.started_at, original.ended_at)
        assert b.load_samples(new_id) == a.load_samples(2)
        assert b.load_laps(new_id) == a.load_laps(2)  # the index travels too


def test_export_of_missing_session(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    _db_with_sessions(db, count=1)
    with pytest.raises(ValueError, match="No existe"):
        export_session(db, 9, tmp_path / "x.gz")


def test_import_rejects_other_files(tmp_path: Path) -> None:
    plain = tmp_path / "plain.txt"
    plain.write_text("hola", encoding="utf-8")
    with pytest.raises(ValueError, match="no es una sesión"):
        import_session(plain, tmp_path / "db.sqlite")

    # A gzip of a whole database with several sessions is not an export either.
    db = tmp_path / "two.sqlite"
    _db_with_sessions(db)
    with SqliteSessionRepository(db) as repo:
        repo.checkpoint()
    many = tmp_path / "many.gz"
    many.write_bytes(gzip.compress(db.read_bytes()))
    with pytest.raises(ValueError, match="no es una sesión"):
        import_session(many, tmp_path / "db.sqlite")


def test_cli_export_and_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _db_with_sessions(Path("data/sessions.sqlite"), count=1)

    assert main(["export-session", "1"]) == 0
    assert "exportada a data/exports/sesion-1.rese.gz" in capsys.readouterr().out.replace("\\", "/")

    assert main(["--db", "mac.sqlite", "import-session", "data/exports/sesion-1.rese.gz"]) == 0
    assert "importada como sesión 1" in capsys.readouterr().out

    assert main(["export-session", "7"]) == 1
    assert main(["--db", "none.sqlite", "export-session", "1"]) == 1
    assert main(["import-session", "missing.gz"]) == 1
