"""Lap index: laps are found once per session and stored, so long sessions open fast."""

from dataclasses import replace

from raceengineer.analysis.laps import segment_laps
from raceengineer.analysis.sectors import with_sectors
from raceengineer.domain.models import Lap, TelemetrySample
from raceengineer.domain.ports import SessionRepository


def session_laps(repository: SessionRepository, session_id: int) -> list[Lap]:
    """The session's laps, from the index or by scanning the lap signals once."""
    laps = repository.load_laps(session_id)
    if laps is None:
        signals = repository.load_lap_signals(session_id)
        laps = with_sectors(segment_laps(signals), signals)
        repository.save_laps(session_id, laps)
    return laps


def load_lap(
    repository: SessionRepository, session_id: int, lap: Lap
) -> tuple[list[TelemetrySample], Lap]:
    """Only this lap's samples, with the lap re-indexed to them (start 0)."""
    samples = repository.load_samples(session_id, lap.start, lap.end)
    return samples, replace(lap, start=0, end=len(samples))
