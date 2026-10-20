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
    lap_count: int
    """Finished laps."""
    best_lap_ms: int | None
    """Best clean lap (complete, on track, no pits)."""


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
    reference_clean: bool
    """False when the session had no clean lap and the fastest finished one was used."""
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


class BestLapOut(BaseModel):
    sim: str
    track: str
    track_config: str
    car: str
    time_ms: int
    session_id: int
    lap: int
    driven_at: datetime


class ProgressPointOut(BaseModel):
    session_id: int
    driven_at: datetime
    best_ms: int


class ProgressOut(BaseModel):
    sim: str
    track: str
    track_config: str
    car: str
    points: list[ProgressPointOut]


class TotalsOut(BaseModel):
    sessions: int
    laps: int
    distance_km: float


class OverviewOut(BaseModel):
    totals: TotalsOut
    best_laps: list[BestLapOut]
    progress: list[ProgressOut]
    recent: list[SessionOut]


class TrackBestOut(BaseModel):
    time_ms: int
    session_id: int
    lap: int
    car: str
    clean: bool


class TrackOut(BaseModel):
    sim: str
    track: str
    track_config: str
    length_m: float
    cars: list[str]
    session_ids: list[int]
    lap_count: int
    best: TrackBestOut | None
    last_driven: datetime
    outline_x: list[float]
    outline_z: list[float]


class MomentOut(BaseModel):
    kind: str
    title: str
    value: str
    detail: str
    distance_m: float
    pos_x: float
    pos_z: float
    warn: bool


class LapStatsOut(BaseModel):
    full_throttle_pct: float
    braking_pct: float
    coasting_pct: float
    avg_speed_kmh: float
    max_rpm: float
    gear_changes: int


class ReferenceGapOut(BaseModel):
    reference: LapRef
    clean: bool
    total_s: float
    """Positive: this lap is slower than the reference."""
    best_segment: SegmentOut
    worst_segment: SegmentOut


class LapHighlightsOut(BaseModel):
    session: SessionOut
    lap: LapOut
    moments: list[MomentOut]
    stats: LapStatsOut
    path_x: list[float]
    path_z: list[float]
    vs_best: ReferenceGapOut | None
    """Against your best lap on this track (another lap), when there is one."""
