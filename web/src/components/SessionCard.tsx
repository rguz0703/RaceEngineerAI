import type { Session } from "../api";
import { dateTime, lapTime, prettyName, simName } from "../format";
import { href } from "../route";

export function SessionCard({ s }: { s: Session }) {
  return (
    <a className="card" href={href({ page: "session", id: s.id })}>
      <span className="card-top">
        <span className="sim">{simName(s.sim)}</span>
        <span className="muted small mono">#{s.id}</span>
      </span>
      <span className="card-title">
        {prettyName(s.track)}
        {s.track_config && <span className="muted"> · {prettyName(s.track_config)}</span>}
      </span>
      <span className="muted small">{prettyName(s.car)}</span>
      <span className="card-foot">
        <span>
          <span className="label">Mejor</span>
          <span className="mono card-best">{lapTime(s.best_lap_ms)}</span>
        </span>
        <span className="right">
          <span className="label">Vueltas</span>
          <span className="mono">{s.lap_count}</span>
        </span>
      </span>
      <span className="muted small">{dateTime(s.started_at)}</span>
    </a>
  );
}
