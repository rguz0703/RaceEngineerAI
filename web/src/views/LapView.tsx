import { useMemo, useState } from "react";
import { api, type LapHighlights, type Moment, type Segment } from "../api";
import { Status } from "../components/Status";
import { dateTime, lapKind, lapTime, prettyName, signed, simName } from "../format";
import { href } from "../route";
import { useAsync } from "../useAsync";

const KIND_CLASS: Record<string, string> = {
  top_speed: "m-speed",
  braking: "m-brake",
  corner: "m-corner",
};

/** One lap's key moments on the map, with the numbers to back them up. */
export function LapView({ session, lap }: { session: number; lap: number }) {
  const state = useAsync(() => api.highlights(session, lap), []);
  return (
    <>
      <a className="back" href={href({ page: "session", id: session })}>
        ← Vueltas de la sesión {session}
      </a>
      <Status state={state}>{(h) => <Highlights h={h} />}</Status>
    </>
  );
}

function Highlights({ h }: { h: LapHighlights }) {
  const [active, setActive] = useState<number | null>(null);
  const { session, lap, stats, vs_best: gap } = h;
  return (
    <div className="lapview">
      <header className="lap-hero panel">
        <div>
          <span className="sim">{simName(session.sim)}</span>
          <h1>
            {prettyName(session.track)}
            {session.track_config && <span className="muted"> · {prettyName(session.track_config)}</span>}
          </h1>
          <p className="muted">
            {prettyName(session.car)} · sesión #{session.id} · {dateTime(session.started_at)}
          </p>
        </div>
        <div className="lap-hero-time">
          <span className="label">Vuelta {lap.number}</span>
          <span className="lap-hero-value mono">{lapTime(lap.time_ms)}</span>
          <span className="lap-hero-tags">
            <span className="badge">{lapKind(lap).toLowerCase()}</span>
            {lap.off_track && <span className="badge warn">fuera de pista</span>}
          </span>
        </div>
      </header>

      <div className="lap-grid">
        <section>
          <h2>Momentos clave</h2>
          <LapMap h={h} active={active} onActive={setActive} />
        </section>
        <section>
          <ol className="moments">
            {h.moments.map((m, i) => (
              <li
                key={i}
                className={`moment panel${m.warn ? " warn" : ""}${active === i ? " active" : ""}`}
                onMouseEnter={() => setActive(i)}
                onMouseLeave={() => setActive(null)}
                onClick={() => setActive(active === i ? null : i)}
              >
                <span className={`moment-n ${m.warn ? "m-warn" : (KIND_CLASS[m.kind] ?? "")}`}>
                  {m.warn ? "!" : i + 1}
                </span>
                <span className="moment-body">
                  <span className="label">{m.title}</span>
                  <span className="moment-value mono">{m.value}</span>
                  <span className="muted small">{m.detail}</span>
                </span>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <h2>Cómo la manejaste</h2>
      <div className="lap-stats">
        <Stat label="A fondo" value={`${stats.full_throttle_pct.toFixed(0)} %`} />
        <Stat label="Frenando" value={`${stats.braking_pct.toFixed(0)} %`} />
        <Stat label="Sin acelerar ni frenar" value={`${stats.coasting_pct.toFixed(0)} %`} />
        <Stat label="Vel. media" value={`${stats.avg_speed_kmh.toFixed(0)} km/h`} />
        <Stat label="RPM máx" value={stats.max_rpm.toFixed(0)} />
        <Stat label="Cambios de marcha" value={String(stats.gear_changes)} />
      </div>

      {gap && (
        <>
          <h2>{gap.total_s <= 0 ? "Tu mejor vuelta aquí, contra la siguiente" : "Contra tu mejor vuelta aquí"}</h2>
          <section className="panel lap-gap">
            <div className="lap-gap-head">
              <span>
                <span className="muted">Referencia </span>
                <span className="mono">
                  V{gap.reference.lap} {lapTime(gap.reference.time_ms)}
                </span>
                <span className="muted small">
                  {" "}
                  · sesión #{gap.reference.session_id}
                  {!gap.clean && " · con salida de pista"}
                </span>
              </span>
              <span className={`lap-gap-total mono ${gap.total_s > 0 ? "lose" : "gain"}`}>
                {signed(gap.total_s)} s
              </span>
            </div>
            <div className="lap-gap-segments">
              <SegmentCard title="Donde más ganas" s={gap.best_segment} />
              <SegmentCard title="Donde más pierdes" s={gap.worst_segment} />
            </div>
            <a
              className="button"
              href={href({
                page: "compare",
                session: session.id,
                lap: lap.number,
                refSession: gap.reference.session_id,
                refLap: gap.reference.lap,
              })}
            >
              Ver comparación completa →
            </a>
          </section>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat panel">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
    </div>
  );
}

function SegmentCard({ title, s }: { title: string; s: Segment }) {
  return (
    <div className="seg-card">
      <span className="label">{title}</span>
      <span className={`mono seg-card-value ${s.delta_s > 0 ? "lose" : "gain"}`}>{signed(s.delta_s)} s</span>
      <span className="muted small">
        {Math.round(s.start_m)}–{Math.round(s.end_m)} m · vel. mín {Math.round(s.target_min_speed_kmh)} vs{" "}
        {Math.round(s.reference_min_speed_kmh)} km/h
      </span>
    </div>
  );
}

function LapMap({ h, active, onActive }: { h: LapHighlights; active: number | null; onActive: (i: number | null) => void }) {
  const box = useMemo(() => {
    const xs = h.path_x;
    const zs = h.path_z;
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minZ = Math.min(...zs);
    const maxZ = Math.max(...zs);
    const span = Math.max(maxX - minX, maxZ - minZ, 1);
    const pad = span * 0.08;
    return {
      minX,
      minZ,
      stroke: span * 0.012,
      viewBox: `${-pad} ${-pad} ${maxX - minX + 2 * pad} ${maxZ - minZ + 2 * pad}`,
      points: xs.map((x, i) => `${(x - minX).toFixed(1)},${(zs[i] - minZ).toFixed(1)}`).join(" "),
    };
  }, [h]);
  const marker = (m: Moment, i: number) => {
    const r = box.stroke * (active === i ? 2.6 : 2);
    return (
      <g
        key={i}
        className={`map-marker ${m.warn ? "m-warn" : (KIND_CLASS[m.kind] ?? "")}${active === i ? " active" : ""}`}
        transform={`translate(${m.pos_x - box.minX} ${m.pos_z - box.minZ})`}
        onMouseEnter={() => onActive(i)}
        onMouseLeave={() => onActive(null)}
      >
        <circle r={r} />
        <text fontSize={r * 1.1} dy="0.36em">
          {m.warn ? "!" : i + 1}
        </text>
      </g>
    );
  };
  return (
    <figure className="panel lap-map">
      <svg viewBox={box.viewBox} role="img" aria-label="Mapa de la vuelta con los momentos clave">
        <polyline className="track-outline" points={box.points} strokeWidth={box.stroke * 2.4} />
        <polyline className="lap-line" points={box.points} strokeWidth={box.stroke * 0.7} />
        {/* Incidents first so the numbered moments sit on top. */}
        {h.moments.map((m, i) => (m.warn ? marker(m, i) : null))}
        {h.moments.map((m, i) => (m.warn ? null : marker(m, i)))}
      </svg>
      <figcaption className="map-legend">
        <span className="swatch m-speed" /> velocidad <span className="swatch m-brake" /> frenada{" "}
        <span className="swatch m-corner" /> curva lenta <span className="swatch m-warn" /> incidente
      </figcaption>
    </figure>
  );
}
