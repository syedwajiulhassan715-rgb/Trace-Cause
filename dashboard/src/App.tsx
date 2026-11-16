import { useEffect, useState } from "react";
import { Chart } from "./Chart";
import {
  type Alert, alertWindows, type Bucket, type Detector, explain, formatTime, formatValue,
  orderServices, type RootCause, series, SIGNALS,
} from "./model";

const RANGE_S = 15 * 60;
const REFRESH_MS = 10_000;
const SIGNAL_LABEL: Record<string, string> = Object.fromEntries(SIGNALS.map((s) => [s.key, s.label]));

type Data = { buckets: Bucket[]; alerts: Alert[]; rootcause: RootCause; now: number };

async function load(detector: Detector, signal: AbortSignal): Promise<Data> {
  const now = Math.floor(Date.now() / 1000);
  const range = `start_s=${now - RANGE_S}&end_s=${now}`;
  const get = async <T,>(path: string): Promise<T> => {
    const r = await fetch(`/api${path}`, { signal });
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
    return r.json() as Promise<T>;
  };
  const [buckets, alerts, rootcause] = await Promise.all([
    get<Bucket[]>(`/buckets?${range}`),
    get<Alert[]>(`/anomalies?detector=${detector}&${range}`),
    get<RootCause>(`/rootcause?detector=${detector}&${range}`),
  ]);
  return { buckets, alerts, rootcause, now };
}

export function App() {
  const [detector, setDetector] = useState<Detector>("persistence");
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ctrl = new AbortController();
    const tick = () => {
      ctrl.abort();
      ctrl = new AbortController();
      load(detector, ctrl.signal)
        .then((d) => { setData(d); setError(null); })
        .catch((e: unknown) => { if (!(e instanceof DOMException && e.name === "AbortError")) setError(String(e)); });
    };
    tick();
    const id = setInterval(tick, REFRESH_MS);
    return () => { clearInterval(id); ctrl.abort(); };
  }, [detector]);

  const services = data ? orderServices(data.buckets.map((b) => b.service)) : [];
  const domain: [number, number] = data
    ? [Math.floor((data.now - RANGE_S) / 10) * 10, Math.floor(data.now / 10) * 10]
    : [0, 1];
  const sentence = data ? explain(data.rootcause, data.alerts) : null;

  return (
    <main>
      <header>
        <div>
          <h1>TraceCause</h1>
          <p className="muted">
            Last 15 minutes · 10 s windows{data ? ` · updated ${formatTime(data.now)}` : ""}
          </p>
        </div>
        <div className="segmented" role="group" aria-label="Detector">
          {(["persistence", "threshold"] as const).map((d) => (
            <button key={d} aria-pressed={detector === d} onClick={() => setDetector(d)}>{d}</button>
          ))}
        </div>
      </header>

      {error && <p className="banner" role="alert">Cannot reach the analyzer: {error}</p>}

      <section className="card" aria-labelledby="rc-title">
        <h2 id="rc-title">Root cause</h2>
        {!data ? <p className="muted">Loading…</p>
          : data.rootcause.ranking.length === 0 ? <p className="muted">No incident in the last 15 minutes.</p>
          : (
            <>
              <p className="sentence">{sentence}</p>
              <table>
                <thead>
                  <tr><th>Rank</th><th>Service</th><th className="num">Score (z)</th><th>Main signal</th><th className="num">Call depth</th></tr>
                </thead>
                <tbody>
                  {data.rootcause.ranking.map((c) => (
                    <tr key={c.service}>
                      <td>{c.rank}</td><td>{c.service}</td><td className="num">{c.score.toFixed(1)}</td>
                      <td>{SIGNAL_LABEL[c.signal] ?? c.signal}</td><td className="num">{c.depth}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
      </section>

      <section aria-label="Signals per service">
        {services.map((svc) => {
          const alerted = alertWindows(data!.alerts, svc);
          const bySignal = (key: string) => new Set(data!.alerts
            .filter((a) => a.service === svc && a.evidence.some((e) => e.signal === key))
            .map((a) => a.window_start_s));
          return (
            <div className="row" key={svc}>
              <h3>{svc}{alerted.size > 0 && <span className="muted"> · {alerted.size} alerted</span>}</h3>
              <div className="charts">
                {SIGNALS.map((s) => (
                  <Chart key={s.key} title={s.label} signal={s.key} domain={domain}
                         points={series(data!.buckets, svc, s.key)} alerts={bySignal(s.key)} />
                ))}
              </div>
            </div>
          );
        })}
      </section>

      {data && data.alerts.length > 0 && (
        <details className="card">
          <summary>All alerts ({data.alerts.length})</summary>
          <table>
            <thead>
              <tr><th>Window</th><th>Service</th><th>Signal</th><th className="num">Value</th><th className="num">Baseline</th><th className="num">z</th></tr>
            </thead>
            <tbody>
              {data.alerts.flatMap((a) => a.evidence.map((e) => (
                <tr key={`${a.service}-${a.window_start_s}-${e.signal}`}>
                  <td>{formatTime(a.window_start_s)}</td><td>{a.service}</td><td>{SIGNAL_LABEL[e.signal] ?? e.signal}</td>
                  <td className="num">{formatValue(e.signal, e.value)}</td>
                  <td className="num">{formatValue(e.signal, e.median)}</td><td className="num">{e.z.toFixed(1)}</td>
                </tr>
              )))}
            </tbody>
          </table>
        </details>
      )}
    </main>
  );
}
