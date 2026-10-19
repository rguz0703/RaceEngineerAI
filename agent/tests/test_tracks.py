from datetime import UTC, datetime

from raceengineer.analysis.tracks import summarize_tracks
from raceengineer.domain.models import Lap, SessionInfo, SessionRecord

RBR = SessionInfo("assetto_corsa", "ks_red_bull_ring", "ferrari", "layout_gp", 4300.0)
RBR_OTHER_CAR = SessionInfo("assetto_corsa", "ks_red_bull_ring", "porsche", "layout_gp", 4300.0)
IMOLA = SessionInfo("assetto_corsa", "imola", "laferrari", "", 4900.0)


def _record(sid: int, info: SessionInfo, day: int) -> SessionRecord:
    return SessionRecord(sid, info, datetime(2026, 10, day, tzinfo=UTC), None, 10)


def _lap(n: int, time_ms: int | None, off_track: bool = False) -> Lap:
    return Lap(n, n * 10, n * 10 + 10, time_ms, True, True, False, False, off_track)


def test_groups_by_track_and_picks_best_lap() -> None:
    calls: list[tuple[int, int]] = []

    def outline(session_id: int, lap: Lap) -> tuple[list[float], list[float]]:
        calls.append((session_id, lap.number))
        return [float(i) for i in range(400)], [float(-i) for i in range(400)]

    tracks = summarize_tracks(
        [
            (_record(1, RBR, 1), [_lap(1, 99_000), _lap(2, 98_000)]),
            (_record(2, RBR_OTHER_CAR, 2), [_lap(1, 97_000, off_track=True), _lap(2, None)]),
            (_record(3, IMOLA, 3), [_lap(1, 126_000, off_track=True)]),
        ],
        outline,
    )

    assert [t.track for t in tracks] == ["imola", "ks_red_bull_ring"]  # newest first
    imola, rbr = tracks
    assert rbr.cars == ["ferrari", "porsche"]
    assert rbr.session_ids == [2, 1]
    assert rbr.lap_count == 3
    # A clean lap beats a faster lap with an off-track moment.
    assert rbr.best is not None
    assert (rbr.best.time_ms, rbr.best.session_id, rbr.best.clean) == (98_000, 1, True)
    assert imola.best is not None and imola.best.clean is False
    assert len(rbr.outline_x) <= 200 and rbr.outline_z[1] < 0
    assert sorted(calls) == [(1, 2), (3, 1)]


def test_track_without_finished_laps_has_no_outline() -> None:
    def outline(session_id: int, lap: Lap) -> tuple[list[float], list[float]]:
        raise AssertionError("not called")

    [track] = summarize_tracks([(_record(1, RBR, 1), [_lap(1, None)])], outline)
    assert track.best is None and track.outline_x == []
