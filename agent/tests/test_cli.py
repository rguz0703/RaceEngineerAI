from pathlib import Path

import pytest

from raceengineer import __version__
from raceengineer.cli import main


def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"raceengineer {__version__}"


def test_no_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "RaceEngineerAI" in capsys.readouterr().out


def test_record_then_list_sessions(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "sessions.sqlite"

    assert main(["--db", str(db), "record", "--laps", "1"]) == 0
    assert "Sesión 1 grabada" in capsys.readouterr().out

    assert main(["--db", str(db), "sessions"]) == 0
    out = capsys.readouterr().out
    assert "synthetic_oval" in out
    assert "fake_gt3" in out


def test_sessions_without_database(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--db", str(tmp_path / "missing.sqlite"), "sessions"]) == 0
    assert "No hay sesiones" in capsys.readouterr().out


def test_sessions_with_empty_database(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from raceengineer.storage.sqlite import SqliteSessionRepository

    db = tmp_path / "empty.sqlite"
    SqliteSessionRepository(db).close()

    assert main(["--db", str(db), "sessions"]) == 0
    assert "No hay sesiones" in capsys.readouterr().out
