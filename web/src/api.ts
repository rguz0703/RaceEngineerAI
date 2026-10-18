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
}

export interface Lap {
  number: number;
  time_ms: number | null;
  official: boolean;
  complete: boolean;
  out_lap: boolean;
  in_lap: boolean;
  off_track: boolean;
}

export interface SessionLaps {
  session: Session;
  laps: Lap[];
  best_clean_lap: number | null;
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

export interface Comparison {
  target: LapRef;
  reference: LapRef;
  partial: boolean;
  distance_m: number[];
  delta_s: number[];
  target_channels: Channels;
  reference_channels: Channels;
  track_x: number[];
  track_z: number[];
  segments: Segment[];
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
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
  sessions: () => get<Session[]>("/api/sessions"),
  laps: (sessionId: number) => get<SessionLaps>(`/api/sessions/${sessionId}/laps`),
  compare: (params: { session: number; lap: number; refSession?: number; refLap?: number }) => {
    const query = new URLSearchParams({ session: String(params.session), lap: String(params.lap) });
    if (params.refSession !== undefined) query.set("ref_session", String(params.refSession));
    if (params.refLap !== undefined) query.set("ref_lap", String(params.refLap));
    return get<Comparison>(`/api/compare?${query.toString()}`);
  },
};
