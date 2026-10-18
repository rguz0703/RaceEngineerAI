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

    out = capsys.readouterr().out
    assert "5 muestras" in out and "vueltas terminadas" in out
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


def test_laps_lists_segmented_laps(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "s.sqlite"
    assert main(["--db", str(db), "record", "--laps", "2"]) == 0
    capsys.readouterr()

    assert main(["--db", str(db), "laps", "1"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["Vuelta", "Tiempo", "Tipo", "Fuera", "de", "pista"]
    assert lines[1].split()[2:] == ["lanzada", "no"]
    assert lines[2].split() == ["2", "-", "sin", "terminar", "no"]
    assert "≈" not in "".join(lines)


def test_laps_marks_estimated_times(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from dataclasses import replace
    from datetime import UTC, datetime

    from raceengineer.adapters.fake import FakeSource
    from raceengineer.domain.models import SessionInfo

    db = tmp_path / "s.sqlite"
    # Like a pre-F3 recording that also started mid-lap.
    samples = [replace(s, last_lap_ms=0) for s in FakeSource(laps=2).samples()][100:]
    with SqliteSessionRepository(db) as repo:
        session_id = repo.create_session(SessionInfo("fake", "t", "c"), datetime.now(UTC))
        repo.append_samples(session_id, samples)

    assert main(["--db", str(db), "laps", str(session_id)]) == 0

    out = capsys.readouterr().out
    assert "≈0:" in out
    assert "incompleta" in out
    assert "tiempo estimado" in out


def test_laps_without_data(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "s.sqlite"
    assert main(["--db", str(db), "laps", "1"]) == 0
    SqliteSessionRepository(db).close()
    assert main(["--db", str(db), "laps", "1"]) == 1
    assert "no tiene muestras" in capsys.readouterr().out


def _fake_db(tmp_path: Path, laps: int = 3) -> Path:
    db = tmp_path / "s.sqlite"
    assert main(["--db", str(db), "record", "--laps", str(laps), "--seed", "3"]) == 0
    return db


def test_compare_against_best_lap(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = _fake_db(tmp_path)
    capsys.readouterr()
    csv_path = tmp_path / "cmp.csv"

    assert main(["--db", str(db), "compare", "1", "2", "--csv", str(csv_path)]) == 0

    out = capsys.readouterr().out
    assert "Vuelta 2" in out and "contra vuelta 1" in out
    assert "Diferencia:" in out
    assert "Tramo" in out
    assert csv_path.exists()


def test_compare_with_explicit_reference_in_other_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = _fake_db(tmp_path)
    assert main(["--db", str(db), "record", "--laps", "3", "--seed", "9"]) == 0
    capsys.readouterr()

    assert main(["--db", str(db), "compare", "1", "1", "--ref", "2", "--ref-session", "2"]) == 0

    out = capsys.readouterr().out
    assert "contra vuelta 2" in out and "sesión 2" in out


def test_compare_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--db", str(tmp_path / "none.sqlite"), "compare", "1", "1"]) == 1
    db = _fake_db(tmp_path, laps=2)
    assert main(["--db", str(db), "compare", "5", "1"]) == 1
    assert main(["--db", str(db), "compare", "1", "1", "--ref-session", "9"]) == 1
    assert main(["--db", str(db), "compare", "1", "2"]) == 1  # lap 2 never finished
    assert main(["--db", str(db), "compare", "1", "1"]) == 1  # no other finished lap
    out = capsys.readouterr().out
    assert "no existe" in out.lower()
    assert "--ref" in out


def test_compare_warns_about_partial_laps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from datetime import UTC, datetime

    from raceengineer.adapters.fake import FakeSource
    from raceengineer.domain.models import SessionInfo

    db = tmp_path / "s.sqlite"
    samples = list(FakeSource(laps=3).samples())[200:]  # starts mid-lap
    with SqliteSessionRepository(db) as repo:
        sid = repo.create_session(
            SessionInfo("fake", "t", "c", track_length_m=2000), datetime.now(UTC)
        )
        repo.append_samples(sid, samples)

    assert main(["--db", str(db), "compare", str(sid), "1", "--ref", "2"]) == 0
    assert "Ojo" in capsys.readouterr().out


def test_serve_starts_uvicorn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import uvicorn

    calls: list[tuple[str, int]] = []

    def fake_run(app: object, host: str, port: int, log_level: str) -> None:
        calls.append((host, port))

    monkeypatch.setattr(uvicorn, "run", fake_run)

    assert main(["--db", str(tmp_path / "s.sqlite"), "serve", "--port", "8123"]) == 0
    assert main(["--db", str(tmp_path / "s.sqlite"), "serve", "--lan"]) == 0

    assert calls == [("127.0.0.1", 8123), ("0.0.0.0", 8000)]
    out = capsys.readouterr().out
    assert "http://127.0.0.1:8123" in out
    assert "Desde otro equipo de tu red: http://" in out


def test_lan_ip_falls_back_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    class NoRoute:
        def __init__(self, *_: object) -> None: ...

        def __enter__(self) -> "NoRoute":
            return self

        def __exit__(self, *_: object) -> None: ...

        def connect(self, _address: object) -> None:
            raise OSError("no route")

    import socket

    monkeypatch.setattr(socket, "socket", NoRoute)
    assert cli._lan_ip() == "127.0.0.1"


def test_https_attempts_become_a_single_hint(capsys: pytest.CaptureFixture[str]) -> None:
    import logging

    hint = cli._HttpsHint()

    def record(message: str) -> logging.LogRecord:
        return logging.LogRecord("uvicorn.error", logging.WARNING, "", 0, message, None, None)

    assert hint.filter(record("Invalid HTTP request received.")) is False
    assert hint.filter(record("Invalid HTTP request received.")) is False
    assert hint.filter(record("Something else")) is True
    assert capsys.readouterr().out.count("http://") == 1


def test_ac_source_waits_until_on_track(monkeypatch: pytest.MonkeyPatch) -> None:
    from threading import Event

    from raceengineer.adapters.ac_shared_memory import ACSharedMemorySource, ACStatus
    from raceengineer.capture.service import SourceUnavailableError

    def not_running() -> ScriptedReader:
        raise ACNotRunningError("AC no está abierto")

    monkeypatch.setattr(cli, "open_ac_reader", not_running)
    with pytest.raises(SourceUnavailableError, match="no está abierto"):
        cli._ac_source(Event())

    menu = ScriptedReader([snapshot(1, ACStatus.OFF)])
    monkeypatch.setattr(cli, "open_ac_reader", lambda: menu)
    with pytest.raises(SourceUnavailableError, match="sal a pista"):
        cli._ac_source(Event())
    assert menu.closed

    on_track = ScriptedReader([snapshot(1)])
    monkeypatch.setattr(cli, "open_ac_reader", lambda: on_track)
    source, close = cli._ac_source(Event())
    assert isinstance(source, ACSharedMemorySource)
    close()
    assert on_track.closed


def test_demo_source_and_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    from threading import Event

    source, close = cli._demo_source(Event())
    assert source.session_info().sim == "fake"
    close()
    assert cli._demo_probe().state == "live"
    monkeypatch.setattr(cli, "open_ac_reader", lambda: ScriptedReader([snapshot(1)]))
    assert cli._ac_probe().state == "live"


def test_serve_demo_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    assert main(["--db", str(tmp_path / "s.sqlite"), "serve", "--demo"]) == 0
    assert "Modo demo" in capsys.readouterr().out
