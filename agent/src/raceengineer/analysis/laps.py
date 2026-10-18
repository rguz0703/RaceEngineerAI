"""Splits a recording into laps."""

from collections.abc import Sequence

from raceengineer.domain.models import Lap, TelemetrySample

START_TOLERANCE_MS = 1000
"""A lap whose first sample shows at most this much on the lap timer was recorded
from the line. Larger means the recording started mid-lap (or the samples near the
line were lost)."""

OFF_TRACK_TYRES = 3
"""Wheels outside the track limits that count as leaving the track."""


def segment_laps(samples: Sequence[TelemetrySample]) -> list[Lap]:
    """Group samples into laps using the game's lap counter and lap timer.

    A new lap starts when the lap counter changes, or when the lap timer jumps
    back without it (the session was restarted). The time of a finished lap is
    the game's own "last lap" figure read right after the line; recordings made
    before that field existed fall back to an estimate from the lap timer.
    """
    numbers = _lap_numbers(samples)
    bounds = _lap_bounds(samples, numbers)
    laps = []
    for i, (start, end) in enumerate(bounds):
        first, last = samples[start], samples[end - 1]
        crossed_line = end < len(samples) and numbers[end] == numbers[end - 1] + 1
        time_ms: int | None = None
        official = False
        if crossed_line:
            next_end = bounds[i + 1][1]
            time_ms = _official_time(samples, end, next_end, first.last_lap_ms)
            official = time_ms is not None
            if time_ms is None:
                time_ms = _estimated_time(last, samples[end])
        laps.append(
            Lap(
                number=numbers[start] + 1,
                start=start,
                end=end,
                time_ms=time_ms,
                official=official,
                complete=crossed_line and first.lap_time_ms <= START_TOLERANCE_MS,
                out_lap=first.in_pit,
                in_lap=last.in_pit,
                off_track=any(s.tyres_out >= OFF_TRACK_TYRES for s in samples[start:end]),
            )
        )
    return laps


def _lap_numbers(samples: Sequence[TelemetrySample]) -> list[int]:
    """The lap each sample belongs to, repairing reads taken mid-update at the line.

    AC resets the lap timer and bumps the lap counter in separate writes, so a
    read can catch one change without the other (seen on the PC at ~70 Hz):

    - timer already reset, counter not yet: those reads belong to the new lap;
    - counter already bumped, timer not yet reset: they belong to the old lap.
    """
    numbers = [s.lap_number for s in samples]
    n = len(samples)
    for i in range(1, n):
        prev, cur = samples[i - 1], samples[i]
        if cur.lap_number == prev.lap_number and _timer_reset(prev, cur):
            j = i
            while j < n and samples[j].lap_number == prev.lap_number and _just_started(samples[j]):
                j += 1
            if i < j < n and samples[j].lap_number == prev.lap_number + 1:
                numbers[i:j] = [prev.lap_number + 1] * (j - i)
        elif cur.lap_number == prev.lap_number + 1 and not _just_started(cur):
            j = i
            while (
                j < n
                and samples[j].lap_number == cur.lap_number
                and samples[j].lap_time_ms >= prev.lap_time_ms
                and samples[j].t - cur.t <= _GLITCH_WINDOW_S
            ):
                j += 1
            if (
                j < n
                and samples[j].lap_number == cur.lap_number
                and _timer_reset(samples[j - 1], samples[j])
            ):
                numbers[i:j] = [prev.lap_number] * (j - i)
    return numbers


_GLITCH_WINDOW_S = 1.0


def _timer_reset(prev: TelemetrySample, cur: TelemetrySample) -> bool:
    return cur.lap_time_ms + START_TOLERANCE_MS < prev.lap_time_ms


def _just_started(sample: TelemetrySample) -> bool:
    return sample.lap_time_ms <= START_TOLERANCE_MS


def _lap_bounds(samples: Sequence[TelemetrySample], numbers: list[int]) -> list[tuple[int, int]]:
    bounds = []
    start = 0
    for i in range(1, len(samples)):
        restarted = numbers[i] == numbers[i - 1] and _timer_reset(samples[i - 1], samples[i])
        if numbers[i] != numbers[i - 1] or restarted:
            bounds.append((start, i))
            start = i
    if samples:
        bounds.append((start, len(samples)))
    return bounds


def _official_time(
    samples: Sequence[TelemetrySample], start: int, end: int, previous_last_lap_ms: int
) -> int | None:
    """The game's last-lap time, read from the first samples after the line."""
    for sample in samples[start:end]:
        if sample.lap_time_ms > START_TOLERANCE_MS:
            break
        if sample.last_lap_ms > 0 and sample.last_lap_ms != previous_last_lap_ms:
            return sample.last_lap_ms
    return None


def _estimated_time(last: TelemetrySample, following: TelemetrySample) -> int:
    """Timer before the line + time between the two samples - timer after the line."""
    gap_ms = (following.t - last.t) * 1000
    return max(0, round(last.lap_time_ms + gap_ms - following.lap_time_ms))
