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
