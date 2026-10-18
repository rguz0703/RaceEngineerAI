import type { Recording } from "../api";
import { lapTime, prettyName } from "../format";
import { href } from "../route";

const GAME_LABEL: Record<string, string> = {
  unavailable: "Solo en la PC con Windows",
  closed: "Assetto Corsa cerrado",
  off: "Assetto Corsa en el menú",
  live: "En pista",
  pause: "En pausa",
  replay: "Viendo una repetición",
};

interface Props {
  recording: Recording | null;
  error: string | null;
  busy: boolean;
  onStart: () => void;
  onStop: () => void;
}

export function ControlCenter({ recording, error, busy, onStart, onStop }: Props) {
  if (error && !recording) return <p className="error">No se pudo conectar con el programa: {error}</p>;
  if (!recording) return null;
  const { state, game } = recording;
  const active = state === "recording" || state === "stopping";
  const tone = active ? "rec" : game.state === "live" ? "ready" : "idle";
  return (
    <section className={`control ${tone}`} aria-live="polite">
      <div className="control-status">
        <span className={`dot ${tone}`} aria-hidden="true" />
        <div>
          <div className="control-title">
            {active ? "Grabando" : state === "waiting" ? "Esperando para grabar" : (GAME_LABEL[game.state] ?? game.state)}
            {game.message === "Modo demo" && <span className="badge good">demo</span>}
          </div>
          <div className="muted small">
            {active &&
              [
                recording.session_id !== null ? `Sesión ${recording.session_id}` : "",
                game.state !== "live" ? (GAME_LABEL[game.state] ?? game.state) : "",
                recording.in_pit ? "en boxes" : "",
              ]
                .filter(Boolean)
                .join(" · ")}
            {!active && game.track && (
              <>
                {prettyName(game.track)} · {prettyName(game.car)}
              </>
            )}
            {state === "waiting" && recording.message}
            {state === "idle" && !game.track && game.state !== "live" && "Abre el juego y sal a pista; luego pulsa Grabar."}
          </div>
        </div>
      </div>

      {active && (
        <div className="control-live">
          <div className="stat">
            <span className="stat-label">Vuelta</span>
            <span className="stat-value">{recording.lap}</span>
          </div>
          <div className="stat big">
            <span className="stat-label">Cronómetro</span>
            <span className="stat-value">{lapTime(recording.lap_time_ms)}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Última</span>
            <span className="stat-value">{recording.last_lap_ms ? lapTime(recording.last_lap_ms) : "—"}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Mejor</span>
            <span className="stat-value">{recording.best_lap_ms ? lapTime(recording.best_lap_ms) : "—"}</span>
          </div>
        </div>
      )}

      <div className="control-actions">
        {!recording.available ? (
          <p className="muted small">Este servidor se abrió sin grabadora.</p>
        ) : active || state === "waiting" ? (
          <button className="rec-button stop" onClick={onStop} disabled={busy || state === "stopping"}>
            ■ {state === "waiting" ? "Cancelar" : state === "stopping" ? "Guardando…" : "Detener"}
          </button>
        ) : (
          <button className="rec-button start" onClick={onStart} disabled={busy}>
            ● Grabar
          </button>
        )}
        {state === "idle" && recording.message && (
          <span className="small">
            {recording.message}{" "}
            {recording.last_session_id !== null && (
              <a href={href({ page: "session", id: recording.last_session_id })}>Ver vueltas</a>
            )}
          </span>
        )}
      </div>
    </section>
  );
}
