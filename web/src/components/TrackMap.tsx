import { useMemo } from "react";
import type { Segment } from "../api";
import { signed } from "../format";

interface Props {
  x: number[];
  z: number[];
  segments: Segment[];
  selected: number | null;
  onSelect: (index: number | null) => void;
  cursor: number | null;
  /** Segments with warnings get a marked label. */
  flagged?: Set<number>;
}

const NEUTRAL_S = 0.02;

export function segmentTone(delta: number): "gain" | "lose" | "even" {
  if (delta > NEUTRAL_S) return "lose";
  if (delta < -NEUTRAL_S) return "gain";
  return "even";
}

/** The reference lap's path, colored by where time is gained or lost. */
export function TrackMap({ x, z, segments, selected, onSelect, cursor, flagged }: Props) {
  const geometry = useMemo(() => {
    const minX = Math.min(...x);
    const maxX = Math.max(...x);
    const minZ = Math.min(...z);
    const maxZ = Math.max(...z);
    const span = Math.max(maxX - minX, maxZ - minZ, 1);
    const pad = span * 0.08;
    const stroke = span * 0.014;
    const point = (i: number) => `${(x[i] - minX).toFixed(1)},${(z[i] - minZ).toFixed(1)}`;
    const paths = segments.map((s) => {
      const pts: string[] = [];
      for (let i = s.start_index; i <= s.end_index; i++) pts.push(point(i));
      return pts.join(" ");
    });
    const labels = segments.map((s) => {
      const mid = Math.round((s.start_index + s.end_index) / 2);
      // Push the label off the line, perpendicular to the direction of travel.
      const a = Math.max(0, mid - 3);
      const b = Math.min(x.length - 1, mid + 3);
      const dx = x[b] - x[a];
      const dz = z[b] - z[a];
      const len = Math.hypot(dx, dz) || 1;
      const off = stroke * 3.2;
      return { x: x[mid] - minX - (dz / len) * off, z: z[mid] - minZ + (dx / len) * off };
    });
    // A short bar across the track at the start/finish line.
    const sx = x[0] - minX;
    const sz = z[0] - minZ;
    const k = Math.min(5, x.length - 1);
    const hx = x[k] - x[0];
    const hz = z[k] - z[0];
    const hl = Math.hypot(hx, hz) || 1;
    const bar = stroke * 2.2;
    const finish = {
      x1: sx - (hz / hl) * bar,
      y1: sz + (hx / hl) * bar,
      x2: sx + (hz / hl) * bar,
      y2: sz - (hx / hl) * bar,
    };
    const maxAbs = Math.max(...segments.map((s) => Math.abs(s.delta_s)), NEUTRAL_S);
    return {
      viewBox: `${-pad} ${-pad} ${maxX - minX + 2 * pad} ${maxZ - minZ + 2 * pad}`,
      stroke,
      paths,
      labels,
      finish,
      maxAbs,
      origin: [minX, minZ] as const,
      outline: x.map((_, i) => point(i)).join(" "),
    };
  }, [x, z, segments]);

  const dot =
    cursor !== null && cursor >= 0 && cursor < x.length
      ? { cx: x[cursor] - geometry.origin[0], cy: z[cursor] - geometry.origin[1] }
      : null;

  return (
    <figure className="track-map">
      <svg
        viewBox={geometry.viewBox}
        role="img"
        aria-label="Mapa del circuito coloreado por tramos"
        onClick={() => onSelect(null)}
      >
        <polyline className="track-outline" points={geometry.outline} strokeWidth={geometry.stroke * 2.4} />
        {segments.map((s, i) => {
          const tone = segmentTone(s.delta_s);
          const strength = 0.45 + 0.55 * Math.min(1, Math.abs(s.delta_s) / geometry.maxAbs);
          const dim = selected !== null && selected !== i;
          return (
            <polyline
              key={i}
              className={`track-seg ${tone}${selected === i ? " selected" : ""}`}
              points={geometry.paths[i]}
              strokeWidth={geometry.stroke * (selected === i ? 1.7 : 1)}
              strokeOpacity={dim ? 0.25 : tone === "even" ? 0.9 : strength}
              onClick={(e) => {
                e.stopPropagation();
                onSelect(selected === i ? null : i);
              }}
            >
              <title>
                T{i + 1}: {signed(s.delta_s)} s
              </title>
            </polyline>
          );
        })}
        <line className="track-finish" {...geometry.finish} strokeWidth={geometry.stroke * 0.6} />
        {geometry.labels.map((p, i) => (
          <g
            key={i}
            className={`track-label${selected === i ? " selected" : ""}${flagged?.has(i) ? " flagged" : ""}`}
            transform={`translate(${p.x} ${p.z})`}
            onClick={(e) => {
              e.stopPropagation();
              onSelect(selected === i ? null : i);
            }}
          >
            <circle r={geometry.stroke * 1.9} />
            <text fontSize={geometry.stroke * 2} dy="0.35em">
              {i + 1}
            </text>
          </g>
        ))}
        {dot && <circle className="track-dot" cx={dot.cx} cy={dot.cy} r={geometry.stroke * 1.3} />}
      </svg>
      <figcaption className="map-legend">
        <span className="swatch gain" /> ganas <span className="swatch lose" /> pierdes{" "}
        <span className="swatch even" /> igual · toca un tramo para resaltarlo
      </figcaption>
    </figure>
  );
}
