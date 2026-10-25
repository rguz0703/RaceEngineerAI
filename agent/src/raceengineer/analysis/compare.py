"""Compares two laps along the track, metre by metre instead of second by second."""

import csv
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from raceengineer.domain.models import Lap, TelemetrySample

_START_MS = 1000
"""A lap timer at or below this means the sample is right after the line."""


@dataclass(frozen=True, slots=True)
class LapTrace:
    """One lap's channels against distance from the line."""

    length_m: float
    distance_m: list[float]
    """Non-decreasing."""
    time_s: list[float]
    """The game's lap timer."""
    speed_kmh: list[float]
    throttle: list[float]
    brake: list[float]
    gear: list[int]
    pos_x: list[float]
    pos_z: list[float]
    """Horizontal world position (the game's Y axis is height)."""


@dataclass(frozen=True, slots=True)
class Channels:
    time_s: list[float]
    speed_kmh: list[float]
    throttle: list[float]
    brake: list[float]
    gear: list[int]
    pos_x: list[float]
    pos_z: list[float]


@dataclass(frozen=True, slots=True)
class LapComparison:
    """Two laps resampled on a common distance grid."""

    distance_m: list[float]
    delta_s: list[float]
    """Time the target has lost (+) or gained (-) on the reference up to each point."""
    target: Channels
    reference: Channels


@dataclass(frozen=True, slots=True)
class SegmentSummary:
    start_index: int
    end_index: int
    start_m: float
    end_m: float
    delta_s: float
    """Time lost (+) or gained (-) within this segment only."""
    target_min_speed_kmh: float
    reference_min_speed_kmh: float
    target_avg_speed_kmh: float
    reference_avg_speed_kmh: float


def lap_trace(
    samples: Sequence[TelemetrySample], lap: Lap, track_length_m: float = 0.0
) -> LapTrace:
    """Build a lap's trace. Without a known track length it is integrated from speed."""
    lap_samples = list(samples[lap.start : lap.end])
    if not lap_samples:
        raise ValueError(f"La vuelta {lap.number} no tiene muestras")
    length = track_length_m if track_length_m > 0 else _integrated_length(lap_samples)
    distance = lap_distances(lap_samples, length)
    trace = LapTrace(
        length_m=length,
        distance_m=distance,
        time_s=[s.lap_time_ms / 1000 for s in lap_samples],
        speed_kmh=[s.speed_kmh for s in lap_samples],
        throttle=[s.throttle for s in lap_samples],
        brake=[s.brake for s in lap_samples],
        gear=[s.gear for s in lap_samples],
        pos_x=[s.pos_x for s in lap_samples],
        pos_z=[s.pos_z for s in lap_samples],
    )
    # Pin the ends to the line so totals match the official lap time exactly.
    if lap.complete and distance[0] > 0:
        _insert(trace, 0, 0.0, 0.0, lap_samples[0])
    if lap.time_ms is not None and distance[-1] < length:
        _insert(trace, len(trace.distance_m), length, lap.time_ms / 1000, lap_samples[-1])
    return trace


def lap_distances(lap_samples: Sequence[TelemetrySample], length_m: float) -> list[float]:
    """Distance from the line for each sample of one lap (non-decreasing)."""
    positions = unwrap_positions(
        [s.normalized_position for s in lap_samples], [s.lap_time_ms for s in lap_samples]
    )
    distance: list[float] = []
    reached = 0.0
    for position in positions:
        reached = max(reached, min(1.0, max(0.0, position)) * length_m)
        distance.append(reached)
    return distance


def compare_laps(target: LapTrace, reference: LapTrace, step_m: float = 5.0) -> LapComparison:
    """Resample both laps every ``step_m`` metres over the stretch both cover."""
    if step_m <= 0:
        raise ValueError("step_m must be > 0")
    start = max(target.distance_m[0], reference.distance_m[0])
    end = min(target.distance_m[-1], reference.distance_m[-1])
    if end <= start:
        raise ValueError("Las vueltas no tienen tramo de pista en común")
    count = int((end - start) / step_m)
    grid = [start + i * step_m for i in range(count + 1)]
    if grid[-1] < end:
        grid.append(end)

    target_channels = _resample(target, grid)
    reference_channels = _resample(reference, grid)
    offset = target_channels.time_s[0] - reference_channels.time_s[0]
    delta = [
        t - r - offset
        for t, r in zip(target_channels.time_s, reference_channels.time_s, strict=True)
    ]
    return LapComparison(
        distance_m=grid, delta_s=delta, target=target_channels, reference=reference_channels
    )


def summarize(comparison: LapComparison, segments: int = 10) -> list[SegmentSummary]:
    """Split the compared stretch into equal segments."""
    if segments < 1:
        raise ValueError("segments must be >= 1")
    d = comparison.distance_m
    span = d[-1] - d[0]
    summaries = []
    first = 0
    for k in range(1, segments + 1):
        boundary = d[0] + span * k / segments
        last = min(len(d) - 1, max(first + 1, bisect_right(d, boundary) - 1))
        if k == segments:
            last = len(d) - 1
        window = slice(first, last + 1)
        target_speed = comparison.target.speed_kmh[window]
        reference_speed = comparison.reference.speed_kmh[window]
        summaries.append(
            SegmentSummary(
                start_index=first,
                end_index=last,
                start_m=d[first],
                end_m=d[last],
                delta_s=comparison.delta_s[last] - comparison.delta_s[first],
                target_min_speed_kmh=min(target_speed),
                reference_min_speed_kmh=min(reference_speed),
                target_avg_speed_kmh=sum(target_speed) / len(target_speed),
                reference_avg_speed_kmh=sum(reference_speed) / len(reference_speed),
            )
        )
        first = last
    return summaries


def write_csv(comparison: LapComparison, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    t, r = comparison.target, comparison.reference
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "distance_m",
                "delta_s",
                "speed_kmh",
                "ref_speed_kmh",
                "throttle",
                "ref_throttle",
                "brake",
                "ref_brake",
                "gear",
                "ref_gear",
            ]
        )
        for i, d in enumerate(comparison.distance_m):
            writer.writerow(
                [
                    f"{d:.1f}",
                    f"{comparison.delta_s[i]:.3f}",
                    f"{t.speed_kmh[i]:.1f}",
                    f"{r.speed_kmh[i]:.1f}",
                    f"{t.throttle[i]:.3f}",
                    f"{r.throttle[i]:.3f}",
                    f"{t.brake[i]:.3f}",
                    f"{r.brake[i]:.3f}",
                    t.gear[i],
                    r.gear[i],
                ]
            )


def unwrap_positions(positions: list[float], lap_times_ms: list[int]) -> list[float]:
    """Make track position continuous across the line.

    Just after the line the spline can still read ~1.0, and just before it ~0.0.
    A lap that starts on the timer's zero cannot be near the end of the track, and
    a jump of more than half a lap between samples is a wrap, not real movement.
    """
    unwrapped: list[float] = []
    for p, lap_ms in zip(positions, lap_times_ms, strict=True):
        if not unwrapped:
            p = p - 1 if lap_ms <= _START_MS and p > 0.5 else p
        else:
            while p - unwrapped[-1] < -0.5:
                p += 1
            while p - unwrapped[-1] > 0.5:
                p -= 1
        unwrapped.append(p)
    return unwrapped


def _integrated_length(samples: list[TelemetrySample]) -> float:
    total = 0.0
    for prev, cur in pairwise(samples):
        dt = max(0.0, (cur.lap_time_ms - prev.lap_time_ms) / 1000)
        total += (prev.speed_kmh + cur.speed_kmh) / 2 / 3.6 * dt
    return total


def _insert(
    trace: LapTrace, index: int, distance: float, time: float, like: TelemetrySample
) -> None:
    trace.distance_m.insert(index, distance)
    trace.time_s.insert(index, time)
    trace.speed_kmh.insert(index, like.speed_kmh)
    trace.throttle.insert(index, like.throttle)
    trace.brake.insert(index, like.brake)
    trace.gear.insert(index, like.gear)
    trace.pos_x.insert(index, like.pos_x)
    trace.pos_z.insert(index, like.pos_z)


def _resample(trace: LapTrace, grid: list[float]) -> Channels:
    times, speeds, throttles, brakes, gears, xs, zs = [], [], [], [], [], [], []
    d = trace.distance_m
    for x in grid:
        hi = min(len(d) - 1, max(1, bisect_right(d, x)))
        lo = hi - 1
        span = d[hi] - d[lo]
        f = (x - d[lo]) / span if span > 0 else 1.0
        f = min(1.0, max(0.0, f))
        times.append(_lerp(trace.time_s, lo, hi, f))
        speeds.append(_lerp(trace.speed_kmh, lo, hi, f))
        throttles.append(_lerp(trace.throttle, lo, hi, f))
        brakes.append(_lerp(trace.brake, lo, hi, f))
        gears.append(trace.gear[lo] if f < 1.0 else trace.gear[hi])
        xs.append(_lerp(trace.pos_x, lo, hi, f))
        zs.append(_lerp(trace.pos_z, lo, hi, f))
    return Channels(
        time_s=times,
        speed_kmh=speeds,
        throttle=throttles,
        brake=brakes,
        gear=gears,
        pos_x=xs,
        pos_z=zs,
    )


def _lerp(values: list[float], lo: int, hi: int, f: float) -> float:
    return values[lo] + (values[hi] - values[lo]) * f
