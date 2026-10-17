"""Simulator-agnostic telemetry and session types."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TelemetrySample:
    """One normalized telemetry reading.

    Every adapter converts its simulator's native data into this shape, so the
    rest of the system never depends on a specific game.
    """

    t: float
    """Seconds since the recording started."""
    lap_number: int
    """Completed laps in the session (0 during the first lap)."""
    lap_time_ms: int
    """Elapsed time in the current lap."""
    normalized_position: float
    """Position along the track spline, 0.0 at the start line to 1.0."""
    speed_kmh: float
    throttle: float
    """0.0 to 1.0."""
    brake: float
    """0.0 to 1.0."""
    clutch: float
    """0.0 (released) to 1.0 (pressed)."""
    steering: float
    """-1.0 (full left) to 1.0 (full right)."""
    gear: int
    """-1 reverse, 0 neutral, 1+ forward gears."""
    rpm: float
    pos_x: float
    pos_y: float
    pos_z: float
    in_pit: bool


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """What was driven, as reported by the source when recording starts."""

    sim: str
    track: str
    car: str
    track_config: str = ""


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """A stored session."""

    id: int
    info: SessionInfo
    started_at: datetime
    ended_at: datetime | None
    sample_count: int
