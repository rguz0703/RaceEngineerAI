from dataclasses import replace
from pathlib import Path

import pytest

from raceengineer.adapters.fake import FakeSource
from raceengineer.analysis.compare import compare_laps, lap_trace, summarize, write_csv
from raceengineer.analysis.laps import segment_laps
from raceengineer.domain.models import Lap, TelemetrySample

TRACK_M = 2000.0


def _fake_laps(laps: int = 3) -> tuple[list[TelemetrySample], list[Lap]]:
    samples = list(FakeSource(laps=laps, track_length_m=TRACK_M, seed=7).samples())
    return samples, segment_laps(samples)


def test_total_delta_equals_lap_time_difference() -> None:
    samples, laps = _fake_laps()
    first, second = laps[0], laps[1]
    assert first.time_ms is not None and second.time_ms is not None

    comparison = compare_laps(
        lap_trace(samples, second, TRACK_M), lap_trace(samples, first, TRACK_M)
    )

    assert comparison.distance_m[0] == 0.0
    assert comparison.distance_m[-1] == TRACK_M
    assert comparison.delta_s[-1] == pytest.approx((second.time_ms - first.time_ms) / 1000)
    assert comparison.delta_s[0] == 0.0


def test_comparing_a_lap_with_itself_gives_zero_delta() -> None:
    samples, laps = _fake_laps()
    trace = lap_trace(samples, laps[0], TRACK_M)

    comparison = compare_laps(trace, trace, step_m=10)

    assert max(abs(d) for d in comparison.delta_s) < 1e-9
    assert comparison.target.gear == comparison.reference.gear


def test_track_length_is_integrated_when_unknown() -> None:
    samples, laps = _fake_laps()
    assert lap_trace(samples, laps[0]).length_m == pytest.approx(TRACK_M, rel=0.02)


def test_positions_are_unwrapped_at_the_line() -> None:
    samples, laps = _fake_laps()
    lap = laps[1]
    lap_samples = samples[lap.start : lap.end]
    # The spline can still read ~1.0 just after the line and ~0.0 just before it.
    lap_samples[0] = replace(lap_samples[0], normalized_position=0.9995)
    lap_samples[-1] = replace(lap_samples[-1], normalized_position=0.0005)
    shifted = samples[: lap.start] + lap_samples + samples[lap.end :]

    distance = lap_trace(shifted, lap, TRACK_M).distance_m

    assert distance[0] == 0.0
    assert distance == sorted(distance)
    assert distance[-1] == TRACK_M


def test_summary_segments_add_up_to_total() -> None:
    samples, laps = _fake_laps()
    comparison = compare_laps(
        lap_trace(samples, laps[1], TRACK_M), lap_trace(samples, laps[0], TRACK_M)
    )

    segments = summarize(comparison, segments=4)

    assert len(segments) == 4
    assert segments[0].start_m == 0.0
    assert segments[-1].end_m == TRACK_M
    assert sum(s.delta_s for s in segments) == pytest.approx(comparison.delta_s[-1])
    assert all(s.target_min_speed_kmh <= s.target_avg_speed_kmh for s in segments)


def test_csv_has_one_row_per_point(tmp_path: Path) -> None:
    samples, laps = _fake_laps()
    trace = lap_trace(samples, laps[0], TRACK_M)
    comparison = compare_laps(trace, trace, step_m=100)
    path = tmp_path / "out" / "cmp.csv"

    write_csv(comparison, path)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("distance_m,delta_s,speed_kmh")
    assert len(lines) == len(comparison.distance_m) + 1


def test_invalid_arguments() -> None:
    samples, laps = _fake_laps()
    trace = lap_trace(samples, laps[0], TRACK_M)
    with pytest.raises(ValueError):
        compare_laps(trace, trace, step_m=0)
    with pytest.raises(ValueError):
        summarize(compare_laps(trace, trace), segments=0)
    with pytest.raises(ValueError):
        lap_trace(samples, replace(laps[0], end=laps[0].start))


def test_laps_without_common_stretch() -> None:
    samples, laps = _fake_laps()
    lap = laps[0]
    early = replace(lap, end=lap.start + 10, time_ms=None, complete=False)
    late_start = lap.end - 10
    late = replace(lap, start=late_start, complete=False)
    with pytest.raises(ValueError, match="en común"):
        compare_laps(lap_trace(samples, early, TRACK_M), lap_trace(samples, late, TRACK_M))
