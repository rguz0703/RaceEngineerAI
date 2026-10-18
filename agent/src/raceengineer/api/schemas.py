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


class TyreOut(BaseModel):
    wheel: str
    pressure_psi: float
    temp_inner_c: float
    temp_middle_c: float
    temp_outer_c: float


class CarOut(BaseModel):
    tyre_compound: str
    tyres: list[TyreOut]
    brake_bias: float
    tc: float
    abs: float
    engine_brake: int
    fuel_start_l: float
    fuel_end_l: float


class NoteOut(BaseModel):
    segment: int | None
    topic: str
    severity: str
    text: str


class SegmentOut(BaseModel):
    start_index: int
    end_index: int
    """Grid indexes covered by the segment (inclusive), to color the track map."""
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
    track_x: list[float]
    track_z: list[float]
    """The reference lap's path on the distance grid, to draw the track map."""
    segments: list[SegmentOut]
    target_car: CarOut | None
    reference_car: CarOut | None
    """None for laps recorded before the car state was stored."""
    notes: list[NoteOut]


class GameOut(BaseModel):
    state: str
    """unavailable, closed, off (menu), live, pause, replay."""
    track: str
    car: str
    message: str


class RecordingOut(BaseModel):
    available: bool
    """False when the server was started without recording support."""
    state: str
    session_id: int | None
    started_at: datetime | None
    sample_count: int
    lap: int
    lap_time_ms: int
    last_lap_ms: int
    best_lap_ms: int
    speed_kmh: float
    in_pit: bool
    message: str
    last_session_id: int | None
    game: GameOut
