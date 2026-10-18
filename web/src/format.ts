import type { Lap } from "./api";

export function lapTime(ms: number | null): string {
  if (ms === null) return "—";
  const minutes = Math.floor(ms / 60000);
  const seconds = (ms % 60000) / 1000;
  return `${minutes}:${seconds.toFixed(3).padStart(6, "0")}`;
}

export function signed(seconds: number, digits = 3): string {
  const text = Math.abs(seconds).toFixed(digits);
  return seconds > 0 ? `+${text}` : seconds < 0 ? `−${text}` : text;
}

export function lapKind(lap: Lap): string {
  if (lap.time_ms === null) return "Sin terminar";
  const kinds = [lap.out_lap && "Salida", lap.in_lap && "Entrada"].filter(Boolean);
  if (kinds.length) return kinds.join(" + ");
  return lap.complete ? "Lanzada" : "Incompleta";
}

/** "ks_porsche_911_gt3_cup_2017" -> "Porsche 911 GT3 Cup 2017". */
export function prettyName(id: string): string {
  return id
    .replace(/^ks_/, "")
    .split("_")
    .filter(Boolean)
    .map((word) =>
      /\d/.test(word) && /[a-z]/i.test(word) ? word.toUpperCase() : word[0].toUpperCase() + word.slice(1),
    )
    .join(" ");
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString("es", { dateStyle: "medium", timeStyle: "short" });
}

const SIM_NAMES: Record<string, string> = {
  assetto_corsa: "Assetto Corsa",
  fake: "Simulación de prueba",
};

export function simName(sim: string): string {
  return SIM_NAMES[sim] ?? prettyName(sim);
}
