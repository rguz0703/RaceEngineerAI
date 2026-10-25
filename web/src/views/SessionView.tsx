import { useState } from "react";
import { api, type Lap } from "../api";
import { Status } from "../components/Status";
import { dateTime, lapKind, lapTime, prettyName, sectorTime, sectorTones, simName } from "../format";
import { href } from "../route";
import { useAsync } from "../useAsync";

export function SessionView({ id }: { id: number }) {
  const state = useAsync(() => api.laps(id), [id]);
  return (
    <Status state={state}>
      {({ session, laps, best_clean_lap, best_sectors_ms, ideal_lap_ms }) => {
        const best = laps.find((l) => l.number === best_clean_lap);
        return (
          <>
            <a className="back" href={href({ page: "sessions" })}>
              ← Sesiones
            </a>
            <header className="sheet-head">
              <div>
                <span className="sim">{simName(session.sim)}</span>
                <h1>{prettyName(session.track)}</h1>
                <p className="muted">
                  {prettyName(session.car)}
                  {session.track_config && `, ${prettyName(session.track_config)}`}, {dateTime(session.started_at)}
                  {session.track_length_m > 0 && `. ${(session.track_length_m / 1000).toLocaleString("es", { maximumFractionDigits: 3 })} km por vuelta`}
                </p>
              </div>
              {ideal_lap_ms !== null && best?.time_ms != null && (
                <div className="ideal">
                  <span className="ideal-time">{lapTime(ideal_lap_ms)}</span>
                  <span className="muted small">
                    Tu vuelta ideal: tus mejores sectores juntos, {((best.time_ms - ideal_lap_ms) / 1000).toFixed(3)} s más
                    rápida que tu mejor vuelta.
                  </span>
                </div>
              )}
            </header>
            <LapsTable sessionId={id} laps={laps} best={best_clean_lap} bestSectors={best_sectors_ms} />
          </>
        );
      }}
    </Status>
  );
}

function LapsTable({
  sessionId,
  laps,
  best,
  bestSectors,
}: {
  sessionId: number;
  laps: Lap[];
  best: number | null;
  bestSectors: number[];
}) {
  const tones = sectorTones(laps, bestSectors);
  const hasSectors = laps.some((l) => l.sector_ms.length === 3);
  const bestTime = laps.find((l) => l.number === best)?.time_ms ?? null;
  const finished = laps.filter((l) => l.time_ms !== null);
  const [reference, setReference] = useState<string>("best");
  if (laps.length === 0) return <p className="muted">Esta sesión no tiene vueltas.</p>;
  const refLap = reference === "best" ? undefined : Number(reference);
  const comparedAgainst = refLap ?? best;
  return (
    <>
      <p className="muted small">Toca un tiempo para ver la ficha de esa vuelta, o › para compararla.</p>
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
      {hasSectors && (
        <p className="sector-legend small muted">
          <span className="tone best">Morado</span> mejor sector de la sesión ·{" "}
          <span className="tone gain">verde</span> mejoraste · <span className="tone lose">amarillo</span> más lento que tu
          mejor
        </p>
      )}
      <div className="table-wrap">
        <table className="timing">
          <thead>
            <tr>
              <th>Vuelta</th>
              {hasSectors && (
                <>
                  <th className="num sector-col">Sector 1</th>
                  <th className="num sector-col">Sector 2</th>
                  <th className="num sector-col">Sector 3</th>
                </>
              )}
              <th className="num">Tiempo</th>
              <th className="num wide-only">Dif.</th>
              <th className="kind-col">Tipo</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {laps.map((lap) => (
              <tr key={lap.number} className={lap.number === best ? "best" : lap.off_track ? "void" : undefined}>
                <td>{lap.number}</td>
                {hasSectors &&
                  [0, 1, 2].map((k) => (
                    <td key={k} className={`num sector-col sector ${tones.get(lap.number)?.[k] ?? ""}`}>
                      {lap.sector_ms.length === 3 ? sectorTime(lap.sector_ms[k]) : ""}
                    </td>
                  ))}
                <td className="num lap-time">
                  {!lap.official && lap.time_ms !== null && <span title="Tiempo estimado">≈</span>}
                  <a
                    className="lap-link"
                    href={href({ page: "lap", session: sessionId, lap: lap.number })}
                    title="Ver la ficha de esta vuelta"
                  >
                    {lapTime(lap.time_ms)}
                  </a>
                </td>
                <td className="num wide-only muted">
                  {lap.time_ms !== null && bestTime !== null && lap.number !== best
                    ? `+${((lap.time_ms - bestTime) / 1000).toFixed(3)}`
                    : ""}
                </td>
                <td className="wrap kind-col">
                  {lapKind(lap)}
                  {lap.off_track && (
                    <span className="flag" title="Más de dos llantas fuera de pista: no cuenta para tus mejores tiempos">
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
