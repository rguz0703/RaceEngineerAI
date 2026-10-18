"""Background recording controlled from the dashboard (start, stop, live status)."""

import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import Event

from raceengineer.analysis import lap_index
from raceengineer.capture.recorder import Recorder
from raceengineer.domain.models import TelemetrySample
from raceengineer.domain.ports import TelemetrySource
from raceengineer.storage.sqlite import SqliteSessionRepository


class SourceUnavailableError(RuntimeError):
    """The game is not ready yet; the service keeps retrying."""


SourceFactory = Callable[[Event], tuple[TelemetrySource, Callable[[], None]]]
"""Opens a source that honours the stop event; returns it and a close function.
Raises SourceUnavailableError while the game is not running."""


class RecordingState(StrEnum):
    IDLE = "idle"
    WAITING = "waiting"
    """Start was pressed but the game is not on track yet."""
    RECORDING = "recording"
    STOPPING = "stopping"


@dataclass(frozen=True, slots=True)
class RecordingStatus:
    state: RecordingState = RecordingState.IDLE
    session_id: int | None = None
    started_at: datetime | None = None
    sample_count: int = 0
    lap: int = 0
    """Current lap, 1-based (0 before the first sample)."""
    lap_time_ms: int = 0
    last_lap_ms: int = 0
    best_lap_ms: int = 0
    speed_kmh: float = 0.0
    in_pit: bool = False
    game_status: str = ""
    """What the source reports right now (live, pause...), if it knows."""
    message: str = ""
    last_session_id: int | None = None
    """The most recent recording that finished."""


class RecordingService:
    """Runs one recording at a time in a background thread."""

    def __init__(
        self,
        db_path: Path,
        open_source: SourceFactory,
        retry_s: float = 2.0,
    ) -> None:
        self._db_path = db_path
        self._open_source = open_source
        self._retry_s = retry_s
        self._lock = threading.Lock()
        self._status = RecordingStatus()
        self._stop = Event()
        self._thread: threading.Thread | None = None
        self._source: TelemetrySource | None = None

    def status(self) -> RecordingStatus:
        with self._lock:
            status = self._status
        source = self._source
        game = getattr(source, "game_status", None) if source is not None else None
        if game is not None and status.state is RecordingState.RECORDING:
            status = replace(status, game_status=str(game.name).lower())
        return status

    def start(self) -> RecordingStatus:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self._status
            self._stop = Event()
            self._status = RecordingStatus(
                state=RecordingState.WAITING,
                message="Esperando a Assetto Corsa…",
                last_session_id=self._status.last_session_id,
            )
            self._thread = threading.Thread(target=self._run, name="recording", daemon=True)
            self._thread.start()
            return self._status

    def stop(self, wait: bool = False, timeout: float = 30.0) -> RecordingStatus:
        with self._lock:
            thread = self._thread
            if thread is None or not thread.is_alive():
                return self._status
            self._stop.set()
            if self._status.state is RecordingState.RECORDING:
                self._status = replace(self._status, state=RecordingState.STOPPING)
        if wait:
            thread.join(timeout)
        return self.status()

    def _run(self) -> None:
        stop = self._stop
        try:
            opened = self._wait_for_source(stop)
            if opened is None:
                self._finish(None, "")
                return
            source, close = opened
            self._source = source
            try:
                with SqliteSessionRepository(self._db_path) as repository:
                    result = Recorder(source, repository).record(
                        stop, on_sample=self._on_sample, on_start=self._on_start
                    )
                    laps = lap_index.session_laps(repository, result.session_id)
            finally:
                self._source = None
                close()
            finished = sum(lap.time_ms is not None for lap in laps)
            laps_text = "1 vuelta terminada" if finished == 1 else f"{finished} vueltas terminadas"
            self._finish(result.session_id, f"Sesión {result.session_id} guardada: {laps_text}.")
        except Exception as exc:  # pragma: no cover - surfaced to the dashboard
            self._finish(None, f"Error al grabar: {exc}")

    def _wait_for_source(self, stop: Event) -> tuple[TelemetrySource, Callable[[], None]] | None:
        while not stop.is_set():
            try:
                return self._open_source(stop)
            except SourceUnavailableError as exc:
                with self._lock:
                    self._status = replace(self._status, message=str(exc))
                stop.wait(self._retry_s)
        return None

    def _on_start(self, session_id: int) -> None:
        with self._lock:
            self._status = replace(
                self._status,
                state=RecordingState.RECORDING
                if self._status.state is RecordingState.WAITING
                else self._status.state,
                session_id=session_id,
                started_at=datetime.now(UTC),
                message="",
            )

    def _on_sample(self, sample: TelemetrySample) -> None:
        with self._lock:
            status = self._status
            best = status.best_lap_ms
            if sample.last_lap_ms and (best == 0 or sample.last_lap_ms < best):
                best = sample.last_lap_ms
            self._status = replace(
                status,
                sample_count=status.sample_count + 1,
                lap=sample.lap_number + 1,
                lap_time_ms=sample.lap_time_ms,
                last_lap_ms=sample.last_lap_ms,
                best_lap_ms=best,
                speed_kmh=sample.speed_kmh,
                in_pit=sample.in_pit,
            )

    def _finish(self, session_id: int | None, message: str) -> None:
        with self._lock:
            last = session_id if session_id is not None else self._status.last_session_id
            self._status = RecordingStatus(message=message, last_session_id=last)
