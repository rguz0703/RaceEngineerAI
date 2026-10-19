import { useEffect, useMemo, useState } from "react";
import { api, type Lap, type SessionLaps, type Track } from "../api";
import { Status } from "../components/Status";
import { TrackThumb } from "../components/TrackThumb";
import { dateTime, lapKind, lapTime, prettyName, simName } from "../format";
import { href } from "../route";
import { useAsync } from "../useAsync";

interface LapPick {
  session: number;
  lap: Lap;
}

const isClean = (l: Lap) => l.time_ms !== null && l.complete && !(l.off_track || l.out_lap || l.in_lap);
const trackKey = (t: Track) => `${t.sim}/${t.track}/${t.track_config}`;

/** Choose two laps in three steps: track, your lap, reference. */
export function PickView() {
  const state = useAsync(api.tracks, []);
  return (
    <>
      <h1>Comparar vueltas</h1>
      <Status state={state}>{(tracks) => <Picker tracks={tracks.filter((t) => t.lap_count > 0)} />}</Status>
    </>
  );
}

function Picker({ tracks }: { tracks: Track[] }) {
  const [key, setKey] = useState<string | null>(tracks.length === 1 ? trackKey(tracks[0]) : null);
  const track = tracks.find((t) => trackKey(t) === key) ?? null;
  const [sessions, setSessions] = useState<SessionLaps[] | null>(null);
  const [target, setTarget] = useState<LapPick | null>(null);
  const [reference, setReference] = useState<LapPick | "best">("best");

  useEffect(() => {
    let cancelled = false;
    setSessions(null);
    setTarget(null);
    setReference("best");
    if (track) {
      void Promise.all(track.session_ids.map((id) => api.laps(id))).then((all) => !cancelled && setSessions(all));
    }
    return () => {
      cancelled = true;
    };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const allLaps = useMemo(
    () => (sessions ?? []).flatMap((s) => s.laps.filter((l) => l.time_ms !== null).map((lap) => ({ session: s.session.id, lap }))),
    [sessions],
  );
  const fastest = allLaps.length ? Math.min(...allLaps.map((p) => p.lap.time_ms!)) : 0;
  const slowest = allLaps.length ? Math.max(...allLaps.map((p) => p.lap.time_ms!)) : 0;
  const same = (a: LapPick, b: LapPick) => a.session === b.session && a.lap.number === b.lap.number;

  // Your best lap on this track, excluding the one being analysed: clean first.
  const bestRef = useMemo(() => {
    const others = allLaps.filter((p) => !target || !same(p, target));
    const pool = others.some((p) => isClean(p.lap)) ? others.filter((p) => isClean(p.lap)) : others;
    return pool.reduce<LapPick | null>((best, p) => (!best || p.lap.time_ms! < best.lap.time_ms! ? p : best), null);
  }, [allLaps, target]);
  const ref = reference === "best" ? bestRef : reference;

  if (tracks.length === 0) return <p className="muted">Todavía no hay vueltas terminadas. Graba una sesión primero.</p>;

  return (
    <div className="pick">
      <Step n={1} title="Circuito" done={track !== null} summary={track && `${prettyName(track.track)}${track.track_config ? ` · ${prettyName(track.track_config)}` : ""}`} onEdit={() => setKey(null)}>
        <ul className="track-cards">
          {tracks.map((t) => (
            <li key={trackKey(t)}>
              <button className="track-card panel" onClick={() => setKey(trackKey(t))}>
                <TrackThumb x={t.outline_x} z={t.outline_z} />
                <span className="track-card-body">
                  <span className="sim">{simName(t.sim)}</span>
                  <span className="card-title">
                    {prettyName(t.track)}
                    {t.track_config && <span className="muted"> · {prettyName(t.track_config)}</span>}
                  </span>
                  <span className="muted small">{t.cars.map(prettyName).join(", ")}</span>
                  <span className="track-card-best mono">{t.best ? lapTime(t.best.time_ms) : "—"}</span>
                  <span className="muted small">
                    {t.session_ids.length} {t.session_ids.length === 1 ? "sesión" : "sesiones"} · {t.lap_count}{" "}
                    {t.lap_count === 1 ? "vuelta" : "vueltas"}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Step>

      {track && (
        <Step
          n={2}
          title="Tu vuelta"
          done={target !== null}
          summary={target && `V${target.lap.number} · ${lapTime(target.lap.time_ms)} · sesión #${target.session}`}
          onEdit={() => setTarget(null)}
        >
          {!sessions ? (
            <p className="muted">Cargando vueltas…</p>
          ) : (
            <LapLists sessions={sessions} fastest={fastest} slowest={slowest} onPick={(p) => setTarget(p)} isSelected={(p) => !!target && same(p, target)} />
          )}
        </Step>
      )}

      {track && target && sessions && (
        <Step n={3} title="Comparar contra" done={false}>
          <button className={`ref-best panel${reference === "best" ? " selected" : ""}`} onClick={() => setReference("best")}>
            <span className="label">{bestRef && isClean(bestRef.lap) ? "Tu mejor vuelta limpia aquí" : "Tu vuelta más rápida aquí"}</span>
            <span className="track-card-best mono">{bestRef ? lapTime(bestRef.lap.time_ms) : "—"}</span>
            <span className="muted small">
              {bestRef ? `V${bestRef.lap.number} · sesión #${bestRef.session}` : "No hay otra vuelta terminada"}
              {bestRef && !isClean(bestRef.lap) && " · no hay vueltas limpias"}
            </span>
          </button>
          <p className="muted small">o elige cualquier otra vuelta:</p>
          <LapLists
            sessions={sessions}
            fastest={fastest}
            slowest={slowest}
            onPick={(p) => setReference(p)}
            isSelected={(p) => reference !== "best" && same(p, reference)}
            disabled={(p) => same(p, target)}
          />
        </Step>
      )}

      {target && ref && (
        <div className="compare-bar">
          <span className="compare-bar-text">
            <span className="mono">V{target.lap.number} {lapTime(target.lap.time_ms)}</span>
            <span className="muted"> vs </span>
            <span className="mono">V{ref.lap.number} {lapTime(ref.lap.time_ms)}</span>
          </span>
          <a
            className="rec-button start"
            href={href({
              page: "compare",
              session: target.session,
              lap: target.lap.number,
              refSession: ref.session,
              refLap: ref.lap.number,
            })}
          >
            Comparar →
          </a>
        </div>
      )}
    </div>
  );
}

function Step({
  n,
  title,
  done,
  summary,
  onEdit,
  children,
}: {
  n: number;
  title: string;
  done: boolean;
  summary?: string | null;
  onEdit?: () => void;
  children: React.ReactNode;
}) {
  return (
    <section className={`step${done ? " done" : ""}`}>
      <header className="step-head">
        <span className="step-num mono">{n}</span>
        <span className="step-title">{title}</span>
        {done && summary && (
          <>
            <span className="step-summary">{summary}</span>
            {onEdit && (
              <button className="chip" onClick={onEdit}>
                cambiar
              </button>
            )}
          </>
        )}
      </header>
      {!done && <div className="step-body">{children}</div>}
    </section>
  );
}

function LapLists({
  sessions,
  fastest,
  slowest,
  onPick,
  isSelected,
  disabled,
}: {
  sessions: SessionLaps[];
  fastest: number;
  slowest: number;
  onPick: (p: LapPick) => void;
  isSelected: (p: LapPick) => boolean;
  disabled?: (p: LapPick) => boolean;
}) {
  const spread = Math.max(slowest - fastest, 1);
  return (
    <div className="lap-lists">
      {sessions.map(({ session, laps }) => {
        const finished = laps.filter((l) => l.time_ms !== null);
        if (!finished.length) return null;
        return (
          <div key={session.id} className="lap-group panel">
            <div className="lap-group-head">
              <span>
                <span className="mono">#{session.id}</span> · {dateTime(session.started_at)}
              </span>
              <span className="muted small">{prettyName(session.car)}</span>
            </div>
            {finished.map((lap) => {
              const pick = { session: session.id, lap };
              const off = disabled?.(pick) ?? false;
              const gap = (lap.time_ms! - fastest) / 1000;
              return (
                <button
                  key={lap.number}
                  className={`lap-row${isSelected(pick) ? " selected" : ""}`}
                  onClick={() => onPick(pick)}
                  disabled={off}
                >
                  <span className="lap-row-n mono">V{lap.number}</span>
                  <span className="lap-row-main">
                    <span className="lap-row-time mono">{lapTime(lap.time_ms)}</span>
                    <span className="lap-row-tags">
                      {gap === 0 && <span className="badge good">mejor</span>}
                      {lap.off_track && <span className="badge warn">fuera de pista</span>}
                      {(lap.out_lap || lap.in_lap || !lap.complete) && (
                        <span className="badge">{lapKind(lap).toLowerCase()}</span>
                      )}
                    </span>
                  </span>
                  <span className="lap-row-bar" aria-hidden="true">
                    <span
                      style={{ width: `${8 + 92 * (1 - (lap.time_ms! - fastest) / spread)}%` }}
                      className={gap === 0 ? "best" : ""}
                    />
                  </span>
                  <span className="lap-row-gap muted small mono">{gap === 0 ? "" : `+${gap.toFixed(3)}`}</span>
                </button>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
