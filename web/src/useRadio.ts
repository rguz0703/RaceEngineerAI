import { useCallback, useEffect, useRef, useState } from "react";
import type { RadioCall } from "./useLive";

export type RadioKind = "sector" | "lap" | "tip" | "incident";

export const RADIO_KINDS: { kind: RadioKind; label: string; hint: string }[] = [
  { kind: "lap", label: "Tiempo de vuelta", hint: "Al cruzar la meta, y si es tu mejor vuelta" },
  { kind: "sector", label: "Sectores", hint: "Cuánto ganas o pierdes en cada tercio de la vuelta" },
  { kind: "tip", label: "Consejo", hint: "Dónde perdiste más tiempo y por qué" },
  { kind: "incident", label: "Incidentes", hint: "Salidas de pista, bloqueos y patinadas" },
];

export interface RadioPrefs {
  kinds: Record<RadioKind, boolean>;
  voice: string;
  /** Speaking speed; 1 is the voice's normal pace. */
  rate: number;
}

const DEFAULTS: RadioPrefs = {
  kinds: { lap: true, sector: true, tip: true, incident: true },
  voice: "",
  rate: 1.1,
};
const KEY = "raceengineer.radio";
/** More calls than this waiting means the driver is being talked over: drop the oldest. */
const MAX_QUEUE = 3;

function loadPrefs(): RadioPrefs {
  try {
    const saved = JSON.parse(window.localStorage.getItem(KEY) ?? "{}") as Partial<RadioPrefs>;
    return { ...DEFAULTS, ...saved, kinds: { ...DEFAULTS.kinds, ...saved.kinds } };
  } catch {
    return DEFAULTS;
  }
}

function savePrefs(prefs: RadioPrefs) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    // Private mode or blocked storage: the settings just won't be remembered.
  }
}

function kindOf(call: RadioCall): RadioKind {
  return call.kind === "best_lap" ? "lap" : (call.kind as RadioKind);
}

export const speechAvailable = typeof window !== "undefined" && "speechSynthesis" in window;

/** Spanish voices first (Mexico, then Latin America, then Spain), then the rest. */
function rankVoices(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice[] {
  const score = (v: SpeechSynthesisVoice) => {
    const lang = v.lang.toLowerCase();
    if (lang === "es-mx") return 0;
    if (lang === "es-us" || lang === "es-419") return 1;
    if (lang.startsWith("es")) return 2;
    return 3;
  };
  return voices.filter((v) => score(v) < 3).sort((a, b) => score(a) - score(b));
}

export interface Radio {
  available: boolean;
  /** The browser only lets a page talk after a tap, so the radio starts off on each visit. */
  on: boolean;
  prefs: RadioPrefs;
  voices: SpeechSynthesisVoice[];
  turnOn: () => void;
  turnOff: () => void;
  test: () => void;
  setPrefs: (prefs: RadioPrefs) => void;
}

/** Reads the engineer's calls aloud with the browser's own voice. */
export function useRadio(calls: RadioCall[]): Radio {
  const [on, setOn] = useState(false);
  const [prefs, setPrefsState] = useState<RadioPrefs>(loadPrefs);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const spoken = useRef<number | null>(null);
  const queue = useRef<SpeechSynthesisUtterance[]>([]);

  useEffect(() => {
    if (!speechAvailable) return;
    const update = () => setVoices(rankVoices(window.speechSynthesis.getVoices()));
    update();
    window.speechSynthesis.addEventListener("voiceschanged", update);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", update);
  }, []);

  const say = useCallback(
    (text: string) => {
      if (!speechAvailable) return;
      const utterance = new SpeechSynthesisUtterance(text);
      const voice = voices.find((v) => v.voiceURI === prefs.voice) ?? voices[0];
      if (voice) utterance.voice = voice;
      utterance.lang = voice?.lang ?? "es-MX";
      utterance.rate = prefs.rate;
      const done = () => {
        queue.current = queue.current.filter((u) => u !== utterance);
      };
      utterance.onend = done;
      utterance.onerror = done;
      queue.current.push(utterance);
      if (queue.current.length > MAX_QUEUE) {
        // Cancelling drops everything queued; put back only the newest calls.
        const keep = queue.current.slice(-MAX_QUEUE + 1);
        window.speechSynthesis.cancel();
        queue.current = [];
        for (const u of keep) {
          queue.current.push(u);
          window.speechSynthesis.speak(u);
        }
        return;
      }
      window.speechSynthesis.speak(utterance);
    },
    [voices, prefs.voice, prefs.rate],
  );

  // Speak each new call once. Calls already there when the radio was turned on stay quiet.
  useEffect(() => {
    if (!on) return;
    const newest = calls.length ? calls[calls.length - 1].id : 0;
    if (spoken.current === null || newest < spoken.current) {
      // First frame after turning on, or the recording restarted and ids began again.
      spoken.current = newest;
      return;
    }
    for (const call of calls) {
      if (call.id <= spoken.current) continue;
      spoken.current = call.id;
      if (prefs.kinds[kindOf(call)]) say(call.speech);
    }
  }, [calls, on, prefs.kinds, say]);

  const turnOn = useCallback(() => {
    spoken.current = null;
    setOn(true);
    // Speaking inside the tap is what unlocks the voice on phones.
    say("Radio lista.");
  }, [say]);

  const turnOff = useCallback(() => {
    setOn(false);
    queue.current = [];
    if (speechAvailable) window.speechSynthesis.cancel();
  }, []);

  const setPrefs = useCallback((next: RadioPrefs) => {
    setPrefsState(next);
    savePrefs(next);
  }, []);

  const test = useCallback(() => say("Sector dos, 2 décimas más rápido."), [say]);

  return { available: speechAvailable, on, prefs, voices, turnOn, turnOff, test, setPrefs };
}
