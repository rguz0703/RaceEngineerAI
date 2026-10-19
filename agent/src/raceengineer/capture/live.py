"""Live view while recording: distance on track and delta against a reference lap.

Everything here runs on every sample (~100 Hz) in the recording thread, so it
only does constant-time work plus a binary search.
"""

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

from raceengineer.analysis.compare import lap_trace
from raceengineer.analysis.lap_index import load_lap, session_laps
from raceengineer.analysis.laps import OFF_TRACK_TYRES, START_TOLERANCE_MS, best_clean_lap
from raceengineer.domain.models import Lap, SessionInfo, TelemetrySample
from raceengineer.domain.ports import SessionRepository

MAP_POINTS = 400
"""Points kept for the live track outline."""


@dataclass(frozen=True, slots=True)
class ReferenceLap:
    """A finished lap to race against: lap time as a function of distance."""

    time_ms: int
    distance_m: list[float]
    time_s: list[float]
    pos_x: list[float]
    pos_z: list[float]
    label: str
    """Where it comes from, e.g. "sesión 3, vuelta 5" or "esta sesión, vuelta 4"."""

    @classmethod
    def from_lap(
        cls, samples: Sequence[TelemetrySample], lap: Lap, track_length_m: float, label: str
    ) -> "ReferenceLap":
        trace = lap_trace(samples, lap, track_length_m)
        assert lap.time_ms is not None
        return cls(
            time_ms=lap.time_ms,
            distance_m=trace.distance_m,
            time_s=trace.time_s,
            pos_x=trace.pos_x,
            pos_z=trace.pos_z,
            label=label,
        )

    def time_at(self, distance_m: float) -> float:
        d = self.distance_m
        hi = min(len(d) - 1, max(1, bisect_right(d, distance_m)))
        lo = hi - 1
        span = d[hi] - d[lo]
        f = (distance_m - d[lo]) / span if span > 0 else 1.0
        f = min(1.0, max(0.0, f))
        return self.time_s[lo] + (self.time_s[hi] - self.time_s[lo]) * f

    def outline(self) -> tuple[list[float], list[float]]:
        """A light copy of the path for drawing the map."""
        step = max(1, len(self.pos_x) // MAP_POINTS)
        return self.pos_x[::step], self.pos_z[::step]


@dataclass(frozen=True, slots=True)
class LiveFrame:
    lap: int
    lap_time_ms: int
    last_lap_ms: int
    best_lap_ms: int
    distance_m: float
    delta_s: float | None
    """Ahead (-) or behind (+) the reference at this point; None without one."""
    speed_kmh: float
    throttle: float
    brake: float
    gear: int
    rpm: float
    steering: float
    pos_x: float
    pos_z: float
    in_pit: bool
    reference_ms: int | None
    reference_label: str


class LiveTracker:
    """Follows the current lap and swaps in this session's laps when they beat the reference."""

    def __init__(self, track_length_m: float, reference: ReferenceLap | None = None) -> None:
        self._length = track_length_m
        self.reference = reference
        self._lap_samples: list[TelemetrySample] = []
        self._best_ms = 0
        self._frame: LiveFrame | None = None

    @property
    def frame(self) -> LiveFrame | None:
        return self._frame

    def update(self, sample: TelemetrySample) -> LiveFrame:
        previous = self._lap_samples[-1] if self._lap_samples else None
        if previous is not None and sample.lap_number != previous.lap_number:
            self._finish_lap(sample)
        self._lap_samples.append(sample)

        distance = self._distance(sample)
        delta = None
        if self.reference is not None and distance is not None and not sample.in_pit:
            delta = sample.lap_time_ms / 1000 - self.reference.time_at(distance)
        self._frame = LiveFrame(
            lap=sample.lap_number + 1,
            lap_time_ms=sample.lap_time_ms,
            last_lap_ms=sample.last_lap_ms,
            best_lap_ms=self._best_ms,
            distance_m=distance or 0.0,
            delta_s=delta,
            speed_kmh=sample.speed_kmh,
            throttle=sample.throttle,
            brake=sample.brake,
            gear=sample.gear,
            rpm=sample.rpm,
            steering=sample.steering,
            pos_x=sample.pos_x,
            pos_z=sample.pos_z,
            in_pit=sample.in_pit,
            reference_ms=self.reference.time_ms if self.reference else None,
            reference_label=self.reference.label if self.reference else "",
        )
        return self._frame

    def _distance(self, sample: TelemetrySample) -> float | None:
        if self._length <= 0:
            return None
        position = sample.normalized_position
        # Just after the line the spline can still read ~1.0.
        if position > 0.5 and sample.lap_time_ms <= START_TOLERANCE_MS:
            position -= 1.0
        return min(1.0, max(0.0, position)) * self._length

    def _finish_lap(self, first_of_next: TelemetrySample) -> None:
        samples = self._lap_samples
        self._lap_samples = []
        time_ms = first_of_next.last_lap_ms
        if time_ms <= 0:
            return
        if self._best_ms == 0 or time_ms < self._best_ms:
            self._best_ms = time_ms
        clean = (
            samples[0].lap_time_ms <= START_TOLERANCE_MS
            and not any(s.in_pit for s in samples)
            and not any(s.tyres_out >= OFF_TRACK_TYRES for s in samples)
        )
        beats = self.reference is None or time_ms < self.reference.time_ms
        if clean and beats and self._length > 0:
            lap = Lap(
                samples[0].lap_number + 1, 0, len(samples), time_ms, True, True, False, False, False
            )
            self.reference = ReferenceLap.from_lap(
                samples, lap, self._length, f"esta sesión, vuelta {lap.number}"
            )


def best_reference(repository: SessionRepository, info: SessionInfo) -> ReferenceLap | None:
    """Fastest clean lap recorded before with the same sim, track, layout and car."""
    best: tuple[int, Lap] | None = None
    for record in repository.list_sessions():
        other = record.info
        same = (other.sim, other.track, other.track_config, other.car) == (
            info.sim,
            info.track,
            info.track_config,
            info.car,
        )
        if not same:
            continue
        lap = best_clean_lap(session_laps(repository, record.id))
        if lap is None or lap.time_ms is None:
            continue
        if best is None or lap.time_ms < (best[1].time_ms or 0):
            best = (record.id, lap)
    if best is None:
        return None
    session_id, lap = best
    samples, local = load_lap(repository, session_id, lap)
    return ReferenceLap.from_lap(
        samples, local, info.track_length_m, f"sesión {session_id}, vuelta {lap.number}"
    )
