"""Sessions grouped by track (and layout), for choosing laps to compare."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from raceengineer.analysis.laps import default_reference
from raceengineer.domain.models import Lap, SessionRecord

TrackKey = tuple[str, str, str]
"""(sim, track, track_config)."""

OUTLINE_POINTS = 160


@dataclass(frozen=True, slots=True)
class TrackBest:
    time_ms: int
    session_id: int
    lap: int
    car: str
    clean: bool


@dataclass(frozen=True, slots=True)
class TrackSummary:
    sim: str
    track: str
    track_config: str
    length_m: float
    cars: list[str]
    session_ids: list[int]
    """Newest first."""
    lap_count: int
    best: TrackBest | None
    last_driven: datetime
    outline_x: list[float]
    outline_z: list[float]


def summarize_tracks(
    sessions: Sequence[tuple[SessionRecord, list[Lap]]],
    outline: Callable[[int, Lap], tuple[list[float], list[float]]],
) -> list[TrackSummary]:
    """One entry per track and layout, most recently driven first.

    ``outline(session_id, lap)`` returns the X/Z path of a lap; it is called once
    per track, for its best lap, to draw the map thumbnail.
    """
    groups: dict[TrackKey, list[tuple[SessionRecord, list[Lap]]]] = {}
    for record, laps in sessions:
        info = record.info
        groups.setdefault((info.sim, info.track, info.track_config), []).append((record, laps))

    summaries = []
    for (sim, track, config), members in groups.items():
        best: TrackBest | None = None
        for record, laps in members:
            lap, clean = default_reference(laps)
            if lap is None or lap.time_ms is None:
                continue
            better = best is None or (clean, -lap.time_ms) > (best.clean, -best.time_ms)
            if better:
                best = TrackBest(lap.time_ms, record.id, lap.number, record.info.car, clean)
        xs: list[float] = []
        zs: list[float] = []
        if best is not None:
            best_laps = next(laps for record, laps in members if record.id == best.session_id)
            lap = next(lap for lap in best_laps if lap.number == best.lap)
            xs, zs = outline(best.session_id, lap)
            step = max(1, len(xs) // OUTLINE_POINTS)
            xs, zs = [round(v, 1) for v in xs[::step]], [round(v, 1) for v in zs[::step]]
        newest_first = sorted(members, key=lambda m: (m[0].started_at, m[0].id), reverse=True)
        summaries.append(
            TrackSummary(
                sim=sim,
                track=track,
                track_config=config,
                length_m=max(r.info.track_length_m for r, _ in members),
                cars=sorted({r.info.car for r, _ in members}),
                session_ids=[r.id for r, _ in newest_first],
                lap_count=sum(lap.time_ms is not None for _, laps in members for lap in laps),
                best=best,
                last_driven=newest_first[0][0].started_at,
                outline_x=xs,
                outline_z=zs,
            )
        )
    return sorted(summaries, key=lambda s: s.last_driven, reverse=True)
