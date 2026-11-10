import { BRAND } from "../lib/brand.js";

// Pixel-grid mark: a chip with pins (industrial) built from squares, after the SHPE 2026 pixel style.
// 1 = outline, 2 = fill, 3 = core.
const GRID = [
  "0101010",
  "1111111",
  "0122210",
  "1123211",
  "0122210",
  "1111111",
  "0101010",
];
const FILL = { 1: "var(--mark-line)", 2: "var(--mark-fill)", 3: "var(--mark-core)" };

export function PixelMark({ size = 28 }) {
  return (
    <svg className="pixel-mark" width={size} height={size} viewBox="0 0 7 7" aria-hidden="true" shapeRendering="crispEdges">
      {GRID.flatMap((row, y) =>
        [...row].map((v, x) => (v === "0" ? null : <rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" fill={FILL[v]} />))
      )}
    </svg>
  );
}

export default function Wordmark({ withLong = false }) {
  return (
    <span className="wordmark">
      <PixelMark />
      <span className="wordmark-text">
        <span className="wordmark-name">{BRAND.name}</span>
        {withLong && <span className="wordmark-long">{BRAND.long}</span>}
      </span>
    </span>
  );
}
