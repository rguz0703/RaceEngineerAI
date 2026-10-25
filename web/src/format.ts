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

/** "ks_porsche_911_gt3_cup_2017" -> "Porsche 911 GT3 Cup 2017"; "layout_gp" -> "GP". */
export function prettyName(id: string): string {
  return id
    .replace(/^ks_/, "")
    .replace(/^layout_/, "")
    .split("_")
    .filter(Boolean)
    .map((word) =>
      (/\d/.test(word) && /[a-z]/i.test(word)) || word.length <= 2
        ? word.toUpperCase()
        : word[0].toUpperCase() + word.slice(1),
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

/** 33219 -> "33.219"; sectors over a minute keep the minutes. */
export function sectorTime(ms: number): string {
  return ms >= 60000 ? lapTime(ms) : (ms / 1000).toFixed(3);
}

export type SectorTone = "best" | "gain" | "lose";

function cleanWithSectors(lap: Lap): boolean {
  return lap.time_ms !== null && lap.complete && !lap.off_track && !lap.out_lap && !lap.in_lap && lap.sector_ms.length === 3;
}

/**
 * Timing-screen colours for each clean lap's sectors, in the order they were driven:
 * purple = best of the session, green = improved your best so far, yellow = slower.
 */
export function sectorTones(laps: Lap[], best: number[]): Map<number, SectorTone[]> {
  const tones = new Map<number, SectorTone[]>();
  const sofar = [Infinity, Infinity, Infinity];
  for (const lap of laps) {
    if (!cleanWithSectors(lap)) continue;
    tones.set(
      lap.number,
      lap.sector_ms.map((t, k) => {
        let tone: SectorTone = "lose";
        if (t < sofar[k]) {
          tone = "gain";
          sofar[k] = t;
        }
        return t === best[k] ? "best" : tone;
      }),
    );
  }
  return tones;
}
