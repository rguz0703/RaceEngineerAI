import { useEffect, useRef, useState } from "react";

export interface LiveEvent {
  id: number;
  kind: "off_track" | "lockup" | "wheelspin" | "best_lap" | string;
  level: "warn" | "good";
  text: string;
  lap: number;
  distance_m: number;
}

export interface RadioCall {
  id: number;
  kind: "sector" | "lap" | "best_lap" | "tip" | "incident" | string;
  text: string;
  speech: string;
  lap: number;
}

export interface LiveSector {
  number: number;
  time_ms: number;
  /** Against the same sector of the reference lap. */
  delta_s: number | null;
  /** Fastest this sector has been driven in this session. */
  best: boolean;
}

export interface LiveFrame {
  lap: number;
  lap_time_ms: number;
  last_lap_ms: number;
  best_lap_ms: number;
  distance_m: number;
  delta_s: number | null;
  speed_kmh: number;
  throttle: number;
  brake: number;
  gear: number;
  rpm: number;
  steering: number;
  pos_x: number;
  pos_z: number;
  in_pit: boolean;
  reference_ms: number | null;
  reference_label: string;
  events: LiveEvent[];
  radio: RadioCall[];
  sectors: LiveSector[];
  last_sectors: LiveSector[];
}

export interface LiveReference {
  label: string;
  time_ms: number;
  length_m: number;
  x: number[];
  z: number[];
}

interface Message {
  state: string;
  game: string;
  frame: LiveFrame | null;
  reference?: LiveReference | null;
}

export interface LiveState {
  connected: boolean;
  state: string;
  game: string;
  frame: LiveFrame | null;
  reference: LiveReference | null;
  /** Delta along the current lap, for the trace: [distance, delta]. */
  trace: [number, number][];
  maxRpm: number;
}

/** Live telemetry pushed by the agent over a WebSocket; reconnects on its own. */
export function useLive(): LiveState {
  const [live, setLive] = useState<LiveState>({
    connected: false,
    state: "idle",
    game: "",
    frame: null,
    reference: null,
    trace: [],
    maxRpm: 0,
  });
  const lapRef = useRef<number | null>(null);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: number | undefined;
    let closed = false;

    const connect = () => {
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${window.location.host}/ws/live`);
      socket.onopen = () => setLive((l) => ({ ...l, connected: true }));
      socket.onmessage = (event) => {
        const msg = JSON.parse(event.data as string) as Message;
        setLive((l) => {
          const frame = msg.frame;
          let trace = l.trace;
          if (!frame) {
            trace = [];
            lapRef.current = null;
          } else {
            if (frame.lap !== lapRef.current) {
              trace = [];
              lapRef.current = frame.lap;
            }
            if (frame.delta_s !== null) {
              const last = trace[trace.length - 1];
              if (!last || frame.distance_m > last[0]) trace = [...trace, [frame.distance_m, frame.delta_s]];
            }
          }
          return {
            connected: true,
            state: msg.state,
            game: msg.game,
            frame,
            reference: msg.reference !== undefined ? msg.reference : l.reference,
            trace,
            maxRpm: frame ? Math.max(l.maxRpm, frame.rpm) : l.maxRpm,
          };
        });
      };
      socket.onclose = () => {
        setLive((l) => ({ ...l, connected: false }));
        if (!closed) retry = window.setTimeout(connect, 1500);
      };
    };
    connect();
    return () => {
      closed = true;
      window.clearTimeout(retry);
      socket?.close();
    };
  }, []);

  return live;
}
