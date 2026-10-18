import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { ControlCenter } from "../components/ControlCenter";
import { Status } from "../components/Status";
import { dateTime, prettyName, simName } from "../format";
import { href } from "../route";
import { useAsync } from "../useAsync";
import type { RecordingControl } from "../useRecording";

export function SessionsView({ control }: { control: RecordingControl }) {
  // Reload the list whenever a recording finishes.
  const [version, setVersion] = useState(0);
  const lastSession = control.recording?.last_session_id ?? null;
  const seen = useRef(lastSession);
  useEffect(() => {
    if (lastSession !== seen.current) {
      seen.current = lastSession;
      setVersion((v) => v + 1);
    }
  }, [lastSession]);
  const state = useAsync(api.sessions, [version]);
  return (
    <>
      <ControlCenter
        recording={control.recording}
        error={control.error}
        busy={control.busy}
        onStart={() => void control.start()}
        onStop={() => void control.stop()}
      />
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
