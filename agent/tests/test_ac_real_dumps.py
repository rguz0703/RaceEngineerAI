"""Sanity checks on raw dumps recorded with the real game (agent/tests/fixtures/*.acraw.gz)."""

from pathlib import Path

import pytest

from raceengineer.adapters.ac_raw_dump import RawDumpReader
from raceengineer.adapters.ac_shared_memory import ACSharedMemorySource
from raceengineer.analysis.car import summarize_car
from raceengineer.analysis.compare import compare_laps, lap_trace, summarize
from raceengineer.analysis.diagnosis import diagnose, lap_data
from raceengineer.analysis.laps import segment_laps

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


F3_LAPS = Path(__file__).parent / "fixtures" / "ac_f3_vueltas.acraw.gz"


@pytest.mark.skipif(not F3_LAPS.exists(), reason="falta el volcado de vueltas")
def test_f3_dump_laps_match_the_game() -> None:
    """Recorded 2026-10-17 at 10 Hz: start parked in the pits (brake, clutch), out lap,
    clean lap, lap with chicane cuts ending in the pit lane, then a drive-through."""
    reader = RawDumpReader(F3_LAPS)
    try:
        source = ACSharedMemorySource(reader, clock=reader.clock, sleep=lambda _: None)
        samples = list(source.samples())
    finally:
        reader.close()

    laps = segment_laps(samples)

    summary = [
        (lap.number, lap.time_ms, lap.official, lap.complete, lap.out_lap, lap.in_lap)
        for lap in laps
    ]
    assert summary == [
        (1, 159_827, True, False, True, False),
        (2, 132_748, True, True, False, False),
        (3, 117_793, True, True, False, True),
        (4, None, False, False, True, False),
    ]
    assert [lap.off_track for lap in laps] == [True, False, True, True]
    # Pedals while parked: AC reports clutch 1.0 released, so ours reads 1.0 pressed.
    assert max(s.brake for s in samples) == 1.0
    assert max(s.clutch for s in samples) == 1.0


@pytest.mark.skipif(not F3_LAPS.exists(), reason="falta el volcado de vueltas")
def test_f3_dump_lap_comparison() -> None:
    reader = RawDumpReader(F3_LAPS)
    try:
        source = ACSharedMemorySource(reader, clock=reader.clock, sleep=lambda _: None)
        info = source.session_info()
        samples = list(source.samples())
    finally:
        reader.close()
    laps = segment_laps(samples)

    comparison = compare_laps(
        lap_trace(samples, laps[2], info.track_length_m),
        lap_trace(samples, laps[1], info.track_length_m),
    )

    assert info.track_length_m == pytest.approx(5758.7, abs=0.1)
    assert comparison.delta_s[-1] == pytest.approx((117_793 - 132_748) / 1000)
    # Lap 3 cut the first chicane and ended through the pit lane.
    segments = summarize(comparison)
    assert segments[1].delta_s < -3
    assert segments[-1].delta_s > 0


@pytest.mark.skipif(not F3_LAPS.exists(), reason="falta el volcado de vueltas")
def test_f3_dump_car_state_and_notes() -> None:
    reader = RawDumpReader(F3_LAPS)
    try:
        source = ACSharedMemorySource(reader, clock=reader.clock, sleep=lambda _: None)
        info = source.session_info()
        samples = list(source.samples())
    finally:
        reader.close()
    laps = segment_laps(samples)
    length = info.track_length_m

    car = summarize_car(samples, laps[1])
    assert info.tyre_compound == "Slick Cup (H)"
    assert car is not None
    assert 20 < car.tyres[0].pressure_psi < 30
    assert car.brake_bias == pytest.approx(0.62)
    # Laps 1 and 3 locked the front left under braking (slip ratio near -0.7).
    assert min(s.slip_ratio_fl for s in samples) < -0.5

    comparison = compare_laps(
        lap_trace(samples, laps[1], length), lap_trace(samples, laps[2], length)
    )
    notes = diagnose(
        lap_data(samples, laps[1], length),
        lap_data(samples, laps[2], length),
        summarize(comparison),
        car,
    )
    # The clean lap lost ~5 s in T2 to a lap that cut the first chicane.
    t2 = [n.text for n in notes if n.segment == 1]
    assert any("antes que en la referencia" in t for t in t2)
