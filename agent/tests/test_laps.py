from dataclasses import replace

from raceengineer.adapters.fake import FakeSource
from raceengineer.analysis.laps import segment_laps
from raceengineer.domain.models import TelemetrySample

BASE = TelemetrySample(
    t=0.0,
    lap_number=0,
    lap_time_ms=0,
    normalized_position=0.0,
    speed_kmh=100.0,
    throttle=1.0,
    brake=0.0,
    clutch=0.0,
    steering=0.0,
    gear=3,
    rpm=6000.0,
    pos_x=0.0,
    pos_y=0.0,
    pos_z=0.0,
    in_pit=False,
)


def _s(t: float, lap: int, lap_ms: int, **changes: object) -> TelemetrySample:
    return replace(BASE, t=t, lap_number=lap, lap_time_ms=lap_ms, **changes)  # type: ignore[arg-type]


def test_fake_session_laps_use_official_times() -> None:
    samples = list(FakeSource(laps=3).samples())

    laps = segment_laps(samples)

    assert [lap.number for lap in laps] == [1, 2, 3]
    assert [lap.complete for lap in laps] == [True, True, False]
    assert all(lap.official for lap in laps[:2])
    for lap in laps[:2]:
        assert lap.time_ms is not None
        last = samples[lap.end - 1]
        assert abs(lap.time_ms - last.lap_time_ms) < 20
    assert laps[2].time_ms is None


def test_official_time_comes_from_first_samples_after_the_line() -> None:
    samples = [
        _s(0.0, 0, 0),
        _s(60.0, 0, 60_000),
        _s(60.1, 1, 50, last_lap_ms=0),  # the game may publish it a frame late
        _s(60.2, 1, 150, last_lap_ms=60_050),
    ]

    [lap, _] = segment_laps(samples)

    assert (lap.time_ms, lap.official, lap.complete) == (60_050, True, True)


def test_estimates_time_when_game_time_is_missing() -> None:
    samples = [_s(0.0, 0, 0), _s(59.98, 0, 59_980), _s(60.08, 1, 70), _s(62.0, 1, 1_990)]

    [lap, _] = segment_laps(samples)

    assert (lap.time_ms, lap.official) == (60_010, False)


def test_recording_started_mid_lap_is_incomplete_but_timed() -> None:
    samples = [
        _s(0.0, 0, 15_000, in_pit=True),
        _s(100.0, 0, 115_000),
        _s(100.1, 1, 50, last_lap_ms=115_040),
    ]

    [lap, _] = segment_laps(samples)

    assert lap.complete is False
    assert lap.time_ms == 115_040
    assert lap.out_lap is True


def test_in_lap_and_off_track() -> None:
    samples = [
        _s(0.0, 2, 0),
        _s(10.0, 2, 10_000, tyres_out=2),
        _s(20.0, 2, 20_000, tyres_out=4),
        _s(30.0, 2, 30_000, in_pit=True),
    ]

    [lap] = segment_laps(samples)

    assert lap.number == 3
    assert lap.in_lap and lap.off_track
    assert lap.time_ms is None


def test_restart_splits_without_a_time() -> None:
    samples = [_s(0.0, 0, 0), _s(30.0, 0, 30_000), _s(31.0, 0, 200), _s(40.0, 0, 9_200)]

    laps = segment_laps(samples)

    assert [(lap.start, lap.end, lap.time_ms) for lap in laps] == [(0, 2, None), (2, 4, None)]


def test_counter_reset_is_not_a_line_crossing() -> None:
    samples = [_s(0.0, 3, 0), _s(10.0, 3, 10_000), _s(11.0, 0, 100, last_lap_ms=90_000)]

    first = segment_laps(samples)[0]

    assert first.time_ms is None


def test_empty_recording() -> None:
    assert segment_laps([]) == []


def test_read_with_timer_reset_before_counter_bump() -> None:
    # Seen on the PC: the lap timer is zeroed one read before the lap counter moves.
    samples = [
        _s(0.0, 1, 0),
        _s(138.45, 1, 138_450),
        _s(138.464, 1, 5),  # timer reset, counter still 1
        _s(138.478, 2, 19),
        _s(150.0, 2, 11_541),
    ]

    laps = segment_laps(samples)

    assert [(lap.number, lap.start, lap.end) for lap in laps] == [(2, 0, 2), (3, 2, 5)]
    assert laps[0].time_ms == 138_459
    assert laps[0].complete and laps[1].start == 2


def test_read_with_counter_bump_before_timer_reset() -> None:
    samples = [
        _s(0.0, 1, 0),
        _s(138.45, 1, 138_450),
        _s(138.464, 2, 138_464),  # counter moved, timer not reset yet
        _s(138.478, 2, 10),
        _s(150.0, 2, 11_532),
    ]

    laps = segment_laps(samples)

    assert [(lap.number, lap.start, lap.end) for lap in laps] == [(2, 0, 3), (3, 3, 5)]
    assert laps[0].time_ms == 138_468


def test_counter_bump_with_stale_official_time_is_still_read() -> None:
    samples = [
        _s(0.0, 1, 0, last_lap_ms=150_000),
        _s(138.45, 1, 138_450, last_lap_ms=150_000),
        _s(138.464, 1, 5, last_lap_ms=150_000),
        _s(138.478, 2, 19, last_lap_ms=138_459),
    ]

    [lap, _] = segment_laps(samples)

    assert (lap.time_ms, lap.official) == (138_459, True)


def test_default_reference_prefers_clean_laps() -> None:
    from raceengineer.analysis.laps import default_reference
    from raceengineer.domain.models import Lap

    clean = Lap(1, 0, 10, 100_000, True, True, False, False, False)
    dirty_fast = Lap(2, 10, 20, 90_000, True, True, False, False, True)
    unfinished = Lap(3, 20, 30, None, False, False, False, False, False)

    assert default_reference([clean, dirty_fast, unfinished]) == (clean, True)
    # No clean lap left: fall back to the fastest finished one, flagged as not clean.
    assert default_reference([clean, dirty_fast], exclude=clean) == (dirty_fast, False)
    assert default_reference([dirty_fast, unfinished], exclude=dirty_fast) == (None, False)


def test_recording_that_starts_on_a_mid_update_read() -> None:
    # Seen when recording started right at the line: timer already reset,
    # counter still on the previous lap, and no earlier sample to compare.
    samples = [
        _s(0.0, 6, 9, last_lap_ms=108_852),
        _s(0.0, 6, 9, last_lap_ms=108_852),
        _s(0.016, 7, 21, last_lap_ms=108_852),
        _s(60.0, 7, 60_000, last_lap_ms=108_852),
    ]

    [lap] = segment_laps(samples)

    assert (lap.number, lap.start, lap.end) == (8, 0, 4)


def test_impossibly_short_laps_are_not_finished() -> None:
    samples = [_s(0.0, 0, 0), _s(3.0, 0, 3_000), _s(3.1, 1, 50, last_lap_ms=3_040)]

    [short, _] = segment_laps(samples)

    assert (short.time_ms, short.complete) == (None, False)
