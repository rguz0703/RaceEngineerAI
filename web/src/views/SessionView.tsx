import { useState } from "react";
import { api, type Lap } from "../api";
import { Status } from "../components/Status";
import { dateTime, lapKind, lapTime, prettyName, simName } from "../format";
import { href } from "../route";
import { useAsync } from "../useAsync";

export function SessionView({ id }: { id: number }) {
  const state = useAsync(() => api.laps(id), [id]);
  return (
    <Status state={state}>
      {({ session, laps, best_clean_lap }) => (
        <>
          <a className="back" href={href({ page: "sessions" })}>
            ← Sesiones
          </a>
          <span className="sim">{simName(session.sim)}</span>
          <h1>
            {prettyName(session.track)}
            {session.track_config && <span className="muted"> · {prettyName(session.track_config)}</span>}
          </h1>
          <p className="muted">
            {prettyName(session.car)} · {dateTime(session.started_at)}
            {session.track_length_m > 0 && ` · ${Math.round(session.track_length_m).toLocaleString("es")} m`}
          </p>
          <LapsTable sessionId={id} laps={laps} best={best_clean_lap} />
        </>
      )}
    </Status>
  );
}

function LapsTable({ sessionId, laps, best }: { sessionId: number; laps: Lap[]; best: number | null }) {
  const finished = laps.filter((l) => l.time_ms !== null);
  const [reference, setReference] = useState<string>("best");
  if (laps.length === 0) return <p className="muted">Esta sesión no tiene vueltas.</p>;
  const refLap = reference === "best" ? undefined : Number(reference);
  const comparedAgainst = refLap ?? best;
  return (
    <>
      <div className="toolbar">
        <label>
          Comparar contra{" "}
          <select value={reference} onChange={(e) => setReference(e.target.value)}>
            <option value="best">
              {best !== null ? `mejor vuelta limpia (${best})` : "mejor vuelta (no hay limpias)"}
            </option>
            {finished.map((l) => (
              <option key={l.number} value={l.number}>
                vuelta {l.number} · {lapTime(l.time_ms)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Vuelta</th>
              <th className="num">Tiempo</th>
              <th>Tipo</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {laps.map((lap) => (
              <tr key={lap.number} className={lap.number === best ? "best" : undefined}>
                <td>
                  {lap.number}
                  {lap.number === best && <span className="badge good">mejor</span>}
                </td>
                <td className="num">
                  {!lap.official && lap.time_ms !== null && <span title="Tiempo estimado">≈</span>}
                  {lapTime(lap.time_ms)}
                </td>
                <td className="wrap">
                  {lapKind(lap)}
                  {lap.off_track && (
                    <span className="badge warn" title="Más de dos llantas fuera de pista">
                      fuera de pista
                    </span>
                  )}
                </td>
                <td className="right">
                  {lap.time_ms !== null && lap.number !== comparedAgainst && (
                    <a
                      className="button"
                      aria-label={`Comparar vuelta ${lap.number}`}
                      href={href({ page: "compare", session: sessionId, lap: lap.number, refLap })}
                    >
                      <span className="wide-only">Comparar</span>
                      <span className="narrow-only" aria-hidden="true">
                        ›
                      </span>
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
