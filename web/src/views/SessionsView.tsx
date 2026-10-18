import { api } from "../api";
import { SessionCard } from "../components/SessionCard";
import { Status } from "../components/Status";
import { useAsync } from "../useAsync";

export function SessionsView({ version }: { version: number }) {
  const state = useAsync(api.sessions, [version]);
  return (
    <>
      <h1>Sesiones</h1>
      <Status state={state}>
        {(sessions) =>
          sessions.length === 0 ? (
            <p className="muted">
              Todavía no hay sesiones. Ve a Inicio y pulsa <strong>Grabar</strong> con el juego en pista.
            </p>
          ) : (
            <ul className="cards">
              {sessions.map((s) => (
                <li key={s.id}>
                  <SessionCard s={s} />
                </li>
              ))}
            </ul>
          )
        }
      </Status>
    </>
  );
}
