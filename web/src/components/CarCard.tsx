import type { Car, Tyre } from "../api";

const WHEEL_ORDER: Tyre["wheel"][] = ["fl", "fr", "rl", "rr"];
const WHEEL_LABEL: Record<Tyre["wheel"], string> = {
  fl: "Del. izq.",
  fr: "Del. der.",
  rl: "Tras. izq.",
  rr: "Tras. der.",
};

/** Cold blue to hot red; fixed scale so laps and sessions compare at a glance. */
function tempColor(c: number): string {
  const t = Math.min(1, Math.max(0, (c - 40) / 70));
  return `hsl(${Math.round(220 - 220 * t)} 65% 40%)`;
}

function TyreBox({ tyre, other }: { tyre: Tyre; other?: Tyre }) {
  // Edges in the order AC names them (I, M, O). Which physical side "I" is has not
  // been confirmed yet, so the strip is not mirrored for left wheels.
  const temps = [tyre.temp_inner_c, tyre.temp_middle_c, tyre.temp_outer_c];
  const dp = other ? tyre.pressure_psi - other.pressure_psi : 0;
  return (
    <div className="tyre">
      <div className="tyre-label">{WHEEL_LABEL[tyre.wheel]}</div>
      <div className="tyre-strip" title="Temperatura I / M / O según AC">
        {temps.map((c, i) => (
          <span key={i} style={{ background: tempColor(c) }}>
            {Math.round(c)}°
          </span>
        ))}
      </div>
      <div className="tyre-pressure">
        {tyre.pressure_psi.toFixed(1)} psi
        {Math.abs(dp) >= 0.3 && <span className={dp > 0 ? "up" : "down"}> {dp > 0 ? "▲" : "▼"}{Math.abs(dp).toFixed(1)}</span>}
      </div>
    </div>
  );
}

function Tyres({ car, other }: { car: Car; other: Car | null }) {
  const byWheel = (c: Car | null, w: Tyre["wheel"]) => c?.tyres.find((t) => t.wheel === w);
  return (
    <div className="tyres">
      {WHEEL_ORDER.map((w) => (
        <TyreBox key={w} tyre={byWheel(car, w)!} other={byWheel(other, w)} />
      ))}
    </div>
  );
}

interface Row {
  label: string;
  target: string;
  reference: string;
}

function rows(t: Car, r: Car | null): Row[] {
  const pct = (v: number) => `${(v * 100).toFixed(1)} %`;
  const num = (v: number, d = 2) => v.toFixed(d);
  const fuel = (c: Car) =>
    c.fuel_start_l === c.fuel_end_l ? `${num(c.fuel_start_l, 1)} L` : `${num(c.fuel_start_l, 1)} → ${num(c.fuel_end_l, 1)} L`;
  const v = (f: (c: Car) => string) => ({ target: f(t), reference: r ? f(r) : "—" });
  return [
    { label: "Compuesto", ...v((c) => c.tyre_compound || "—") },
    { label: "Reparto de frenada", ...v((c) => pct(c.brake_bias)) },
    { label: "Control de tracción", ...v((c) => (c.tc === 0 ? "apagado" : num(c.tc))) },
    { label: "ABS", ...v((c) => (c.abs === 0 ? "apagado" : num(c.abs))) },
    { label: "Freno motor", ...v((c) => String(c.engine_brake)) },
    { label: "Combustible", ...v(fuel) },
  ];
}

export function CarCard({ target, reference, targetLap, referenceLap, hints }: {
  target: Car | null;
  reference: Car | null;
  targetLap: number;
  referenceLap: number;
  hints: string[];
}) {
  if (!target) {
    return (
      <p className="muted">
        Esta vuelta se grabó antes de guardar el estado del coche. Graba una sesión nueva para ver presiones y
        temperaturas.
      </p>
    );
  }
  return (
    <div className="car-card">
      <div className="car-tyres">
        <div>
          <h3>Vuelta {targetLap}</h3>
          <Tyres car={target} other={reference} />
        </div>
        {reference && (
          <div>
            <h3>Vuelta {referenceLap}</h3>
            <Tyres car={reference} other={null} />
          </div>
        )}
      </div>
      {hints.length > 0 && (
        <ul className="note-list hints">
          {hints.map((h) => (
            <li key={h}>
              <span className="note-topic">neumáticos</span> {h}
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">
        Promedios en pista. Cada llanta muestra la temperatura en tres zonas (I · M · O, como las nombra el juego)
        y la presión; ▲▼ = diferencia con la referencia. Aún falta confirmar qué borde es el interior.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th />
              <th className="num">Vuelta {targetLap}</th>
              <th className="num">Vuelta {referenceLap}</th>
            </tr>
          </thead>
          <tbody>
            {rows(target, reference).map((row) => (
              <tr key={row.label} className={reference && row.target !== row.reference ? "changed" : undefined}>
                <td>{row.label}</td>
                <td className="num">{row.target}</td>
                <td className="num">{row.reference}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
