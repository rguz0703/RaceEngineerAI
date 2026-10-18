import { api } from "../api";
import { Status } from "../components/Status";
import { dateTime, prettyName, simName } from "../format";
import { href } from "../route";
import { useAsync } from "../useAsync";

export function SessionsView() {
  const state = useAsync(api.sessions, []);
  return (
    <>
      <h1>Sesiones</h1>
      <Status state={state}>
        {(sessions) =>
          sessions.length === 0 ? (
            <p className="muted">
              Todavía no hay sesiones. Graba una con <code>raceengineer record --source ac</code>.
            </p>
          ) : (
            <ul className="cards">
              {sessions.map((s) => (
                <li key={s.id}>
                  <a className="card" href={href({ page: "session", id: s.id })}>
                    <span className="sim">{simName(s.sim)}</span>
                    <span className="card-title">
                      {prettyName(s.track)}
                      {s.track_config && <span className="muted"> · {prettyName(s.track_config)}</span>}
                    </span>
                    <span>{prettyName(s.car)}</span>
                    <span className="muted small">
                      Sesión {s.id} · {dateTime(s.started_at)} · {s.sample_count.toLocaleString("es")} muestras
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          )
        }
      </Status>
    </>
  );
}
