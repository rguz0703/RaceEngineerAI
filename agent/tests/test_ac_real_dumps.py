"""Sanity checks on raw dumps recorded with the real game (agent/tests/fixtures/*.acraw.gz)."""

from pathlib import Path

import pytest

from raceengineer.adapters.ac_raw_dump import RawDumpReader
from raceengineer.adapters.ac_shared_memory import ACSharedMemorySource

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.acraw.gz"))


@pytest.mark.skipif(not FIXTURES, reason="todavía no hay volcados reales de AC")
@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_real_dump_replays_to_plausible_samples(path: Path) -> None:
    reader = RawDumpReader(path)
    try:
        source = ACSharedMemorySource(reader, clock=reader.clock, sleep=lambda _: None)
        info = source.session_info()
        samples = list(source.samples())
    finally:
        reader.close()

    assert info.track
    assert info.car
    assert samples
    assert all(0.0 <= s.normalized_position <= 1.0 for s in samples)
    assert all(0.0 <= s.speed_kmh < 500.0 for s in samples)
    assert all(-1 <= s.gear <= 10 for s in samples)
    laps = [s.lap_number for s in samples]
    assert laps == sorted(laps)
    times = [s.t for s in samples]
    assert times == sorted(times)


MONZA = Path(__file__).parent / "fixtures" / "ac_monza_911cup.acraw.gz"


@pytest.mark.skipif(not MONZA.exists(), reason="falta el volcado de Monza")
def test_monza_dump_matches_what_was_driven() -> None:
    """Recorded 2026-10-17 on the PC: AC 1.16.4, practice at Monza, 30 s with a pause."""
    reader = RawDumpReader(MONZA)
    try:
        source = ACSharedMemorySource(reader, clock=reader.clock, sleep=lambda _: None)
        info = source.session_info()
        samples = list(source.samples())
    finally:
        reader.close()

    assert (info.track, info.car, info.track_config) == (
        "monza",
        "ks_porsche_911_gt3_cup_2017",
        "",
    )
    # 287 paused frames are skipped; only the LIVE ones become samples.
    assert len(samples) == 4600
    assert max(s.speed_kmh for s in samples) == pytest.approx(241.9, abs=0.1)
    assert {s.gear for s in samples} == set(range(0, 7))  # neutral (mid-shift) to 6th
    # AC's own lap timer advances exactly as the recording clock does.
    elapsed_ms = samples[-1].lap_time_ms - samples[0].lap_time_ms
    assert elapsed_ms == pytest.approx((samples[-1].t - samples[0].t) * 1000, abs=1)


CALIBRATION = Path(__file__).parent / "fixtures" / "ac_calibration.acraw.gz"


@pytest.mark.skipif(not CALIBRATION.exists(), reason="falta el volcado de calibración")
def test_calibration_dump_steering_is_normalized_left_negative() -> None:
    """Recorded 2026-10-17, parked in the Monza pits with a Logitech G923.

    Order of inputs: full left, full right, then full throttle.
    """
    reader = RawDumpReader(CALIBRATION)
    try:
        source = ACSharedMemorySource(reader, clock=reader.clock, sleep=lambda _: None)
        samples = list(source.samples())
    finally:
        reader.close()

    steering = [s.steering for s in samples]
    first_full_left = steering.index(-1.0)
    first_full_right = steering.index(1.0)
    assert first_full_left < first_full_right
    assert max(s.throttle for s in samples) == 1.0
    assert all(s.speed_kmh < 1.0 and s.in_pit for s in samples)
