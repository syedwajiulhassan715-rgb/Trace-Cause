import { useState } from "react";
import { formatTime, niceMax, type Point, segments, type SignalKey } from "./model";

const W = 320;
const H = 112;
const PAD = { left: 40, right: 8, top: 8, bottom: 20 };
const WINDOW_S = 10;

function fmt(signal: SignalKey, v: number): string {
  return signal === "own_error_rate" ? `${v.toFixed(1)} %` : `${v.toFixed(1)} ms`;
}

function tick(signal: SignalKey, v: number): string {
  const n = Number.isInteger(v) ? String(v) : v.toFixed(1);
  return signal === "own_error_rate" ? `${n} %` : `${n} ms`;
}

type Props = {
  title: string;
  signal: SignalKey;
  points: Point[];
  alerts: Set<number>;
  domain: [number, number];
};

/** One series, one axis: a 2px line with a light wash, alert windows shaded behind it. */
export function Chart({ title, signal, points, alerts, domain }: Props) {
  const [hover, setHover] = useState<Point | null>(null);
  const [t0, t1] = domain;
  const yMax = niceMax(Math.max(0, ...points.map((p) => p.v)));
  const x = (t: number) => PAD.left + ((t - t0) / Math.max(1, t1 - t0)) * (W - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - v / yMax) * (H - PAD.top - PAD.bottom);
  // Plot each window at its middle; missing windows break the line.
  const base = y(0);
  const parts = segments(points, WINDOW_S).map((seg) => {
    const xy = seg.map((p) => [x(p.t + WINDOW_S / 2), y(p.v)] as const);
    const d = xy.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join("");
    return { line: d, area: `${d}L${xy[xy.length - 1][0].toFixed(1)},${base}L${xy[0][0].toFixed(1)},${base}Z` };
  });
  const line = parts.map((p) => p.line).join("");
  const area = parts.map((p) => p.area).join("");
  const alertCount = [...alerts].filter((t) => t >= t0 && t < t1).length;

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    if (!points.length) return;
    const r = e.currentTarget.getBoundingClientRect();
    const vx = ((e.clientX - r.left) / r.width) * W;
    let best = points[0];
    for (const p of points) if (Math.abs(x(p.t + WINDOW_S / 2) - vx) < Math.abs(x(best.t + WINDOW_S / 2) - vx)) best = p;
    setHover(best);
  }

  return (
    <figure className="chart">
      <figcaption>
        <span>{title}</span>
        {alertCount > 0 && (
          <span className="alert-tag">
            <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><path d="M5 1 9.5 9h-9z" /></svg>
            {alertCount} alert window{alertCount === 1 ? "" : "s"}
          </span>
        )}
      </figcaption>
      <div className="plot">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title}, ${points.length} windows`}
             onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
          {[...alerts].filter((t) => t >= t0 && t < t1).map((t) => (
            <rect key={t} className="alert-band" x={x(t)} y={PAD.top} width={x(t + WINDOW_S) - x(t)}
                  height={base - PAD.top} />
          ))}
          {[0, yMax / 2, yMax].map((v) => (
            <g key={v}>
              <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} />
              <text className="tick" x={PAD.left - 6} y={y(v) + 3} textAnchor="end">{tick(signal, v)}</text>
            </g>
          ))}
          <text className="tick" x={PAD.left} y={H - 4}>{formatTime(t0)}</text>
          <text className="tick" x={W - PAD.right} y={H - 4} textAnchor="end">{formatTime(t1)}</text>
          {area && <path className="wash" d={area} />}
          {line && <path className="line" d={line} />}
          {hover && (
            <g>
              <line className="crosshair" x1={x(hover.t + WINDOW_S / 2)} x2={x(hover.t + WINDOW_S / 2)}
                    y1={PAD.top} y2={base} />
              <circle className="dot" cx={x(hover.t + WINDOW_S / 2)} cy={y(hover.v)} r={4} />
            </g>
          )}
        </svg>
        {hover && (
          <div className="tooltip" style={{ left: `${(x(hover.t + WINDOW_S / 2) / W) * 100}%` }}>
            <strong>{fmt(signal, hover.v)}</strong>
            <span>{formatTime(hover.t)}{alerts.has(hover.t) ? " · alert" : ""}</span>
          </div>
        )}
        {!points.length && <p className="empty">No closed windows yet</p>}
      </div>
    </figure>
  );
}
