import signal
from pathlib import Path

import pytest
from ac_blocks import ScriptedReader, snapshot

from raceengineer import __version__, cli
from raceengineer.adapters.ac_shared_memory import ACNotRunningError
from raceengineer.cli import main
from raceengineer.storage.sqlite import SqliteSessionRepository


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


def _fake_ac(
    monkeypatch: pytest.MonkeyPatch, frames: int = 5, repeat_last: bool = False
) -> list[ScriptedReader]:
    readers: list[ScriptedReader] = []

    def factory() -> ScriptedReader:
        snapshots = [snapshot(i, speedKmh=float(i)) for i in range(1, frames + 1)]
        reader = ScriptedReader(snapshots, repeat_last=repeat_last)
        readers.append(reader)
        return reader

    monkeypatch.setattr(cli, "open_ac_reader", factory)
    return readers


def test_record_from_ac(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    readers = _fake_ac(monkeypatch)
    db = tmp_path / "s.sqlite"

    assert main(["--db", str(db), "record", "--source", "ac", "--poll-hz", "1000"]) == 0

    assert "5 muestras" in capsys.readouterr().out
    assert readers[0].closed
    assert main(["--db", str(db), "sessions"]) == 0
    assert "magione" in capsys.readouterr().out


def test_dump_raw_then_record_dump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_ac(monkeypatch, repeat_last=True)
    dump = tmp_path / "d.acraw.gz"

    code = main(["dump-raw", "--seconds", "0.5", "--poll-hz", "1000", "--output", str(dump)])

    assert code == 0
    assert "Volcado guardado" in capsys.readouterr().out
    db = tmp_path / "s.sqlite"
    assert main(["--db", str(db), "record", "--source", "ac-dump", "--input", str(dump)]) == 0
    assert "5 muestras" in capsys.readouterr().out


def test_dump_raw_default_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_ac(monkeypatch, repeat_last=True)
    monkeypatch.chdir(tmp_path)
    assert main(["dump-raw", "--seconds", "0.01"]) == 0
    assert len(list((tmp_path / "data" / "dumps").glob("ac-*.acraw.gz"))) == 1


def test_record_ac_dump_requires_input(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["record", "--source", "ac-dump"]) == 2
    assert "--input" in capsys.readouterr().out


def test_ac_not_running_is_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def factory() -> ScriptedReader:
        raise ACNotRunningError("AC no está abierto")

    monkeypatch.setattr(cli, "open_ac_reader", factory)
    assert main(["record", "--source", "ac"]) == 1
    assert "AC no está abierto" in capsys.readouterr().out


def test_ctrl_c_handler_sets_stop_and_is_restored() -> None:
    previous = signal.getsignal(signal.SIGINT)
    with cli._stop_on_ctrl_c() as stop:
        handler = signal.getsignal(signal.SIGINT)
        assert callable(handler)
        handler(signal.SIGINT, None)
        assert stop.is_set()
    assert signal.getsignal(signal.SIGINT) == previous


def test_laps_reports_last_lap_timer(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "s.sqlite"
    assert main(["--db", str(db), "record", "--laps", "2"]) == 0
    capsys.readouterr()

    assert main(["--db", str(db), "laps", "1"]) == 0

    out = capsys.readouterr().out
    assert "     1  0:" in out
    assert "     2  0:" in out


def test_laps_without_data(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "s.sqlite"
    assert main(["--db", str(db), "laps", "1"]) == 0
    SqliteSessionRepository(db).close()
    assert main(["--db", str(db), "laps", "1"]) == 1
    assert "no tiene muestras" in capsys.readouterr().out
