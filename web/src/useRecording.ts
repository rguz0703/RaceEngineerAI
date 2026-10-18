import { useCallback, useEffect, useState } from "react";
import { api, type Recording } from "./api";

const POLL_MS = 1000;

export interface RecordingControl {
  recording: Recording | null;
  error: string | null;
  start: () => Promise<void>;
  stop: () => Promise<void>;
  busy: boolean;
}

/** Live recording status, refreshed every second (WebSocket push comes with the live view). */
export function useRecording(): RecordingControl {
  const [recording, setRecording] = useState<Recording | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const next = await api.recording();
        if (!cancelled) {
          setRecording(next);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
      if (!cancelled) timer = window.setTimeout(tick, POLL_MS);
    };
    void tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  const run = useCallback(async (action: () => Promise<Recording>) => {
    setBusy(true);
    try {
      setRecording(await action());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  return {
    recording,
    error,
    busy,
    start: () => run(api.startRecording),
    stop: () => run(api.stopRecording),
  };
}
