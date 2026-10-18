from datetime import UTC, datetime

from raceengineer.analysis.overview import overview
from raceengineer.domain.models import Lap, SessionInfo, SessionRecord

MONZA = SessionInfo("assetto_corsa", "monza", "porsche", track_length_m=5000.0)
SPA = SessionInfo("assetto_corsa", "spa", "porsche", track_length_m=7000.0)


def _record(session_id: int, info: SessionInfo, day: int) -> SessionRecord:
    return SessionRecord(session_id, info, datetime(2026, 10, day, tzinfo=UTC), None, 100)


def _lap(number: int, time_ms: int | None, clean: bool = True) -> Lap:
    return Lap(number, 0, 1, time_ms, True, True, False, False, not clean)


def test_overview_bests_progress_and_totals() -> None:
    sessions = [
        (_record(1, MONZA, 1), [_lap(1, 130_000), _lap(2, 128_000), _lap(3, None)]),
        (_record(2, SPA, 2), [_lap(1, 140_000, clean=False)]),
        (_record(3, MONZA, 3), [_lap(1, 126_500), _lap(2, 120_000, clean=False)]),
    ]

    o = overview(sessions)

    assert (o.totals.sessions, o.totals.laps) == (3, 5)
    assert o.totals.distance_km == 5 * 4 + 7  # 4 Monza laps + 1 Spa lap
    # Spa has no clean lap, so only Monza appears; off-track 2:00.000 is not a best.
    [best] = o.best_laps
    assert (best.track, best.time_ms, best.session_id, best.lap) == ("monza", 126_500, 3, 1)
    [progress] = o.progress
    assert [p.best_ms for p in progress.points] == [128_000, 126_500]


def test_overview_orders_combos_by_last_driven() -> None:
    sessions = [
        (_record(1, MONZA, 1), [_lap(1, 130_000)]),
        (_record(2, SPA, 5), [_lap(1, 150_000)]),
    ]
    assert [b.track for b in overview(sessions).best_laps] == ["spa", "monza"]


def test_empty_overview() -> None:
    o = overview([])
    assert (o.totals.sessions, o.best_laps, o.progress) == (0, [], [])
