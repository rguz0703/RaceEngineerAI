"""JSON shapes returned by the API (mirrored in web/src/api.ts)."""

from datetime import datetime

from pydantic import BaseModel


class SessionOut(BaseModel):
    id: int
    sim: str
    track: str
    track_config: str
    car: str
    track_length_m: float
    started_at: datetime
    ended_at: datetime | None
    sample_count: int


class LapOut(BaseModel):
    number: int
    time_ms: int | None
    official: bool
    complete: bool
    out_lap: bool
    in_lap: bool
    off_track: bool


class SessionLapsOut(BaseModel):
    session: SessionOut
    laps: list[LapOut]
    best_clean_lap: int | None


class ChannelsOut(BaseModel):
    speed_kmh: list[float]
    throttle: list[float]
    brake: list[float]
    gear: list[int]


class LapRef(BaseModel):
    session_id: int
    lap: int
    time_ms: int | None


class SegmentOut(BaseModel):
    start_m: float
    end_m: float
    delta_s: float
    target_min_speed_kmh: float
    reference_min_speed_kmh: float
    target_avg_speed_kmh: float
    reference_avg_speed_kmh: float


class ComparisonOut(BaseModel):
    target: LapRef
    reference: LapRef
    partial: bool
    """One of the laps was not recorded from the line, so only part of the track is compared."""
    distance_m: list[float]
    delta_s: list[float]
    target_channels: ChannelsOut
    reference_channels: ChannelsOut
    segments: list[SegmentOut]
