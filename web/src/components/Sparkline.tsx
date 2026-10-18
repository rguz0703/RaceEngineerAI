/** Tiny line of lap times (lower is better, so the chart is flipped: up = faster). */
export function Sparkline({ values, width = 120, height = 32 }: { values: number[]; width?: number; height?: number }) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 3;
  const points = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * (width - 2 * pad);
    const y = pad + ((v - min) / span) * (height - 2 * pad);
    return [x, y] as const;
  });
  const last = points[points.length - 1];
  const improving = values[values.length - 1] <= values[0];
  return (
    <svg className={`spark ${improving ? "gain" : "lose"}`} width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <polyline points={points.map(([x, y]) => `${x},${y}`).join(" ")} />
      <circle cx={last[0]} cy={last[1]} r={2.5} />
    </svg>
  );
}
