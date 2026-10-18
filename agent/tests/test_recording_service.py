import time
from collections.abc import Callable, Iterator
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

from raceengineer.adapters.ac_shared_memory import ACStatus, GameProbe
from raceengineer.adapters.fake import FakeSource
from raceengineer.api.app import create_app
from raceengineer.capture.realtime import RealtimeSource
from raceengineer.capture.service import (
    RecordingService,
    RecordingState,
    SourceUnavailableError,
)
from raceengineer.domain.models import SessionInfo, TelemetrySample
from raceengineer.domain.ports import TelemetrySource
from raceengineer.storage.sqlite import SqliteSessionRepository


def wait_until(condition: Callable[[], bool], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


class GatedSource:
    """Yields fake samples, then blocks until stopped, like a game on track."""

    def __init__(self, stop: Event, laps: int = 2) -> None:
        self._inner = FakeSource(laps=laps)
        self._stop = stop
        self.game_status = ACStatus.LIVE

    def session_info(self) -> SessionInfo:
        return self._inner.session_info()

    def samples(self) -> Iterator[TelemetrySample]:
        yield from self._inner.samples()
        self.game_status = ACStatus.PAUSE
        self._stop.wait()


def _gated(stop: Event) -> tuple[TelemetrySource, Callable[[], None]]:
    return GatedSource(stop), lambda: None


def _finite(stop: Event) -> tuple[TelemetrySource, Callable[[], None]]:
    return FakeSource(laps=2), lambda: None


def test_records_until_stopped_and_indexes_laps(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    service = RecordingService(db, _gated)

    assert service.start().state is RecordingState.WAITING
    wait_until(lambda: service.status().lap == 2)
    status = service.status()
    assert status.state is RecordingState.RECORDING
    assert status.session_id == 1
    assert status.last_lap_ms > 0 and status.best_lap_ms == status.last_lap_ms
    wait_until(lambda: service.status().game_status == "pause")
    assert service.start().state is RecordingState.RECORDING  # already running

    final = service.stop(wait=True)

    assert final.state is RecordingState.IDLE
    assert final.last_session_id == 1
    assert "1 vuelta terminada" in final.message
    with SqliteSessionRepository(db) as repo:
        assert repo.load_laps(1) is not None


def test_recording_ends_on_its_own_when_the_source_ends(tmp_path: Path) -> None:
    service = RecordingService(tmp_path / "s.sqlite", _finite)
    service.start()
    wait_until(lambda: service.status().last_session_id == 1)
    assert service.status().state is RecordingState.IDLE
    assert service.stop().state is RecordingState.IDLE  # nothing to stop


def test_waits_for_the_game_and_can_be_cancelled(tmp_path: Path) -> None:
    attempts: list[int] = []

    def unavailable(stop: Event) -> tuple[TelemetrySource, Callable[[], None]]:
        attempts.append(1)
        raise SourceUnavailableError("Assetto Corsa está abierto: sal a pista para empezar.")

    service = RecordingService(tmp_path / "s.sqlite", unavailable, retry_s=0.01)
    service.start()
    wait_until(lambda: len(attempts) >= 3)
    assert service.status().state is RecordingState.WAITING
    assert "sal a pista" in service.status().message

    final = service.stop(wait=True)

    assert final.state is RecordingState.IDLE
    assert final.last_session_id is None


def test_errors_are_reported(tmp_path: Path) -> None:
    def broken(stop: Event) -> tuple[TelemetrySource, Callable[[], None]]:
        raise RuntimeError("boom")

    service = RecordingService(tmp_path / "s.sqlite", broken)
    service.start()
    wait_until(lambda: service.status().state is RecordingState.IDLE)
    assert "boom" in service.status().message


def test_realtime_source_paces_and_stops() -> None:
    now = [0.0]
    waits: list[float] = []

    def wait(seconds: float) -> bool:
        waits.append(seconds)
        now[0] += seconds
        return False

    stop = Event()
    source = RealtimeSource(FakeSource(laps=1, rate_hz=10), stop, clock=lambda: now[0], wait=wait)
    stream = source.samples()
    samples = [next(stream) for _ in range(5)]
    assert samples[4].t == pytest.approx(0.4)
    assert sum(waits) == pytest.approx(0.4)
    assert source.session_info().sim == "fake"
    stop.set()
    assert list(stream) == []
    with pytest.raises(ValueError):
        RealtimeSource(FakeSource(), speed=0)


def test_realtime_source_stops_during_a_wait() -> None:
    stop = Event()

    def wait(_: float) -> bool:
        stop.set()
        return True

    samples = list(RealtimeSource(FakeSource(laps=1), stop, wait=wait).samples())
    assert len(samples) == 1


def test_api_controls_recording(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    service = RecordingService(db, _gated)
    probe_calls: list[int] = []

    def probe() -> GameProbe:
        probe_calls.append(1)
        return GameProbe(state="off")

    with TestClient(create_app(db, static_dir=None, recorder=service, probe=probe)) as client:
        idle = client.get("/api/recording").json()
        assert (idle["available"], idle["state"], idle["game"]["state"]) == (True, "idle", "off")

        client.post("/api/recording/start")
        wait_until(lambda: client.get("/api/recording").json()["state"] == "recording")
        live = client.get("/api/recording").json()
        assert live["game"]["state"] in ("live", "pause")
        calls_while_recording = len(probe_calls)
        client.get("/api/recording")
        assert len(probe_calls) == calls_while_recording  # no probing while recording

        stopped = client.post("/api/recording/stop").json()
        assert stopped["state"] == "idle"
        assert stopped["last_session_id"] == 1


def test_api_stops_recording_on_shutdown(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    service = RecordingService(db, _gated)
    with TestClient(create_app(db, static_dir=None, recorder=service)) as client:
        client.post("/api/recording/start")
        wait_until(lambda: service.status().state is RecordingState.RECORDING)
    assert service.status().state is RecordingState.IDLE
    assert service.status().last_session_id == 1


def test_api_without_recorder(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "s.sqlite", static_dir=None))
    body = client.get("/api/recording").json()
    assert (body["available"], body["game"]["state"]) == (False, "unavailable")
    assert client.post("/api/recording/start").status_code == 409
    assert client.post("/api/recording/stop").status_code == 409
