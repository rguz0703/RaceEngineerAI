"""Summary across sessions for the dashboard's home page: bests, progress, totals."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from raceengineer.analysis.laps import best_clean_lap
from raceengineer.domain.models import Lap, SessionRecord

Combo = tuple[str, str, str, str]
"""(sim, track, track_config, car): lap times only compare within one."""


@dataclass(frozen=True, slots=True)
class BestLap:
    sim: str
    track: str
    track_config: str
    car: str
    time_ms: int
    session_id: int
    lap: int
    driven_at: datetime


@dataclass(frozen=True, slots=True)
class ProgressPoint:
    session_id: int
    driven_at: datetime
    best_ms: int


@dataclass(frozen=True, slots=True)
class Progress:
    sim: str
    track: str
    track_config: str
    car: str
    points: list[ProgressPoint]
    """Best clean lap of each session, oldest first."""


@dataclass(frozen=True, slots=True)
class Totals:
    sessions: int
    laps: int
    """Finished laps."""
    distance_km: float
    """Finished laps times the track length (sessions with a known length)."""


@dataclass(frozen=True, slots=True)
class Overview:
    totals: Totals
    best_laps: list[BestLap]
    """One per combo, most recently driven combo first."""
    progress: list[Progress]


def overview(sessions: Sequence[tuple[SessionRecord, list[Lap]]]) -> Overview:
    laps_total = 0
    distance_m = 0.0
    points: dict[Combo, list[ProgressPoint]] = {}
    best: dict[Combo, BestLap] = {}
    last_driven: dict[Combo, datetime] = {}
    for record, laps in sessions:
        info = record.info
        combo = (info.sim, info.track, info.track_config, info.car)
        finished = [lap for lap in laps if lap.time_ms is not None]
        laps_total += len(finished)
        distance_m += len(finished) * info.track_length_m
        last_driven[combo] = max(last_driven.get(combo, record.started_at), record.started_at)
        session_best = best_clean_lap(laps)
        if session_best is None or session_best.time_ms is None:
            continue
        points.setdefault(combo, []).append(
            ProgressPoint(record.id, record.started_at, session_best.time_ms)
        )
        current = best.get(combo)
        if current is None or session_best.time_ms < current.time_ms:
            best[combo] = BestLap(
                *combo,
                time_ms=session_best.time_ms,
                session_id=record.id,
                lap=session_best.number,
                driven_at=record.started_at,
            )
    order = sorted(best, key=lambda c: last_driven[c], reverse=True)
    return Overview(
        totals=Totals(len(sessions), laps_total, round(distance_m / 1000, 1)),
        best_laps=[best[c] for c in order],
        progress=[Progress(*c, points=sorted(points[c], key=lambda p: p.driven_at)) for c in order],
    )
