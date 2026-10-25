// Mirrors agent/src/raceengineer/api/schemas.py.

export interface Session {
  id: number;
  sim: string;
  track: string;
  track_config: string;
  car: string;
  track_length_m: number;
  started_at: string;
  ended_at: string | null;
  sample_count: number;
  lap_count: number;
  best_lap_ms: number | null;
}

export interface Lap {
  number: number;
  time_ms: number | null;
  official: boolean;
  complete: boolean;
  out_lap: boolean;
  in_lap: boolean;
  off_track: boolean;
  /** Time in each third of the track; empty when the lap was not recorded whole. */
  sector_ms: number[];
}

export interface SessionLaps {
  session: Session;
  laps: Lap[];
  best_clean_lap: number | null;
  /** Fastest time in each sector among clean laps. */
  best_sectors_ms: number[];
  /** The best sectors put together. */
  ideal_lap_ms: number | null;
}

export interface Channels {
  speed_kmh: number[];
  throttle: number[];
  brake: number[];
  gear: number[];
}

export interface LapRef {
  session_id: number;
  lap: number;
  time_ms: number | null;
}

export interface Segment {
  start_index: number;
  end_index: number;
  start_m: number;
  end_m: number;
  delta_s: number;
  target_min_speed_kmh: number;
  reference_min_speed_kmh: number;
  target_avg_speed_kmh: number;
  reference_avg_speed_kmh: number;
}

export interface Tyre {
  wheel: "fl" | "fr" | "rl" | "rr";
  pressure_psi: number;
  temp_inner_c: number;
  temp_middle_c: number;
  temp_outer_c: number;
}

export interface Car {
  tyre_compound: string;
  tyres: Tyre[];
  brake_bias: number;
  tc: number;
  abs: number;
  engine_brake: number;
  fuel_start_l: number;
  fuel_end_l: number;
}

export interface Note {
  segment: number | null;
  topic: string;
  severity: "warn" | "info";
  text: string;
}

export interface Comparison {
  target: LapRef;
  reference: LapRef;
  partial: boolean;
  reference_clean: boolean;
  distance_m: number[];
  delta_s: number[];
  target_channels: Channels;
  reference_channels: Channels;
  track_x: number[];
  track_z: number[];
  segments: Segment[];
  target_car: Car | null;
  reference_car: Car | null;
  notes: Note[];
}

export interface BestLap {
  sim: string;
  track: string;
  track_config: string;
  car: string;
  time_ms: number;
  session_id: number;
  lap: number;
  driven_at: string;
}

export interface Progress {
  sim: string;
  track: string;
  track_config: string;
  car: string;
  points: { session_id: number; driven_at: string; best_ms: number }[];
}

export interface Overview {
  totals: { sessions: number; laps: number; distance_km: number };
  best_laps: BestLap[];
  progress: Progress[];
  recent: Session[];
}

export interface Track {
  sim: string;
  track: string;
  track_config: string;
  length_m: number;
  cars: string[];
  session_ids: number[];
  lap_count: number;
  best: { time_ms: number; session_id: number; lap: number; car: string; clean: boolean } | null;
  last_driven: string;
  outline_x: number[];
  outline_z: number[];
}

export interface Moment {
  kind: "top_speed" | "braking" | "corner" | "off_track" | "lockup" | "wheelspin" | string;
  title: string;
  value: string;
  detail: string;
  distance_m: number;
  pos_x: number;
  pos_z: number;
  warn: boolean;
}

export interface LapHighlights {
  session: Session;
  lap: Lap;
  moments: Moment[];
  stats: {
    full_throttle_pct: number;
    braking_pct: number;
    coasting_pct: number;
    avg_speed_kmh: number;
    max_rpm: number;
    gear_changes: number;
  };
  path_x: number[];
  path_z: number[];
  vs_best: {
    reference: LapRef;
    clean: boolean;
    total_s: number;
    best_segment: Segment;
    worst_segment: Segment;
  } | null;
}

export interface Game {
  state: "unavailable" | "closed" | "off" | "live" | "pause" | "replay" | string;
  track: string;
  car: string;
  message: string;
}

export interface Recording {
  available: boolean;
  state: "idle" | "waiting" | "recording" | "stopping";
  session_id: number | null;
  started_at: string | null;
  sample_count: number;
  lap: number;
  lap_time_ms: number;
  last_lap_ms: number;
  best_lap_ms: number;
  speed_kmh: number;
  in_pit: boolean;
  message: string;
  last_session_id: number | null;
  game: Game;
}

async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let detail = `Error ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Not JSON; keep the status text.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const api = {
  overview: () => get<Overview>("/api/overview"),
  tracks: () => get<Track[]>("/api/tracks"),
  highlights: (sessionId: number, lap: number) =>
    get<LapHighlights>(`/api/sessions/${sessionId}/laps/${lap}/highlights`),
  recording: () => get<Recording>("/api/recording"),
  startRecording: () => get<Recording>("/api/recording/start", { method: "POST" }),
  stopRecording: () => get<Recording>("/api/recording/stop", { method: "POST" }),
  sessions: () => get<Session[]>("/api/sessions"),
  laps: (sessionId: number) => get<SessionLaps>(`/api/sessions/${sessionId}/laps`),
  compare: (params: { session: number; lap: number; refSession?: number; refLap?: number }) => {
    const query = new URLSearchParams({ session: String(params.session), lap: String(params.lap) });
    if (params.refSession !== undefined) query.set("ref_session", String(params.refSession));
    if (params.refLap !== undefined) query.set("ref_lap", String(params.refLap));
    return get<Comparison>(`/api/compare?${query.toString()}`);
  },
};
