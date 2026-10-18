import { useEffect, useRef } from "react";
import uPlot from "uplot";

export interface Series {
  label: string;
  values: number[];
  color: string;
  width?: number;
  dash?: number[];
  stepped?: boolean;
}

interface Props {
  title: string;
  x: number[];
  series: Series[];
  height?: number;
  yRange?: [number, number];
  zeroLine?: boolean;
  format?: (value: number) => string;
  syncKey: string;
  /** Called with the grid index under the cursor, or null when it leaves. */
  onCursor?: (index: number | null) => void;
  /** Zoom to this distance range; null shows the whole lap. */
  xRange?: [number, number] | null;
}

/** A distance-based line chart; charts with the same syncKey share the cursor. */
export function Chart({ title, x, series, height = 180, yRange, zeroLine, format, syncKey, onCursor, xRange }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const plotRef = useRef<uPlot | null>(null);
  // Kept in a ref so a new callback does not rebuild the chart.
  const cursorCallback = useRef(onCursor);
  cursorCallback.current = onCursor;

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const css = getComputedStyle(document.documentElement);
    const axis = css.getPropertyValue("--muted").trim();
    const grid = css.getPropertyValue("--grid").trim();
    const fmt = format ?? ((v: number) => v.toFixed(0));
    const options: uPlot.Options = {
      width: el.clientWidth,
      height,
      cursor: { sync: { key: syncKey }, drag: { x: true, y: false } },
      legend: { live: true },
      scales: { x: { time: false }, y: yRange ? { range: yRange } : {} },
      axes: [
        {
          stroke: axis,
          grid: { stroke: grid },
          ticks: { stroke: grid },
          values: (_u, ticks) => ticks.map((t) => `${Math.round(t)} m`),
        },
        {
          stroke: axis,
          grid: { stroke: grid },
          ticks: { stroke: grid },
          size: 52,
          values: (_u, ticks) => ticks.map(fmt),
        },
      ],
      series: [
        { label: "Distancia", value: (_u, v) => (v == null ? "—" : `${Math.round(v)} m`) },
        ...series.map((s) => ({
          label: s.label,
          stroke: s.color,
          width: s.width ?? 1.5,
          dash: s.dash,
          paths: s.stepped ? uPlot.paths.stepped!({ align: 1 }) : undefined,
          value: (_u: uPlot, v: number | null) => (v == null ? "—" : fmt(v)),
        })),
      ],
      hooks: {
        setCursor: [(u: uPlot) => cursorCallback.current?.(u.cursor.idx ?? null)],
        ...(zeroLine
        ? {
            drawClear: [
              (u: uPlot) => {
                const y = u.valToPos(0, "y", true);
                const ctx = u.ctx;
                ctx.save();
                ctx.strokeStyle = axis;
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(u.bbox.left, y);
                ctx.lineTo(u.bbox.left + u.bbox.width, y);
                ctx.stroke();
                ctx.restore();
              },
            ],
          }
        : {}),
      },
    };
    const plot = new uPlot(options, [x, ...series.map((s) => s.values)], el);
    plotRef.current = plot;
    const resize = new ResizeObserver(() => plot.setSize({ width: el.clientWidth, height }));
    resize.observe(el);
    return () => {
      resize.disconnect();
      plot.destroy();
      plotRef.current = null;
    };
  }, [x, series, height, yRange, zeroLine, format, syncKey]);

  useEffect(() => {
    const plot = plotRef.current;
    if (!plot || x.length === 0) return;
    const [min, max] = xRange ?? [x[0], x[x.length - 1]];
    plot.setScale("x", { min, max });
  }, [xRange, x]);

  return (
    <figure className="chart">
      <figcaption>{title}</figcaption>
      <div ref={host} />
    </figure>
  );
}
