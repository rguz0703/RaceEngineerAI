"""Live view while recording: distance on track and delta against a reference lap.

Everything here runs on every sample (~100 Hz) in the recording thread, so it
only does constant-time work plus a binary search.
"""

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

from raceengineer.analysis.car import WHEEL_NAMES, WHEELS
from raceengineer.analysis.compare import LapTrace, compare_laps, lap_trace
from raceengineer.analysis.diagnosis import LOCK_RATIO, MIN_EVENT_S, SPIN_RATIO
from raceengineer.analysis.lap_index import load_lap, session_laps
from raceengineer.analysis.laps import (
    MIN_LAP_MS,
    OFF_TRACK_TYRES,
    START_TOLERANCE_MS,
    default_reference,
)
from raceengineer.capture.engineer import (
    RadioCall,
    biggest_loss,
    incident_speech,
    lap_call,
    sector_call,
    tip_call,
)
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
    trace: LapTrace | None = None
    """The full trace, used by the engineer to explain where time went."""

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
            trace=trace,
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
class LiveEvent:
    """Something worth flagging the moment it happens."""

    id: int
    """Increasing, so clients can tell new events from ones already shown."""
    kind: str
    """off_track, lockup, wheelspin or best_lap."""
    level: str
    """"warn" (yellow) or "good" (green)."""
    text: str
    lap: int
    distance_m: float


MAX_EVENTS = 20
SECTORS = 3
WHOLE_LAP = 0.9
"""Share of a lap's time that must have been recorded to judge it."""
INCIDENT_GAP_S = 3.0
"""The engineer leaves at least this long between incident calls."""
REARM_S = 0.5
"""A condition must be absent this long before the same kind can fire again."""


@dataclass(frozen=True, slots=True)
class LiveSector:
    """One finished sector of the current lap."""

    number: int
    """1 to 3."""
    time_ms: int
    delta_s: float | None
    """Against the same sector of the reference lap; None without one."""
    best: bool
    """The fastest this sector has been driven in this session (on track) and no slower
    than the reference's."""


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
    events: list[LiveEvent]
    """Most recent last, at most MAX_EVENTS."""
    radio: list[RadioCall]
    """What the engineer said, most recent last, at most MAX_EVENTS."""
    sectors: list[LiveSector]
    """Sectors finished so far in this lap (only for laps started at the line)."""
    last_sectors: list[LiveSector]
    """All three sectors of the previous lap, when it was timed."""


class _Episode:
    """Fires once when a condition has held for ``min_s``; re-arms after it clears."""

    def __init__(self, min_s: float) -> None:
        self._min_s = min_s
        self._since: float | None = None
        self._cleared_at: float | None = None
        self._fired = False

    def update(self, active: bool, t: float) -> bool:
        if active:
            self._cleared_at = None
            if self._since is None:
                self._since = t
            if not self._fired and t - self._since >= self._min_s:
                self._fired = True
                return True
            return False
        self._since = None
        if self._fired:
            self._cleared_at = self._cleared_at if self._cleared_at is not None else t
            if t - self._cleared_at >= REARM_S:
                self._fired = False
        return False


class LiveTracker:
    """Follows the current lap and swaps in this session's laps when they beat the reference."""

    def __init__(self, track_length_m: float, reference: ReferenceLap | None = None) -> None:
        self._length = track_length_m
        self.reference = reference
        self._lap_samples: list[TelemetrySample] = []
        self._best_ms = 0
        self._frame: LiveFrame | None = None
        self._events: list[LiveEvent] = []
        self._next_event = 1
        self._off_track = _Episode(0.0)
        self._lockups = {w: _Episode(MIN_EVENT_S) for w in WHEELS}
        self._spin = _Episode(1.5 * MIN_EVENT_S)
        self._radio: list[RadioCall] = []
        self._next_radio = 1
        self._now = 0.0
        self._last_incident: float | None = None
        self._sector = 0
        self._sector_start: float | None = None
        self._sector_start_ms = 0
        self._timed = False
        self._lap_sectors: list[LiveSector] = []
        self._last_sectors: list[LiveSector] = []
        self._best_sectors: list[int] = [0] * SECTORS

    @property
    def frame(self) -> LiveFrame | None:
        return self._frame

    def update(self, sample: TelemetrySample) -> LiveFrame:
        self._now = sample.t
        previous = self._lap_samples[-1] if self._lap_samples else None
        if previous is not None and sample.lap_number != previous.lap_number:
            self._finish_lap(sample)
        starting = not self._lap_samples
        self._lap_samples.append(sample)

        distance = self._distance(sample)
        self._detect(sample, distance or 0.0)
        delta = None
        if self.reference is not None and distance is not None and not sample.in_pit:
            delta = sample.lap_time_ms / 1000 - self.reference.time_at(distance)
        if starting:
            self._start_sectors(sample, distance, delta)
        elif distance is not None:
            self._sectors(sample, distance, delta)
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
            events=list(self._events),
            radio=list(self._radio),
            sectors=list(self._lap_sectors),
            last_sectors=list(self._last_sectors),
        )
        return self._frame

    def _start_sectors(
        self, sample: TelemetrySample, distance: float | None, delta: float | None
    ) -> None:
        """Sectors are timed only for laps started at the line."""
        self._timed = sample.lap_time_ms <= START_TOLERANCE_MS and not sample.in_pit
        self._sector_start = delta if self._timed else None
        self._sector_start_ms = 0
        self._lap_sectors = []
        self._sector = 0
        if not self._timed and distance is not None and self._length > 0:
            # Skip the sectors already behind us.
            self._sector = min(SECTORS, int(distance / self._length * SECTORS) + 1)

    def _sectors(self, sample: TelemetrySample, distance: float, delta: float | None) -> None:
        while (
            self._sector < SECTORS - 1 and distance >= self._length * (self._sector + 1) / SECTORS
        ):
            if self._timed:
                gap = (
                    delta - self._sector_start
                    if delta is not None and self._sector_start is not None
                    else None
                )
                self._close_sector(
                    sample.lap_time_ms - self._sector_start_ms, gap, self._lap_samples
                )
                if gap is not None:
                    self._say(
                        sector_call(self._next_radio, sample.lap_number + 1, self._sector, gap)
                    )
            self._sector_start = delta
            self._sector_start_ms = sample.lap_time_ms
            self._sector += 1

    def _close_sector(
        self, time_ms: int, gap: float | None, lap_samples: list[TelemetrySample]
    ) -> None:
        """Record the sector just finished; it counts for the best only while on track."""
        k = len(self._lap_sectors)
        on_track = not any(s.tyres_out >= OFF_TRACK_TYRES or s.in_pit for s in lap_samples)
        if on_track and (self._best_sectors[k] == 0 or time_ms < self._best_sectors[k]):
            self._best_sectors[k] = time_ms
        # Purple only when it is also no slower than the lap you are racing.
        best = on_track and time_ms == self._best_sectors[k] and (gap is None or gap <= 0)
        self._lap_sectors.append(LiveSector(k + 1, time_ms, gap, best))

    def _finish_sectors(
        self, samples: list[TelemetrySample], time_ms: int, reference: ReferenceLap | None
    ) -> None:
        """Time the last sector at the line; the lap's sectors stay visible as the last lap's."""
        self._last_sectors = []
        if not self._timed or len(self._lap_sectors) != SECTORS - 1:
            return
        gap = None
        if reference is not None and self._sector_start is not None:
            gap = (time_ms - reference.time_ms) / 1000 - self._sector_start
        self._close_sector(time_ms - self._sector_start_ms, gap, samples)
        self._last_sectors = list(self._lap_sectors)

    def _say(self, call: RadioCall) -> None:
        self._radio.append(call)
        self._next_radio = call.id + 1
        del self._radio[:-MAX_EVENTS]

    def _detect(self, sample: TelemetrySample, distance: float) -> None:
        lap = sample.lap_number + 1
        if self._off_track.update(sample.tyres_out >= OFF_TRACK_TYRES, sample.t):
            self._add(
                "off_track",
                "warn",
                f"Fuera de pista ({sample.tyres_out} ruedas)",
                lap,
                distance,
                incident_speech("off_track"),
            )
        for wheel, episode in self._lockups.items():
            slip = float(getattr(sample, f"slip_ratio_{wheel}"))
            if episode.update(sample.brake > 0.2 and slip < LOCK_RATIO, sample.t):
                self._add(
                    "lockup",
                    "warn",
                    f"Bloqueo: {WHEEL_NAMES[wheel]}",
                    lap,
                    distance,
                    incident_speech("lockup", wheel),
                )
        spinning = sample.throttle > 0.5 and any(
            float(getattr(sample, f"slip_ratio_{w}")) > SPIN_RATIO for w in WHEELS
        )
        if self._spin.update(spinning, sample.t):
            self._add(
                "wheelspin",
                "warn",
                "Patinaste al acelerar",
                lap,
                distance,
                incident_speech("wheelspin"),
            )

    def _add(
        self, kind: str, level: str, text: str, lap: int, distance: float, speech: str = ""
    ) -> None:
        self._events.append(LiveEvent(self._next_event, kind, level, text, lap, round(distance)))
        self._next_event += 1
        del self._events[:-MAX_EVENTS]
        quiet = self._last_incident is not None and self._now - self._last_incident < INCIDENT_GAP_S
        if speech and not quiet:
            self._last_incident = self._now
            self._say(RadioCall(self._next_radio, "incident", text, speech, lap))

    def _distance(self, sample: TelemetrySample) -> float | None:
        if self._length <= 0:
            return None
        position = sample.normalized_position
        # Just after the line the spline can still read ~1.0.
        if position > 0.5 and sample.lap_time_ms <= START_TOLERANCE_MS:
            position -= 1.0
        return min(1.0, max(0.0, position)) * self._length

    def _finish_lap(self, first_of_next: TelemetrySample) -> None:
        samples = _until_reset(self._lap_samples)
        self._lap_samples = []
        time_ms = first_of_next.last_lap_ms
        if time_ms < MIN_LAP_MS:
            return
        number = samples[0].lap_number + 1
        # Recording can start mid-lap or just before the line: judge only what was seen.
        seen = (samples[-1].t - samples[0].t) / (time_ms / 1000)
        if seen < 0.5:
            return
        reference = self.reference
        # "New best" only when it beats this session's laps and the reference you race.
        to_beat = [ms for ms in (self._best_ms, reference.time_ms if reference else 0) if ms]
        new_best = bool(to_beat) and time_ms < min(to_beat)
        if self._best_ms == 0 or time_ms < self._best_ms:
            self._best_ms = time_ms
        if new_best:
            gain = (min(to_beat) - time_ms) / 1000
            self._add(
                "best_lap",
                "good",
                f"¡Nueva mejor vuelta! {_lap_text(time_ms)} ({gain:.3f} s más rápida)",
                number,
                0.0,
            )
        started_at_line = samples[0].lap_time_ms <= START_TOLERANCE_MS and seen >= WHOLE_LAP
        off_track = any(s.tyres_out >= OFF_TRACK_TYRES for s in samples)
        clean = started_at_line and not off_track and not any(s.in_pit for s in samples)
        if started_at_line:
            self._finish_sectors(samples, time_ms, reference)
        else:
            self._last_sectors = []
        self._say(
            lap_call(
                self._next_radio,
                number,
                time_ms,
                reference.time_ms if reference else None,
                new_best,
                off_track,
            )
        )
        lap = Lap(number, 0, len(samples), time_ms, True, True, False, False, False)
        if clean and self._length > 0 and reference is not None and reference.trace:
            try:
                comparison = compare_laps(lap_trace(samples, lap, self._length), reference.trace)
            except ValueError:
                comparison = None
            tip = biggest_loss(comparison) if comparison is not None else None
            if tip is not None:
                self._say(tip_call(self._next_radio, number, tip))
        beats = reference is None or time_ms < reference.time_ms
        if clean and beats and self._length > 0:
            self.reference = ReferenceLap.from_lap(
                samples, lap, self._length, f"esta sesión, vuelta {lap.number}"
            )


def _until_reset(samples: list[TelemetrySample]) -> list[TelemetrySample]:
    """Drop trailing reads where the game already reset the timer but not the lap counter."""
    for i in range(1, len(samples)):
        if samples[i].lap_time_ms + START_TOLERANCE_MS < samples[i - 1].lap_time_ms:
            return samples[:i]
    return samples


def _lap_text(ms: int) -> str:
    minutes, rest = divmod(ms, 60_000)
    return f"{minutes}:{rest / 1000:06.3f}"


def best_reference(repository: SessionRepository, info: SessionInfo) -> ReferenceLap | None:
    """Fastest lap recorded before with the same sim, track, layout and car.

    Clean laps first; if there are none, the fastest finished lap (its label says so).
    """
    best: tuple[int, Lap, bool] | None = None
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
        lap, clean = default_reference(session_laps(repository, record.id))
        if lap is None or lap.time_ms is None:
            continue
        if best is None or (clean, -lap.time_ms) > (best[2], -(best[1].time_ms or 0)):
            best = (record.id, lap, clean)
    if best is None:
        return None
    session_id, lap, clean = best
    samples, local = load_lap(repository, session_id, lap)
    label = f"sesión {session_id}, vuelta {lap.number}" + (
        "" if clean else " (con salida de pista)"
    )
    return ReferenceLap.from_lap(samples, local, info.track_length_m, label)
