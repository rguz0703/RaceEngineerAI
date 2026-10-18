import { useEffect, useMemo, useState } from "react";
import { api, type Session, type SessionLaps } from "../api";
import { Status } from "../components/Status";
import { lapKind, lapTime, prettyName } from "../format";
import { href } from "../route";
import { useAsync } from "../useAsync";

const BEST = "best";

function sessionLabel(s: Session): string {
  const date = new Date(s.started_at).toLocaleDateString("es", { day: "numeric", month: "short" });
  return `#${s.id} · ${prettyName(s.track)} · ${prettyName(s.car)} · ${date}`;
}

function useLaps(sessionId: number | null): SessionLaps | null {
  const [laps, setLaps] = useState<SessionLaps | null>(null);
  useEffect(() => {
    let cancelled = false;
    setLaps(null);
    if (sessionId !== null) void api.laps(sessionId).then((l) => !cancelled && setLaps(l));
    return () => {
      cancelled = true;
    };
  }, [sessionId]);
  return laps;
}

/** Choose any two finished laps on the same track, across sessions. */
export function PickView() {
  const state = useAsync(api.sessions, []);
  return (
    <>
      <h1>Comparar vueltas</h1>
      <p className="muted">Elige una vuelta y contra qué compararla: puede ser de otra sesión en el mismo circuito.</p>
      <Status state={state}>{(sessions) => <Picker sessions={sessions.filter((s) => s.lap_count > 0)} />}</Status>
    </>
  );
}

function Picker({ sessions }: { sessions: Session[] }) {
  const [targetId, setTargetId] = useState<number | null>(sessions[0]?.id ?? null);
  const [lap, setLap] = useState<string>("");
  const [refId, setRefId] = useState<number | null>(sessions[0]?.id ?? null);
  const [refLap, setRefLap] = useState<string>(BEST);
  const target = sessions.find((s) => s.id === targetId) ?? null;
  const targetLaps = useLaps(targetId);
  const refLaps = useLaps(refId);
  const sameTrack = useMemo(
    () => sessions.filter((s) => target && s.track === target.track && s.track_config === target.track_config),
    [sessions, target],
  );

  // Default to the session's last finished lap.
  useEffect(() => {
    const finished = targetLaps?.laps.filter((l) => l.time_ms !== null) ?? [];
    setLap(finished.length ? String(finished[finished.length - 1].number) : "");
  }, [targetLaps]);

  if (sessions.length === 0) return <p className="muted">Todavía no hay vueltas terminadas.</p>;

  const finished = (l: SessionLaps | null) => l?.laps.filter((x) => x.time_ms !== null) ?? [];
  const ready = targetId !== null && lap !== "" && refId !== null;
  const link = ready
    ? href({
        page: "compare",
        session: targetId,
        lap: Number(lap),
        refSession: refId === targetId ? undefined : refId,
        refLap: refLap === BEST ? undefined : Number(refLap),
      })
    : undefined;

  return (
    <div className="picker">
      <fieldset className="panel">
        <legend className="label">Vuelta a analizar</legend>
        <label>
          Sesión
          <select
            value={targetId ?? ""}
            onChange={(e) => {
              const id = Number(e.target.value);
              setTargetId(id);
              setRefId(id);
              setRefLap(BEST);
            }}
          >
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {sessionLabel(s)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Vuelta
          <select value={lap} onChange={(e) => setLap(e.target.value)} disabled={!targetLaps}>
            {finished(targetLaps).map((l) => (
              <option key={l.number} value={l.number}>
                V{l.number} · {lapTime(l.time_ms)} · {lapKind(l)}
                {l.off_track ? " · fuera de pista" : ""}
              </option>
            ))}
          </select>
        </label>
      </fieldset>

      <span className="picker-vs mono" aria-hidden="true">
        VS
      </span>

      <fieldset className="panel">
        <legend className="label">Referencia</legend>
        <label>
          Sesión
          <select
            value={refId ?? ""}
            onChange={(e) => {
              setRefId(Number(e.target.value));
              setRefLap(BEST);
            }}
          >
            {sameTrack.map((s) => (
              <option key={s.id} value={s.id}>
                {sessionLabel(s)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Vuelta
          <select value={refLap} onChange={(e) => setRefLap(e.target.value)} disabled={!refLaps}>
            <option value={BEST}>
              Mejor vuelta limpia
              {refLaps?.best_clean_lap && !(refId === targetId && refLaps.best_clean_lap === Number(lap))
                ? ` (V${refLaps.best_clean_lap})`
                : ""}
            </option>
            {finished(refLaps).map((l) => (
              <option key={l.number} value={l.number}>
                V{l.number} · {lapTime(l.time_ms)} · {lapKind(l)}
              </option>
            ))}
          </select>
        </label>
      </fieldset>

      <a className={`rec-button start compare-go${ready ? "" : " disabled"}`} href={link} aria-disabled={!ready}>
        Comparar
      </a>
    </div>
  );
}
