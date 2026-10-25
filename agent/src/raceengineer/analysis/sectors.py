"""Sector times: each lap split into equal thirds of the track, as timing screens do."""

from collections.abc import Sequence
from dataclasses import replace
from itertools import pairwise

from raceengineer.analysis.compare import unwrap_positions
from raceengineer.analysis.laps import best_clean_lap
from raceengineer.domain.models import Lap, LapSignals

SECTORS = 3


def sector_times(signals: Sequence[LapSignals], lap_time_ms: int) -> tuple[int, ...]:
    """Time spent in each sector of one complete lap, in ms; empty if it can't be told."""
    if len(signals) < 2:
        return ()
    positions = unwrap_positions(
        [s.normalized_position for s in signals], [s.lap_time_ms for s in signals]
    )
    splits: list[float] = []
    i = 1
    for k in range(1, SECTORS):
        boundary = k / SECTORS
        while i < len(positions) and positions[i] < boundary:
            i += 1
        if i >= len(positions) or positions[i - 1] > boundary:
            return ()
        a, b = positions[i - 1], positions[i]
        f = (boundary - a) / (b - a) if b > a else 1.0
        t0, t1 = signals[i - 1].lap_time_ms, signals[i].lap_time_ms
        splits.append(t0 + (t1 - t0) * f)
    edges = [0.0, *splits, float(lap_time_ms)]
    times = tuple(round(b - a) for a, b in pairwise(edges))
    return times if all(t > 0 for t in times) else ()


def with_sectors(laps: Sequence[Lap], signals: Sequence[LapSignals]) -> list[Lap]:
    """The laps with their sector times filled in where the lap was recorded whole."""
    return [
        replace(lap, sector_ms=sector_times(signals[lap.start : lap.end], lap.time_ms))
        if lap.complete and lap.time_ms is not None
        else lap
        for lap in laps
    ]


def _clean(lap: Lap) -> bool:
    return (
        lap.time_ms is not None
        and lap.complete
        and not (lap.off_track or lap.out_lap or lap.in_lap)
        and len(lap.sector_ms) == SECTORS
    )


def best_sectors(laps: Sequence[Lap]) -> tuple[int, ...]:
    """The fastest time in each sector among clean laps; empty without any."""
    clean = [lap for lap in laps if _clean(lap)]
    if not clean:
        return ()
    return tuple(min(lap.sector_ms[k] for lap in clean) for k in range(SECTORS))


def ideal_lap_ms(laps: Sequence[Lap]) -> int | None:
    """Your best sectors put together: what the session says you can do."""
    best = best_sectors(laps)
    if not best or best_clean_lap(laps) is None:
        return None
    return sum(best)
