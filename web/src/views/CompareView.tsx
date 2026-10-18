import { useMemo, useState } from "react";
import { api, type Comparison } from "../api";
import { Chart, type Series } from "../components/Chart";
import { Status } from "../components/Status";
import { TrackMap, segmentTone } from "../components/TrackMap";
import { lapTime, signed } from "../format";
import { href } from "../route";
import { useAsync } from "../useAsync";

interface Props {
  session: number;
  lap: number;
  refSession?: number;
  refLap?: number;
}

export function CompareView(props: Props) {
  const state = useAsync(() => api.compare(props), []);
  return (
    <>
      <a className="back" href={href({ page: "session", id: props.session })}>
        ← Vueltas de la sesión {props.session}
      </a>
      <Status state={state}>{(c) => <ComparisonPanel c={c} />}</Status>
    </>
  );
}

// Module constants so re-renders (e.g. moving the cursor) never rebuild the charts.
const PERCENT_RANGE: [number, number] = [0, 100];
const formatDelta = (v: number) => signed(v, 2);

function color(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function ComparisonPanel({ c }: { c: Comparison }) {
  const [selected, setSelected] = useState<number | null>(null);
  const [cursor, setCursor] = useState<number | null>(null);
  const total = c.delta_s[c.delta_s.length - 1] ?? 0;
  const sameSession = c.target.session_id === c.reference.session_id;
  const refName = `vuelta ${c.reference.lap}${sameSession ? "" : ` (sesión ${c.reference.session_id})`}`;
  const losses = c.segments
    .map((s, i) => ({ ...s, n: i + 1 }))
    .filter((s) => s.delta_s > 0)
    .sort((a, b) => b.delta_s - a.delta_s)
    .slice(0, 3);
  const zoom = useMemo<[number, number] | null>(() => {
    if (selected === null) return null;
    const s = c.segments[selected];
    return [s.start_m, s.end_m];
  }, [selected, c.segments]);
  const hasMap = c.track_x.some((v, i) => v !== c.track_x[0] || c.track_z[i] !== c.track_z[0]);

  const charts = useMemo(() => {
    const target = color("--series-target");
    const reference = color("--series-ref");
    const t = c.target_channels;
    const r = c.reference_channels;
    const pct = (values: number[]) => values.map((v) => v * 100);
    // Sequential gearboxes pass through neutral for a moment on every shift; hide those blips.
    const gears = (values: number[], speed: number[]) => {
      const out: number[] = [];
      values.forEach((g, i) => out.push(g === 0 && i > 0 && speed[i] > 20 ? out[i - 1] : g));
      return out;
    };
    const these = `Vuelta ${c.target.lap}`;
    const ref = `Vuelta ${c.reference.lap}`;
    return {
      delta: [{ label: "Delta", values: c.delta_s, color: color("--series-delta"), width: 2 }] as Series[],
      speed: [
        { label: these, values: t.speed_kmh, color: target },
        { label: ref, values: r.speed_kmh, color: reference, dash: [4, 3] },
      ] as Series[],
      pedals: [
        { label: `Acel. ${c.target.lap}`, values: pct(t.throttle), color: color("--series-throttle") },
        { label: `Acel. ${c.reference.lap}`, values: pct(r.throttle), color: color("--series-throttle"), dash: [4, 3] },
        { label: `Freno ${c.target.lap}`, values: pct(t.brake), color: color("--series-brake") },
        { label: `Freno ${c.reference.lap}`, values: pct(r.brake), color: color("--series-brake"), dash: [4, 3] },
      ] as Series[],
      gear: [
        { label: these, values: gears(t.gear, t.speed_kmh), color: target, stepped: true },
        { label: ref, values: gears(r.gear, r.speed_kmh), color: reference, dash: [4, 3], stepped: true },
      ] as Series[],
    };
  }, [c]);

  return (
    <>
      <h1>
        Vuelta {c.target.lap} <span className="muted">contra</span> {refName}
      </h1>
      <div className="summary">
        <div className="stat">
          <span className="stat-label">Esta vuelta</span>
          <span className="stat-value">{lapTime(c.target.time_ms)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Referencia</span>
          <span className="stat-value">{lapTime(c.reference.time_ms)}</span>
        </div>
        <div className={`stat ${total > 0 ? "lose" : "gain"}`}>
          <span className="stat-label">Diferencia</span>
          <span className="stat-value">{signed(total)} s</span>
        </div>
      </div>
      {c.partial && (
        <p className="notice">
          Una de las vueltas no se grabó desde la meta (por ejemplo, salida de boxes). Solo se compara de{" "}
          {Math.round(c.distance_m[0])} a {Math.round(c.distance_m[c.distance_m.length - 1])} m.
        </p>
      )}
      {losses.length > 0 && (
        <section>
          <h2>Dónde pierdes más tiempo</h2>
          <ol className="losses">
            {losses.map((s) => (
              <li key={s.n}>
                <button className="link" onClick={() => setSelected(s.n - 1)}>
                  <strong>
                    T{s.n} · {Math.round(s.start_m)}–{Math.round(s.end_m)} m
                  </strong>
                </button>
                : {signed(s.delta_s)} s · vel. mínima {Math.round(s.target_min_speed_kmh)} vs{" "}
                {Math.round(s.reference_min_speed_kmh)} km/h
              </li>
            ))}
          </ol>
        </section>
      )}
      <div className="analysis">
      <aside className="tramos">
        <h2>Por tramos</h2>
        <div>
          {hasMap && (
            <TrackMap
              x={c.track_x}
              z={c.track_z}
              segments={c.segments}
              selected={selected}
              onSelect={setSelected}
              cursor={cursor}
            />
          )}
          <div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Tramo</th>
                    <th className="num">Delta</th>
                    <th className="num">Vel. mín</th>
                    <th className="num">Vel. media</th>
                  </tr>
                </thead>
                <tbody>
                  {c.segments.map((s, i) => (
                    <tr
                      key={i}
                      className={`clickable${selected === i ? " selected" : ""}`}
                      onClick={() => setSelected(selected === i ? null : i)}
                    >
                      <td>
                        <span className={`seg-dot ${segmentTone(s.delta_s)}`} />T{i + 1}{" "}
                        <span className="muted small">
                          {Math.round(s.start_m)}–{Math.round(s.end_m)} m
                        </span>
                      </td>
                      <td className={`num ${segmentTone(s.delta_s) === "even" ? "" : segmentTone(s.delta_s)}`}>
                        {signed(s.delta_s)} s
                      </td>
                      <td className="num">
                        {Math.round(s.target_min_speed_kmh)} / {Math.round(s.reference_min_speed_kmh)}
                      </td>
                      <td className="num">
                        {Math.round(s.target_avg_speed_kmh)} / {Math.round(s.reference_avg_speed_kmh)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted small">Velocidades en km/h: esta vuelta / referencia.</p>
          </div>
        </div>
      </aside>
      <section className="charts">
        <h2>
          Metro a metro
          {selected !== null && (
            <>
              {" "}
              <span className="muted">· T{selected + 1}</span>{" "}
              <button className="chip" onClick={() => setSelected(null)}>
                ver vuelta completa
              </button>
            </>
          )}
        </h2>
        <Chart
          title="Delta (s) · por encima de 0 pierdes tiempo"
          x={c.distance_m}
          series={charts.delta}
          zeroLine
          format={formatDelta}
          syncKey="cmp"
          onCursor={setCursor}
          xRange={zoom}
          height={160}
        />
        <Chart title="Velocidad (km/h)" x={c.distance_m} series={charts.speed} syncKey="cmp"
          onCursor={setCursor}
          xRange={zoom} height={200} />
        <Chart
          title="Acelerador y freno (%)"
          x={c.distance_m}
          series={charts.pedals}
          yRange={PERCENT_RANGE}
          syncKey="cmp"
          onCursor={setCursor}
          xRange={zoom}
          height={150}
        />
        <Chart title="Marcha" x={c.distance_m} series={charts.gear} syncKey="cmp"
          onCursor={setCursor}
          xRange={zoom} height={110} />
      </section>
      </div>
    </>
  );
}
