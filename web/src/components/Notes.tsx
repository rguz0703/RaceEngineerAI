import { useState } from "react";
import type { Note, Segment } from "../api";

interface Props {
  notes: Note[];
  segments: Segment[];
  selected: number | null;
  onSelect: (segment: number) => void;
}

const FIRST_GROUPS = 3;

/** The engineer's notes: lap-wide first, then by segment. */
export function Notes({ notes, segments, selected, onSelect }: Props) {
  const [showAll, setShowAll] = useState(false);
  if (notes.length === 0) {
    return <p className="muted">Sin observaciones: no hay diferencias claras que expliquen la pérdida.</p>;
  }
  const lap = notes.filter((n) => n.segment === null);
  const bySegment = new Map<number, Note[]>();
  for (const n of notes) {
    if (n.segment === null) continue;
    bySegment.set(n.segment, [...(bySegment.get(n.segment) ?? []), n]);
  }
  // Segments that cost the most time first.
  const ordered = [...bySegment.keys()].sort((a, b) => segments[b].delta_s - segments[a].delta_s);
  const visible =
    selected !== null && bySegment.has(selected)
      ? [selected]
      : showAll
        ? ordered
        : ordered.slice(0, FIRST_GROUPS);
  return (
    <div className="notes">
      {lap.length > 0 && (
        <ul className="note-list">
          {lap.map((n, i) => (
            <li key={i} className={n.severity}>
              <span className="note-topic">{n.topic}</span> {n.text}
            </li>
          ))}
        </ul>
      )}
      {visible.map((segment) => (
        <div key={segment} className="note-group">
          <button className={`seg-chip${selected === segment ? " selected" : ""}`} onClick={() => onSelect(segment)}>
            T{segment + 1}
          </button>
          <ul className="note-list">
            {bySegment.get(segment)!.map((n, i) => (
              <li key={i} className={n.severity}>
                <span className="note-topic">{n.topic}</span> {n.text}
              </li>
            ))}
          </ul>
        </div>
      ))}
      {selected === null && !showAll && ordered.length > FIRST_GROUPS && (
        <button className="chip more" onClick={() => setShowAll(true)}>
          ver las notas de {ordered.length - FIRST_GROUPS} tramos más
        </button>
      )}
      {selected !== null && !bySegment.has(selected) && (
        <p className="muted small">Sin observaciones en T{selected + 1}.</p>
      )}
      <p className="muted small">
        Son sugerencias calculadas con reglas: con pocas vueltas, un error de manejo y un problema de reglaje
        pueden parecerse.
      </p>
    </div>
  );
}
