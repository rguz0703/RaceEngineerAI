from dataclasses import replace

import pytest

from raceengineer.adapters.fake import FakeSource
from raceengineer.analysis.highlights import lap_highlights
from raceengineer.analysis.laps import segment_laps
from raceengineer.domain.models import TelemetrySample

TRACK = 2000.0


def _lap(seed: int = 0) -> list[TelemetrySample]:
    samples = list(FakeSource(laps=2, seed=seed, track_length_m=TRACK).samples())
    lap = segment_laps(samples)[0]
    return samples[lap.start : lap.end]


def test_key_moments_of_a_clean_lap() -> None:
    samples = _lap()
    h = lap_highlights(samples, TRACK)

    kinds = [m.kind for m in h.moments]
    assert kinds[0] == "top_speed" and kinds[1] == "braking"
    assert kinds.count("corner") == 3  # the synthetic track has three corners
    top = h.moments[0]
    assert top.value == f"{max(s.speed_kmh for s in samples):.0f} km/h"
    braking = h.moments[1]
    assert braking.value.endswith(" G") and float(braking.value.split()[0]) > 0
    corners = [m for m in h.moments if m.kind == "corner"]
    assert [m.distance_m for m in corners] == sorted(m.distance_m for m in corners)
    assert not any(m.warn for m in h.moments)
    assert 0 < h.stats.full_throttle_pct < 100
    assert h.stats.avg_speed_kmh > 0 and len(h.path_x) == len(h.path_z) > 10


def test_incidents_are_flagged() -> None:
    samples = _lap()
    for i in range(100, 140):
        samples[i] = replace(samples[i], tyres_out=4)
    for i in range(200, 215):
        samples[i] = replace(samples[i], brake=1.0, slip_ratio_fr=-0.5)
    for i in range(300, 320):
        samples[i] = replace(samples[i], throttle=1.0, slip_ratio_rr=0.5)

    warn = [m for m in lap_highlights(samples, TRACK).moments if m.warn]

    assert [m.kind for m in warn] == ["off_track", "lockup", "wheelspin"]
    assert warn[0].value == "4 ruedas"
    assert warn[1].value == "delantera derecha"


def test_too_short_lap() -> None:
    with pytest.raises(ValueError):
        lap_highlights(_lap()[:2], TRACK)
