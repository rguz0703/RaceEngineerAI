import time
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

from raceengineer.adapters.fake import FakeSource
from raceengineer.analysis.lap_index import session_laps
from raceengineer.api.app import create_app
from raceengineer.capture.live import LiveTracker, ReferenceLap, best_reference
from raceengineer.capture.recorder import Recorder
from raceengineer.capture.service import RecordingService
from raceengineer.domain.models import SessionInfo, TelemetrySample
from raceengineer.domain.ports import TelemetrySource
from raceengineer.storage.sqlite import SqliteSessionRepository

TRACK = 2000.0


def _laps(laps: int = 3, seed: int = 0) -> list[TelemetrySample]:
    return list(FakeSource(laps=laps, seed=seed, track_length_m=TRACK).samples())


def test_delta_against_reference_and_swap_on_faster_lap() -> None:
    samples = _laps(laps=4, seed=1)
    tracker = LiveTracker(TRACK)
    frames = [tracker.update(s) for s in samples]

    # No reference until a clean lap is finished, then the delta appears.
    assert frames[0].delta_s is None
    first_lap_end = next(i for i, s in enumerate(samples) if s.lap_number == 1)
    after = frames[first_lap_end + 10]
    assert after.delta_s is not None
    assert after.reference_label == "esta sesión, vuelta 1"
    assert after.best_lap_ms == samples[first_lap_end].last_lap_ms
    times = [s.last_lap_ms for s in samples if s.last_lap_ms]
    assert tracker.reference is not None
    assert tracker.reference.time_ms == min(set(times))


def test_delta_ends_the_lap_at_the_time_difference() -> None:
    # One lap, then the first sample of the next lap (which carries its time).
    crossing = replace(_laps(laps=2, seed=2)[-1], lap_number=1, lap_time_ms=0)
    reference_samples = [*_laps(laps=1, seed=2), crossing]
    tracker = LiveTracker(TRACK)
    for s in reference_samples:
        tracker.update(s)
    assert tracker.reference is not None

    # Replay the same lap: delta stays ~0 all the way round.
    replay = LiveTracker(TRACK, tracker.reference)
    deltas = [replay.update(s).delta_s for s in _laps(laps=1, seed=2)]
    assert max(abs(d) for d in deltas if d is not None) < 0.05


def test_dirty_or_slower_laps_do_not_replace_the_reference() -> None:
    samples = _laps(laps=3, seed=3)
    dirty = [replace(s, tyres_out=4) if s.lap_number == 1 else s for s in samples]
    tracker = LiveTracker(TRACK)
    for s in dirty:
        tracker.update(s)
    assert tracker.reference is not None
    assert tracker.reference.label == "esta sesión, vuelta 1"


def test_pits_and_unknown_length_have_no_delta() -> None:
    samples = _laps(laps=2)
    tracker = LiveTracker(0.0)
    assert all(tracker.update(s).delta_s is None for s in samples)
    reference = ReferenceLap(60_000, [0.0, TRACK], [0.0, 60.0], [0.0, 1.0], [0.0, 1.0], "x")
    pit = LiveTracker(TRACK, reference).update(replace(samples[100], in_pit=True))
    assert pit.delta_s is None


def test_distance_unwraps_just_after_the_line() -> None:
    reference = ReferenceLap(60_000, [0.0, TRACK], [0.0, 60.0], [0.0], [0.0], "x")
    tracker = LiveTracker(TRACK, reference)
    frame = tracker.update(replace(_laps()[0], normalized_position=0.999, lap_time_ms=50))
    assert frame.distance_m == 0.0
    assert reference.outline() == ([0.0], [0.0])


def test_best_reference_comes_from_same_track_and_car(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    with SqliteSessionRepository(db) as repo:
        for seed in (1, 2):
            Recorder(FakeSource(laps=2, seed=seed, track_length_m=TRACK), repo).record()
            session_laps(repo, seed)
        info = FakeSource(track_length_m=TRACK).session_info()
        reference = best_reference(repo, info)
        assert reference is not None
        best = min(
            (lap.time_ms or 0)
            for sid in (1, 2)
            for lap in session_laps(repo, sid)
            if lap.time_ms is not None
        )
        assert reference.time_ms == best
        assert reference.label.startswith("sesión ")
        assert best_reference(repo, SessionInfo("fake", "otra_pista", "fake_gt3")) is None


def _wait(condition: Callable[[], bool], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


class _Endless:
    """Fake laps, then holds until stopped (so the live socket has something to show)."""

    def __init__(self, stop: Event) -> None:
        self._inner = FakeSource(laps=2, track_length_m=TRACK)
        self._stop = stop

    def session_info(self) -> SessionInfo:
        return self._inner.session_info()

    def samples(self) -> Iterator[TelemetrySample]:
        yield from self._inner.samples()
        self._stop.wait()


def _endless(stop: Event) -> tuple[TelemetrySource, Callable[[], None]]:
    return _Endless(stop), lambda: None


def test_websocket_streams_frames_and_reference(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    service = RecordingService(db, _endless)
    app = create_app(db, static_dir=None, recorder=service, live_hz=200)
    with TestClient(app) as client, client.websocket_connect("/ws/live") as ws:
        idle = ws.receive_json()
        assert (idle["state"], idle["frame"]) == ("idle", None)
        assert "reference" not in idle

        client.post("/api/recording/start")
        _wait(lambda: service.live()[0] is not None and service.live()[0].lap == 2)  # type: ignore[union-attr]
        message = ws.receive_json()
        while message.get("reference") is None:
            message = ws.receive_json()
        assert message["state"] == "recording"
        reference = message["reference"]
        assert reference["label"] == "esta sesión, vuelta 1"
        assert reference["length_m"] == pytest.approx(TRACK, abs=1)
        assert len(reference["x"]) == len(reference["z"]) > 10
        frame = ws.receive_json()["frame"]
        assert frame["lap"] == 2 and frame["delta_s"] is not None
        client.post("/api/recording/stop")


def test_websocket_without_recorder(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "s.sqlite", static_dir=None))
    with client.websocket_connect("/ws/live") as ws:
        assert ws.receive_json()["state"] == "idle"


def test_events_for_off_track_lockup_wheelspin_and_best_lap() -> None:
    samples = _laps(laps=3, seed=4)
    lap0_end = next(i for i, s in enumerate(samples) if s.lap_number == 1)
    edited = list(samples)
    # Off track for a stretch, twice close together: one event per episode.
    for i in range(100, 130):
        edited[i] = replace(edited[i], tyres_out=4)
    for i in range(200, 215):
        edited[i] = replace(edited[i], brake=1.0, throttle=0.0, slip_ratio_fl=-0.6)
    for i in range(300, 320):
        edited[i] = replace(edited[i], throttle=1.0, slip_ratio_rl=0.4)
    for i in range(400, 401):
        edited[i] = replace(edited[i], tyres_out=3)  # brief: still counts as off track
    tracker = LiveTracker(TRACK)
    frame = None
    for s in edited:
        frame = tracker.update(s)
    assert frame is not None
    kinds = [e.kind for e in frame.events]
    assert kinds.count("off_track") == 2
    assert "lockup" in kinds and "wheelspin" in kinds
    assert any("delantera izquierda" in e.text for e in frame.events)
    ids = [e.id for e in frame.events]
    assert ids == sorted(ids)
    assert edited[lap0_end].lap_number == 1


def test_new_best_lap_event_and_event_cap() -> None:
    samples = _laps(laps=3, seed=5)
    first_time = next(s.last_lap_ms for s in samples if s.lap_number == 1)
    # Make lap 2 exactly half a second faster than lap 1.
    faster = [replace(s, last_lap_ms=first_time - 500) if s.lap_number == 2 else s for s in samples]
    tracker = LiveTracker(TRACK)
    for s in faster:
        frame = tracker.update(s)

    [best] = [e for e in frame.events if e.kind == "best_lap"]
    assert best.level == "good" and best.lap == 2
    assert "0.500 s más rápida" in best.text

    for _ in range(30):
        tracker._add("off_track", "warn", "x", 1, 0.0)
    assert len(tracker.update(_laps()[0]).events) == 20
