/** Small outline of a track, for cards. */
export function TrackThumb({ x, z, size = 96 }: { x: number[]; z: number[]; size?: number }) {
  if (x.length < 2) return <div className="thumb empty" style={{ width: size, height: size }} />;
  const minX = Math.min(...x);
  const maxX = Math.max(...x);
  const minZ = Math.min(...z);
  const maxZ = Math.max(...z);
  const span = Math.max(maxX - minX, maxZ - minZ, 1);
  const pad = span * 0.08;
  const points = x.map((v, i) => `${(v - minX).toFixed(1)},${(z[i] - minZ).toFixed(1)}`).join(" ");
  return (
    <svg
      className="thumb"
      width={size}
      height={size}
      viewBox={`${-pad} ${-pad} ${maxX - minX + 2 * pad} ${maxZ - minZ + 2 * pad}`}
      aria-hidden="true"
    >
      <polyline points={points} strokeWidth={span * 0.035} />
    </svg>
  );
}
