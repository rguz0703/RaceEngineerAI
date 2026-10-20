import { useEffect, useMemo, useState } from "react";
import { ControlCenter } from "../components/ControlCenter";
import { lapTime, signed } from "../format";
import { useLive, type LiveEvent, type LiveFrame, type LiveReference } from "../useLive";
import type { RecordingControl } from "../useRecording";

/** What the engineer's screen shows while driving: delta first, then the car. */
export function LiveView({ control }: { control: RecordingControl }) {
  const live = useLive();
  const recording = live.state === "recording" || live.state === "stopping";
  const frame = live.frame;
  return (
    <>
      <div className="live-head">
        <h1>En vivo</h1>
        <span className={`conn ${live.connected ? "on" : "off"}`}>
          {live.connected ? "conectado" : "reconectando…"}
        </span>
      </div>
      {!recording || !frame ? (
        <>
          <ControlCenter
            recording={control.recording}
            error={control.error}
            busy={control.busy}
            onStart={() => void control.start()}
            onStop={() => void control.stop()}
          />
          <p className="muted">
            {recording
              ? "Grabando: esperando las primeras lecturas…"
              : "Pulsa Grabar con el coche en pista y aquí verás la telemetría en directo."}
          </p>
        </>
      ) : (
        <LivePanel frame={frame} reference={live.reference} trace={live.trace} maxRpm={live.maxRpm} game={live.game} onStop={() => void control.stop()} busy={control.busy} />
      )}
    </>
  );
}

function LivePanel({
  frame,
  reference,
  trace,
  maxRpm,
  game,
  onStop,
  busy,
}: {
  frame: LiveFrame;
  reference: LiveReference | null;
  trace: [number, number][];
  maxRpm: number;
  game: string;
  onStop: () => void;
  busy: boolean;
}) {
  const delta = frame.delta_s;
  const tone = delta === null ? "even" : delta > 0.02 ? "lose" : delta < -0.02 ? "gain" : "even";
  const paused = game === "pause" || game === "replay";
  return (
    <div className="live">
      <AlertBanner events={frame.events} />
      <section className={`panel live-delta ${tone}`}>
        <span className="live-best">
          <span className="label">Tu mejor vuelta</span>
          <span className="live-best-value mono">{reference ? lapTime(reference.time_ms) : "—:—.———"}</span>
          <span className="muted small">
            {reference ? reference.label : "Termina una vuelta limpia para tener referencia"}
          </span>
        </span>
        <span className="live-divider" aria-hidden="true" />
        <span className="label">
          Delta
          {paused && <span className="badge warn">en pausa</span>}
          {frame.in_pit && <span className="badge warn">boxes</span>}
        </span>
        <span className="live-delta-value mono">{delta === null ? "—" : signed(delta, 2)}</span>
      </section>

      <section className="live-grid">
        <div className="panel stat">
          <span className="stat-label">Vuelta {frame.lap}</span>
          <span className="stat-value live-timer">{lapTime(frame.lap_time_ms)}</span>
        </div>
        <div className="panel stat">
          <span className="stat-label">Velocidad</span>
          <span className="stat-value">
            {Math.round(frame.speed_kmh)} <span className="unit">km/h</span>
          </span>
        </div>
        <div className="panel stat">
          <span className="stat-label">Marcha</span>
          <span className="stat-value live-gear">{frame.gear === -1 ? "R" : frame.gear === 0 ? "N" : frame.gear}</span>
        </div>
      </section>

      <section className="panel live-inputs">
        <Bar label="RPM" value={maxRpm > 0 ? frame.rpm / maxRpm : 0} text={`${Math.round(frame.rpm)}`} tone="rpm" />
        <Bar label="Acel." value={frame.throttle} text={`${Math.round(frame.throttle * 100)} %`} tone="throttle" />
        <Bar label="Freno" value={frame.brake} text={`${Math.round(frame.brake * 100)} %`} tone="brake" />
        <div className="steer">
          <span className="label">Volante</span>
          <div className="steer-track">
            <span className="steer-mark" style={{ left: `${50 + frame.steering * 50}%` }} />
          </div>
        </div>
      </section>

      <section className="live-bottom">
        {reference && <LiveMap reference={reference} frame={frame} />}
        <div className="panel live-trace">
          <span className="label">Delta en esta vuelta</span>
          <DeltaTrace trace={trace} length={reference?.length_m ?? 1} />
          <div className="live-laps">
            <span>
              <span className="label">Última</span> <span className="mono">{frame.last_lap_ms ? lapTime(frame.last_lap_ms) : "—"}</span>
            </span>
            <span>
              <span className="label">Mejor</span> <span className="mono">{frame.best_lap_ms ? lapTime(frame.best_lap_ms) : "—"}</span>
            </span>
          </div>
        </div>
      </section>

      {frame.events.length > 0 && (
        <section className="panel live-events">
          <span className="label">Avisos de esta sesión</span>
          <ul>
            {[...frame.events].reverse().map((e) => (
              <li key={e.id} className={e.level}>
                <span className="mono muted">V{e.lap}</span> {e.text}
                {e.kind !== "best_lap" && <span className="muted small"> · {Math.round(e.distance_m)} m</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <button className="rec-button stop" onClick={onStop} disabled={busy}>
        ■ Detener
      </button>
    </div>
  );
}

const ALERT_MS = 4000;

/** Shows each new event for a few seconds: yellow for incidents, green for a new best lap. */
function AlertBanner({ events }: { events: LiveEvent[] }) {
  const latest = events[events.length - 1];
  const [shown, setShown] = useState<LiveEvent | null>(null);
  const [seen, setSeen] = useState<number>(() => latest?.id ?? 0);

  useEffect(() => {
    if (!latest || latest.id <= seen) return;
    setSeen(latest.id);
    setShown(latest);
    const timer = window.setTimeout(() => setShown(null), ALERT_MS);
    return () => window.clearTimeout(timer);
  }, [latest, seen]);

  if (!shown) return null;
  return (
    <div className={`alert-banner ${shown.level}`} role="alert">
      <span className="alert-icon" aria-hidden="true">
        {shown.level === "good" ? "★" : "⚠"}
      </span>
      {shown.text}
    </div>
  );
}

function Bar({ label, value, text, tone }: { label: string; value: number; text: string; tone: string }) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div className="bar-row">
      <span className="label">{label}</span>
      <div className="bar">
        <span className={`bar-fill ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="mono bar-text">{text}</span>
    </div>
  );
}

function LiveMap({ reference, frame }: { reference: LiveReference; frame: LiveFrame }) {
  const box = useMemo(() => {
    const minX = Math.min(...reference.x);
    const maxX = Math.max(...reference.x);
    const minZ = Math.min(...reference.z);
    const maxZ = Math.max(...reference.z);
    const span = Math.max(maxX - minX, maxZ - minZ, 1);
    const pad = span * 0.06;
    return {
      minX,
      minZ,
      stroke: span * 0.012,
      viewBox: `${-pad} ${-pad} ${maxX - minX + 2 * pad} ${maxZ - minZ + 2 * pad}`,
      points: reference.x.map((x, i) => `${(x - minX).toFixed(1)},${(reference.z[i] - minZ).toFixed(1)}`).join(" "),
    };
  }, [reference]);
  return (
    <figure className="panel live-map">
      <svg viewBox={box.viewBox} role="img" aria-label="Posición en el circuito">
        <polyline className="track-outline" points={box.points} strokeWidth={box.stroke * 2.2} />
        <polyline className="live-line" points={box.points} strokeWidth={box.stroke * 0.6} />
        <circle className="track-dot" cx={frame.pos_x - box.minX} cy={frame.pos_z - box.minZ} r={box.stroke * 1.6} />
      </svg>
    </figure>
  );
}

function DeltaTrace({ trace, length }: { trace: [number, number][]; length: number }) {
  const width = 300;
  const height = 90;
  if (trace.length < 2) return <svg className="delta-trace" viewBox={`0 0 ${width} ${height}`} />;
  const maxAbs = Math.max(0.2, ...trace.map(([, d]) => Math.abs(d)));
  const x = (d: number) => (d / length) * width;
  // Above the line = losing time, as in the comparison charts.
  const y = (v: number) => height / 2 - (v / maxAbs) * (height / 2 - 4);
  const points = trace.map(([d, v]) => `${x(d).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const last = trace[trace.length - 1][1];
  return (
    <svg className="delta-trace" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <line x1={0} x2={width} y1={height / 2} y2={height / 2} className="zero" />
      <polyline points={points} className={last > 0 ? "lose" : "gain"} />
    </svg>
  );
}
