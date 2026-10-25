from dataclasses import replace

from raceengineer.adapters.fake import FakeSource
from raceengineer.analysis.laps import segment_laps
from raceengineer.analysis.sectors import best_sectors, ideal_lap_ms, sector_times, with_sectors
from raceengineer.capture.live import LiveSector, LiveTracker
from raceengineer.domain.models import Lap, LapSignals


def _signals(lap_ms: int = 90_000, steps: int = 900) -> list[LapSignals]:
    """One lap at constant speed: position grows in step with the timer."""
    return [
        LapSignals(i * lap_ms / steps / 1000, 0, i * lap_ms // steps, 0, False, 0, i / steps)
        for i in range(steps)
    ]


def test_equal_thirds_at_constant_speed() -> None:
    assert sector_times(_signals(), 90_000) == (30_000, 30_000, 30_000)


def test_line_wrap_at_the_start_is_handled() -> None:
    signals = _signals()
    # Just after the line the spline still reads ~1.0.
    signals[0] = signals[0]._replace(normalized_position=0.999)
    assert sector_times(signals, 90_000) == (30_000, 30_000, 30_000)


def test_unknown_when_the_lap_is_too_short_or_misses_a_sector() -> None:
    assert sector_times(_signals()[:1], 90_000) == ()
    half = _signals()[:450]  # never reaches 2/3 of the track
    assert sector_times(half, 90_000) == ()


def _lap(n: int, sectors: tuple[int, ...], **flags: bool) -> Lap:
    return Lap(
        n,
        0,
        1,
        sum(sectors) or None,
        True,
        flags.get("complete", True),
        flags.get("out_lap", False),
        False,
        flags.get("off_track", False),
        sectors,
    )


def test_best_sectors_and_ideal_lap_use_clean_laps_only() -> None:
    laps = [
        _lap(1, (33_000, 34_000, 32_000)),
        _lap(2, (34_000, 33_000, 31_500)),
        _lap(3, (30_000, 30_000, 30_000), off_track=True),
        _lap(4, ()),
    ]
    assert best_sectors(laps) == (33_000, 33_000, 31_500)
    assert ideal_lap_ms(laps) == 97_500
    assert best_sectors([laps[2]]) == ()
    assert ideal_lap_ms([laps[2]]) is None


def test_with_sectors_from_a_recording() -> None:
    samples = list(FakeSource(laps=3, track_length_m=2000.0).samples())
    signals = [
        LapSignals(
            s.t,
            s.lap_number,
            s.lap_time_ms,
            s.last_lap_ms,
            s.in_pit,
            s.tyres_out,
            s.normalized_position,
        )
        for s in samples
    ]
    laps = with_sectors(segment_laps(signals), signals)
    finished = [lap for lap in laps if lap.time_ms is not None]
    assert all(len(lap.sector_ms) == 3 and sum(lap.sector_ms) == lap.time_ms for lap in finished)
    unfinished = [lap for lap in laps if lap.time_ms is None]
    assert all(lap.sector_ms == () for lap in unfinished)


def test_live_sectors_with_best_flags() -> None:
    samples = list(FakeSource(laps=3, seed=1, track_length_m=2000.0).samples())
    tracker = LiveTracker(2000.0)
    seen_last: list[list[LiveSector]] = []
    for s in samples:
        frame = tracker.update(s)
        if frame.last_sectors and frame.last_sectors != (seen_last[-1] if seen_last else None):
            seen_last.append(frame.last_sectors)
    first, second = seen_last[0], seen_last[1]
    assert [x.number for x in first] == [1, 2, 3]
    assert all(x.best and x.delta_s is None for x in first)  # no reference yet on lap 1
    assert all(x.delta_s is not None for x in second)
    for a, b in zip(first, second, strict=True):
        assert b.best == (b.time_ms <= a.time_ms and b.delta_s is not None and b.delta_s <= 0)


def test_live_off_track_sector_is_never_best() -> None:
    samples = list(FakeSource(laps=2, seed=2, track_length_m=2000.0).samples())
    dirty = [replace(s, tyres_out=4) if 10 <= i < 20 else s for i, s in enumerate(samples)]
    tracker = LiveTracker(2000.0)
    for s in dirty:
        frame = tracker.update(s)
    assert frame.last_sectors and not frame.last_sectors[0].best
