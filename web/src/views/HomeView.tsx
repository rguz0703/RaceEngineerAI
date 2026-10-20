import { api } from "../api";
import { ControlCenter } from "../components/ControlCenter";
import { SessionCard } from "../components/SessionCard";
import { Sparkline } from "../components/Sparkline";
import { Status } from "../components/Status";
import { dateTime, lapTime, prettyName, signed, simName } from "../format";
import { href } from "../route";
import { useAsync } from "../useAsync";
import type { RecordingControl } from "../useRecording";

export function HomeView({ control, version }: { control: RecordingControl; version: number }) {
  const state = useAsync(api.overview, [version]);

  return (
    <>
      <ControlCenter
        recording={control.recording}
        error={control.error}
        busy={control.busy}
        onStart={() => void control.start()}
        onStop={() => void control.stop()}
      />
      <Status state={state}>
        {(o) =>
          o.totals.sessions === 0 ? (
            <p className="muted">Todavía no hay sesiones. Sal a pista y pulsa Grabar.</p>
          ) : (
            <>
              <div className="totals">
                <div className="stat panel">
                  <span className="stat-label">Sesiones</span>
                  <span className="stat-value">{o.totals.sessions}</span>
                </div>
                <div className="stat panel">
                  <span className="stat-label">Vueltas</span>
                  <span className="stat-value">{o.totals.laps}</span>
                </div>
                <div className="stat panel">
                  <span className="stat-label">Km recorridos</span>
                  <span className="stat-value">{o.totals.distance_km.toLocaleString("es")}</span>
                </div>
              </div>

              {o.best_laps.length > 0 && (
                <>
                  <h2>Mejores vueltas</h2>
                  <ul className="cards">
                    {o.best_laps.map((b) => {
                      const progress = o.progress.find(
                        (p) => p.track === b.track && p.track_config === b.track_config && p.car === b.car && p.sim === b.sim,
                      );
                      const times = progress?.points.map((p) => p.best_ms) ?? [];
                      const change = times.length >= 2 ? (times[times.length - 1] - times[0]) / 1000 : null;
                      return (
                        <li key={`${b.sim}/${b.track}/${b.track_config}/${b.car}`}>
                          <a className="card best-card" href={href({ page: "lap", session: b.session_id, lap: b.lap })}>
                            <span className="card-top">
                              <span className="sim">{simName(b.sim)}</span>
                              <span className="muted small">{dateTime(b.driven_at)}</span>
                            </span>
                            <span className="card-title">
                              {prettyName(b.track)}
                              {b.track_config && <span className="muted"> · {prettyName(b.track_config)}</span>}
                            </span>
                            <span className="muted small">{prettyName(b.car)}</span>
                            <span className="best-row">
                              <span className="best-time mono">{lapTime(b.time_ms)}</span>
                              <Sparkline values={times} />
                            </span>
                            <span className="muted small">
                              {times.length >= 2 && change !== null ? (
                                <>
                                  {times.length} sesiones ·{" "}
                                  <span className={change <= 0 ? "gain" : "lose"}>
                                    {signed(change, 3)} s desde la primera
                                  </span>
                                </>
                              ) : (
                                <>Vuelta {b.lap} · sesión #{b.session_id}</>
                              )}
                            </span>
                          </a>
                        </li>
                      );
                    })}
                  </ul>
                </>
              )}

              <div className="section-head">
                <h2>Últimas sesiones</h2>
                <a href={href({ page: "sessions" })}>Ver todas →</a>
              </div>
              <ul className="cards">
                {o.recent.map((s) => (
                  <li key={s.id}>
                    <SessionCard s={s} />
                  </li>
                ))}
              </ul>
            </>
          )
        }
      </Status>
    </>
  );
}
