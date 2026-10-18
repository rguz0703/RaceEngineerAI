"""Simulator-agnostic telemetry and session types."""

from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple


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
    last_lap_ms: int = 0
    """The game's official time for the last completed lap; 0 if none yet or unknown."""
    tyres_out: int = 0
    """Wheels outside the track limits right now (0 to 4)."""

    # Car state. Wheels are front-left, front-right, rear-left, rear-right.
    yaw_rate: float = 0.0
    """Rotation around the vertical axis, rad/s (sign depends on the game)."""
    tyre_pressure_fl: float = 0.0
    tyre_pressure_fr: float = 0.0
    tyre_pressure_rl: float = 0.0
    tyre_pressure_rr: float = 0.0
    """Tyre pressures, psi."""
    tyre_temp_inner_fl: float = 0.0
    tyre_temp_inner_fr: float = 0.0
    tyre_temp_inner_rl: float = 0.0
    tyre_temp_inner_rr: float = 0.0
    tyre_temp_middle_fl: float = 0.0
    tyre_temp_middle_fr: float = 0.0
    tyre_temp_middle_rl: float = 0.0
    tyre_temp_middle_rr: float = 0.0
    tyre_temp_outer_fl: float = 0.0
    tyre_temp_outer_fr: float = 0.0
    tyre_temp_outer_rl: float = 0.0
    tyre_temp_outer_rr: float = 0.0
    """Tyre surface temperatures across the tread, °C."""
    slip_ratio_fl: float = 0.0
    slip_ratio_fr: float = 0.0
    slip_ratio_rl: float = 0.0
    slip_ratio_rr: float = 0.0
    """Wheel speed vs car speed: -1 fully locked, 0 rolling, + spinning."""
    brake_bias: float = 0.0
    """Share of braking on the front axle, 0 to 1."""
    tc: float = 0.0
    abs: float = 0.0
    engine_brake: int = 0
    fuel: float = 0.0
    """Litres."""


class LapSignals(NamedTuple):
    """The few channels lap detection needs, so long sessions load quickly."""

    t: float
    lap_number: int
    lap_time_ms: int
    last_lap_ms: int
    in_pit: bool
    tyres_out: int


@dataclass(frozen=True, slots=True)
class Lap:
    """One lap found in a recording, as samples[start:end]."""

    number: int
    """1-based, as the game counts them (the first lap of the session is 1)."""
    start: int
    end: int
    """Index after the last sample (exclusive)."""
    time_ms: int | None
    """Lap time, or None if the line was never crossed at the end."""
    official: bool
    """True if time_ms is the game's own figure; False if estimated from samples."""
    complete: bool
    """Recorded from line to line, so every sample of the lap is present."""
    out_lap: bool
    """Started in the pit lane."""
    in_lap: bool
    """Ended in the pit lane."""
    off_track: bool
    """At some point more than two wheels were outside the track limits."""


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """What was driven, as reported by the source when recording starts."""

    sim: str
    track: str
    car: str
    track_config: str = ""
    track_length_m: float = 0.0
    """Length of the racing line; 0 if the source does not know it."""
    tyre_compound: str = ""


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """A stored session."""

    id: int
    info: SessionInfo
    started_at: datetime
    ended_at: datetime | None
    sample_count: int
