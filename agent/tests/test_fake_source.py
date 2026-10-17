import pytest

from raceengineer.adapters.fake import FakeSource


def test_produces_requested_laps_with_consistent_lap_counter() -> None:
    samples = list(FakeSource(laps=2).samples())

    assert samples[0].lap_number == 0
    assert samples[-1].lap_number == 1
    lap_numbers = [s.lap_number for s in samples]
    assert lap_numbers == sorted(lap_numbers)


def test_lap_time_resets_when_crossing_the_line() -> None:
    samples = list(FakeSource(laps=2).samples())
    first_of_lap_2 = next(s for s in samples if s.lap_number == 1)

    assert first_of_lap_2.lap_time_ms < 100
    assert samples[-1].lap_time_ms > 10_000


def test_values_stay_within_normalized_ranges() -> None:
    for s in FakeSource(laps=1).samples():
        assert 0.0 <= s.normalized_position < 1.0
        assert 0.0 <= s.throttle <= 1.0
        assert 0.0 <= s.brake <= 1.0
        assert -1.0 <= s.steering <= 1.0
        assert 1 <= s.gear <= 6
        assert s.speed_kmh > 0
        assert not (s.throttle > 0 and s.brake > 0)


def test_car_brakes_and_slows_for_corners() -> None:
    samples = list(FakeSource(laps=1).samples())

    assert any(s.brake > 0 for s in samples)
    assert min(s.speed_kmh for s in samples) < 100
    assert max(s.speed_kmh for s in samples) > 200


def test_same_seed_is_reproducible_and_different_seed_differs() -> None:
    a = list(FakeSource(laps=2, seed=1).samples())
    b = list(FakeSource(laps=2, seed=1).samples())
    c = list(FakeSource(laps=2, seed=2).samples())

    assert a == b
    assert len(a) != len(c) or a != c


def test_rejects_invalid_arguments() -> None:
    with pytest.raises(ValueError):
        FakeSource(laps=0)
    with pytest.raises(ValueError):
        FakeSource(rate_hz=0)
