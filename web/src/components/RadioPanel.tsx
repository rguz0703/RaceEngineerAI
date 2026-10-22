import { useState } from "react";
import type { RadioCall } from "../useLive";
import { RADIO_KINDS, type Radio } from "../useRadio";

/** Turns the engineer's voice on and off, picks what it talks about, and lists what it said. */
export function RadioPanel({ radio, calls }: { radio: Radio; calls: RadioCall[] }) {
  const [open, setOpen] = useState(false);
  const { prefs } = radio;
  if (!radio.available) {
    return (
      <section className="panel radio">
        <span className="label">Ingeniero por radio</span>
        <p className="muted small">Este navegador no puede hablar. Prueba con Chrome, Edge o Safari.</p>
      </section>
    );
  }
  return (
    <section className={`panel radio ${radio.on ? "on" : ""}`}>
      <div className="radio-head">
        <button className={`radio-toggle ${radio.on ? "on" : ""}`} onClick={radio.on ? radio.turnOff : radio.turnOn}>
          <span aria-hidden="true">{radio.on ? "🔊" : "🔇"}</span>
          {radio.on ? "Radio activada" : "Activar radio del ingeniero"}
        </button>
        <button className="chip" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "Cerrar ajustes" : "Ajustes"}
        </button>
      </div>
      {!radio.on && (
        <p className="muted small">
          Te dice por voz los tiempos de vuelta, los sectores y dónde pierdes tiempo. Ponte los audífonos en el
          aparato donde tengas abierta esta página.
        </p>
      )}

      {open && (
        <div className="radio-settings">
          <fieldset>
            <legend className="label">Qué te dice</legend>
            {RADIO_KINDS.map(({ kind, label, hint }) => (
              <label key={kind} className="radio-option">
                <input
                  type="checkbox"
                  checked={prefs.kinds[kind]}
                  onChange={(e) => radio.setPrefs({ ...prefs, kinds: { ...prefs.kinds, [kind]: e.target.checked } })}
                />
                <span>
                  {label}
                  <span className="muted small"> · {hint}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <label className="radio-field">
            <span className="label">Voz</span>
            <select value={prefs.voice} onChange={(e) => radio.setPrefs({ ...prefs, voice: e.target.value })}>
              <option value="">Automática (español)</option>
              {radio.voices.map((v) => (
                <option key={v.voiceURI} value={v.voiceURI}>
                  {v.name} ({v.lang})
                </option>
              ))}
            </select>
          </label>
          <label className="radio-field">
            <span className="label">Velocidad</span>
            <input
              type="range"
              min={0.8}
              max={1.6}
              step={0.1}
              value={prefs.rate}
              onChange={(e) => radio.setPrefs({ ...prefs, rate: Number(e.target.value) })}
            />
            <span className="mono small">{prefs.rate.toFixed(1)}×</span>
          </label>
          <button className="button" onClick={radio.test}>
            Probar voz
          </button>
        </div>
      )}

      {calls.length > 0 && (
        <ul className="radio-log">
          {[...calls].reverse().map((c) => (
            <li key={c.id} className={c.kind}>
              <span className="mono muted">V{c.lap}</span> {c.text}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
