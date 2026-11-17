// Shapes of the analyzer API and the pure logic the dashboard needs.
// Nothing here decides anything: the analyzer detects and ranks; this only presents.

export type Bucket = {
  service: string;
  window_start_s: number;
  requests: number;
  errors: number;
  error_rate: number;
  own_errors: number;
  mean_ms: number;
  p50_ms: number;
  p95_ms: number;
  self_p50_ms: number;
  self_p95_ms: number;
  db_p50_ms: number;
  db_p95_ms: number;
  closed: boolean;
};

export type Evidence = { signal: string; value: number; median: number; scale: number; z: number };
export type Alert = { service: string; window_start_s: number; detector: string; evidence: Evidence[] };
export type Ranked = { rank: number; service: string; score: number; signal: string; depth: number };
export type RootCause = {
  detector: string;
  incidents_in_range?: number;
  incident_windows_s: number[];
  ranking: Ranked[];
};
export type Detector = "threshold" | "persistence";

export type SignalKey = "self_ms" | "db_ms" | "own_error_rate";
export const SIGNALS: { key: SignalKey; label: string }[] = [
  { key: "self_ms", label: "Own code time (p50)" },
  { key: "db_ms", label: "Database time (p50)" },
  { key: "own_error_rate", label: "Own errors" },
];
const SIGNAL_NAME: Record<string, string> = {
  self_ms: "own code time",
  db_ms: "database time",
  own_error_rate: "own error rate",
};

const SERVICE_ORDER = ["gateway", "orders", "inventory", "payments"];

export function orderServices(names: Iterable<string>): string[] {
  const unique = [...new Set(names)];
  const known = SERVICE_ORDER.filter((s) => unique.includes(s));
  const rest = unique.filter((s) => !SERVICE_ORDER.includes(s)).sort();
  return [...known, ...rest];
}

export type Point = { t: number; v: number };

function valueOf(b: Bucket, signal: SignalKey): number {
  if (signal === "self_ms") return b.self_p50_ms;
  if (signal === "db_ms") return b.db_p50_ms;
  return b.requests ? (100 * b.own_errors) / b.requests : 0;
}

/** Closed windows only: an open window may still be missing spans. */
export function series(buckets: Bucket[], service: string, signal: SignalKey): Point[] {
  return buckets
    .filter((b) => b.service === service && b.closed)
    .sort((a, b) => a.window_start_s - b.window_start_s)
    .map((b) => ({ t: b.window_start_s, v: valueOf(b, signal) }));
}

export function alertWindows(alerts: Alert[], service: string): Set<number> {
  return new Set(alerts.filter((a) => a.service === service).map((a) => a.window_start_s).sort((a, b) => a - b));
}

/** Smallest of 1, 2, 5 x 10^n that is >= v (at least 1), for a clean y-axis top. */
export function niceMax(v: number): number {
  if (!(v > 1)) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 2, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

/** Values from the API: ms for latency signals, a 0-1 rate for errors. */
export function formatValue(signal: string, v: number): string {
  return signal === "own_error_rate" ? `${(100 * v).toFixed(1)} %` : `${v.toFixed(1)} ms`;
}

export function formatTime(t: number): string {
  return new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/**
 * One templated sentence built only from the analyzer's numbers.
 * (An LLM may later rephrase it; it must never change these facts.)
 */
export function explain(rc: RootCause, alerts: Alert[]): string | null {
  const top = rc.ranking[0];
  if (!top || rc.incident_windows_s.length === 0) return null;
  const incident = new Set(rc.incident_windows_s);
  const evidence = alerts
    .filter((a) => a.service === top.service && incident.has(a.window_start_s))
    .flatMap((a) => a.evidence)
    .filter((e) => e.signal === top.signal)
    .sort((a, b) => b.z - a.z)[0];
  const windows = `across ${rc.incident_windows_s.length} alert window${rc.incident_windows_s.length === 1 ? "" : "s"}`;
  const name = SIGNAL_NAME[top.signal] ?? top.signal;
  if (!evidence) return `${top.service} is the most likely cause (${name}, score ${top.score}), ${windows}.`;
  return (
    `${top.service} is the most likely cause: ${name} ${formatValue(top.signal, evidence.value)} ` +
    `against a baseline of ${formatValue(top.signal, evidence.median)} (z = ${evidence.z}), ${windows}.`
  );
}
