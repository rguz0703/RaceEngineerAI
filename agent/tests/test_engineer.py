from dataclasses import replace

import pytest

from raceengineer.adapters.fake import FakeSource
from raceengineer.analysis.compare import Channels, LapComparison
from raceengineer.capture.engineer import (
    biggest_loss,
    gap_words,
    incident_speech,
    lap_call,
    lap_time_words,
    sector_call,
    tip_call,
)
from raceengineer.capture.live import LiveTracker, _until_reset
from raceengineer.domain.models import TelemetrySample

TRACK = 2000.0


@pytest.mark.parametrize(
    ("seconds", "words"),
    [
        (0.21, "2 décimas"),
        (-0.14, "1 décima"),
        (1.04, "1 segundo"),
        (1.34, "1 segundo y 3 décimas"),
        (2.66, "2 segundos y 7 décimas"),
        (0.01, "nada"),
    ],
)
def test_gap_words(seconds: float, words: str) -> None:
    assert gap_words(seconds) == words


def test_lap_time_words() -> None:
    assert lap_time_words(97_831) == "1, 37, 8"
    assert lap_time_words(125_045) == "2, 05, 0"
    assert lap_time_words(58_900) == "58, 9"


def test_sector_call() -> None:
    faster = sector_call(1, 3, 0, -0.21)
    assert faster.kind == "sector"
    assert faster.text == "Sector 1: \u22120.21 s"
    assert faster.speech == "Sector uno, 2 décimas más rápido."
    assert sector_call(2, 3, 1, 0.5).speech == "Sector dos, 5 décimas más lento."
    assert sector_call(3, 3, 1, 0.02).speech == "Sector dos, igual que tu mejor."


def test_lap_call_variants() -> None:
    best = lap_call(1, 4, 97_831, 99_112, new_best=True, off_track=False)
    assert best.kind == "best_lap"
    assert best.speech == "Nueva mejor vuelta. 1, 37, 8. 1 segundo y 3 décimas más rápida."
    slower = lap_call(2, 5, 98_268, 97_831, new_best=False, off_track=False)
    assert slower.text == "Vuelta 5: 1:38.268 (+0.437 s)"
    assert slower.speech == "1, 38, 2. 4 décimas más lenta que tu mejor."
    first = lap_call(3, 1, 114_548, None, new_best=False, off_track=True)
    assert first.speech == "1, 54, 5. Con salida de pista."
    even = lap_call(4, 6, 97_850, 97_831, new_best=False, off_track=False)
    assert "Igual que tu mejor." in even.speech


def _comparison(**target_changes: list[float]) -> LapComparison:
    """1 km on a 5 m grid with one corner at 500 m; the target loses 0.3 s around it."""
    grid = [i * 5.0 for i in range(201)]

    def corner(d: float) -> float:
        return 200.0 - max(0.0, 100.0 - abs(d - 500.0))

    speed = [corner(d) for d in grid]
    brake = [1.0 if 350 <= d < 450 else 0.0 for d in grid]
    throttle = [0.0 if 350 <= d < 550 else 1.0 for d in grid]
    zeros = [0.0] * len(grid)
    reference = Channels(zeros, speed, throttle, brake, [3] * len(grid), zeros, zeros)
    target = Channels(
        zeros,
        target_changes.get("speed", speed),
        target_changes.get("throttle", throttle),
        target_changes.get("brake", brake),
        [3] * len(grid),
        zeros,
        zeros,
    )
    delta = [0.0 if d < 400 else 0.3 if d > 600 else (d - 400) / 200 * 0.3 for d in grid]
    return LapComparison(grid, delta, target, reference)


def test_biggest_loss_finds_the_corner_and_the_reason() -> None:
    grid = [i * 5.0 for i in range(201)]
    early = [1.0 if 330 <= d < 450 else 0.0 for d in grid]
    tip = biggest_loss(_comparison(brake=early))
    assert tip is not None
    assert tip.apex_m == 500.0
    assert tip.loss_s == pytest.approx(0.3)
    assert tip.cause == "Frenaste 20 metros antes."
    call = tip_call(1, 4, tip)
    assert call.kind == "tip"
    assert "curva de los 500 metros, 3 décimas" in call.speech

    slow = [
        s - 10 if 450 <= d <= 550 else s
        for d, s in zip(grid, _comparison().target.speed_kmh, strict=True)
    ]
    slow_tip = biggest_loss(_comparison(speed=slow))
    assert slow_tip is not None
    assert slow_tip.cause == "Pasaste 10 kilómetros por hora más lento por la curva."

    late = [0.0 if 350 <= d < 600 else 1.0 for d in grid]
    late_tip = biggest_loss(_comparison(throttle=late))
    assert late_tip is not None
    assert late_tip.cause == "Aceleraste a fondo 50 metros más tarde."

    exit_speed = [
        s - 5 if d >= 600 else s for d, s in zip(grid, _comparison().target.speed_kmh, strict=True)
    ]
    exit_tip = biggest_loss(_comparison(speed=exit_speed))
    assert exit_tip is not None
    assert exit_tip.cause == "Saliste 5 kilómetros por hora más lento."

    plain = biggest_loss(_comparison())
    assert plain is not None and plain.cause == ""
    assert "Revisa la trazada" in tip_call(2, 4, plain).speech


def test_small_losses_are_not_mentioned() -> None:
    comparison = _comparison()
    small = replace(comparison, delta_s=[v / 10 for v in comparison.delta_s])
    assert biggest_loss(small) is None
    assert biggest_loss(replace(comparison, distance_m=[0.0, 5.0])) is None


def test_incident_speech() -> None:
    assert incident_speech("off_track") == "Fuera de pista."
    assert incident_speech("lockup", "fl") == "Bloqueo, delantera izquierda."
    assert "patinaste" in incident_speech("wheelspin")
    assert incident_speech("other") == ""


def _laps(laps: int, seed: int) -> list[TelemetrySample]:
    return list(FakeSource(laps=laps, seed=seed, track_length_m=TRACK).samples())


def test_tracker_calls_sectors_laps_and_tips() -> None:
    samples = _laps(laps=4, seed=1)
    tracker = LiveTracker(TRACK)
    for s in samples:
        frame = tracker.update(s)
    kinds = [c.kind for c in frame.radio]
    ids = [c.id for c in frame.radio]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    # Lap 1 has no reference: just its time. Laps 2 to 4 get two sector calls each.
    assert kinds[0] == "lap" and frame.radio[0].lap == 1
    assert kinds.count("sector") == 3 * 2
    assert kinds.count("lap") + kinds.count("best_lap") == 3
    assert all(c.speech for c in frame.radio)


def test_tracker_tip_when_a_lap_loses_time_in_one_corner() -> None:
    samples = _laps(laps=3, seed=2)
    lap1 = [s for s in samples if s.lap_number == 1]
    # Lap 2 (index 1) loses 0.5 s in the middle of the lap and brakes much earlier there.
    middle = lap1[len(lap1) // 2 :]
    slowed = {
        id(s): replace(s, lap_time_ms=s.lap_time_ms + 500, last_lap_ms=s.last_lap_ms)
        for s in middle
    }
    edited = [slowed.get(id(s), s) for s in samples]
    first_of_lap2 = next(i for i, s in enumerate(edited) if s.lap_number == 2)
    edited[first_of_lap2] = replace(
        edited[first_of_lap2], last_lap_ms=edited[first_of_lap2 - 1].lap_time_ms
    )
    tracker = LiveTracker(TRACK)
    for s in edited:
        frame = tracker.update(s)
    tips = [c for c in frame.radio if c.kind == "tip"]
    assert len(tips) == 1 and tips[0].lap == 2
    assert "Donde más perdiste" in tips[0].speech


def test_incident_calls_are_spaced_out() -> None:
    samples = _laps(laps=1, seed=4)
    edited = list(samples)
    for start in (100, 150, 600):  # 50 samples apart is well under 3 s at the fake rate
        for i in range(start, start + 10):
            edited[i] = replace(edited[i], tyres_out=4)
    tracker = LiveTracker(TRACK)
    for s in edited:
        frame = tracker.update(s)
    assert [e.kind for e in frame.events].count("off_track") == 3
    incidents = [c for c in frame.radio if c.kind == "incident"]
    assert len(incidents) == 2
    assert incidents[0].speech == "Fuera de pista."


def test_until_reset_drops_reads_after_the_timer_reset() -> None:
    samples = _laps(laps=1, seed=0)[:200]
    reset = [*samples, replace(samples[-1], lap_time_ms=3), replace(samples[-1], lap_time_ms=12)]
    assert _until_reset(reset) == samples
    assert _until_reset(samples) == samples


def test_a_few_reads_before_the_line_are_not_judged() -> None:
    samples = _laps(laps=3, seed=6)
    first_of_lap2 = next(i for i, s in enumerate(samples) if s.lap_number == 1)
    # Start recording 3 reads before the end of lap 1, as when Grabar is pressed at the line.
    tracker = LiveTracker(TRACK)
    for s in samples[first_of_lap2 - 3 :]:
        frame = tracker.update(s)
    laps = [c.lap for c in frame.radio if c.kind in ("lap", "best_lap", "tip")]
    assert 1 not in laps
    assert 2 in laps


def test_a_session_best_slower_than_the_reference_is_not_a_new_best() -> None:
    samples = _laps(laps=3, seed=7)
    tracker = LiveTracker(TRACK)
    for s in samples:
        tracker.update(s)
    assert tracker.reference is not None
    # Race against a reference far faster than anything in this session.
    fast = replace(tracker.reference, time_ms=10_000)
    again = LiveTracker(TRACK, fast)
    for s in samples:
        frame = again.update(s)
    assert not [c for c in frame.radio if c.kind == "best_lap"]
    assert not [e for e in frame.events if e.kind == "best_lap"]
    assert all("más lenta que tu mejor" in c.speech for c in frame.radio if c.kind == "lap")
