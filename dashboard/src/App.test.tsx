import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";

afterEach(() => vi.unstubAllGlobals());

it("shows the ranking and an explanation from the analyzer's numbers", async () => {
  const now = Math.floor(Date.now() / 1000 / 10) * 10;
  const bucket = (service: string, t: number, db: number) => ({
    service, window_start_s: t, requests: 100, errors: 0, error_rate: 0, own_errors: 0, mean_ms: 5,
    p50_ms: 5, p95_ms: 8, self_p50_ms: 1, self_p95_ms: 2, db_p50_ms: db, db_p95_ms: db, closed: true,
  });
  const responses: Record<string, unknown> = {
    "/api/buckets": [bucket("payments", now - 60, 3), bucket("payments", now - 50, 300), bucket("orders", now - 60, 2)],
    "/api/anomalies": [{ service: "payments", window_start_s: now - 50, detector: "persistence",
      evidence: [{ signal: "db_ms", value: 300, median: 3, scale: 1, z: 297 }] }],
    "/api/rootcause": { detector: "persistence", incident_windows_s: [now - 50], ranking: [
      { rank: 1, service: "payments", score: 297, signal: "db_ms", depth: 2 },
      { rank: 2, service: "orders", score: 0, signal: "self_ms", depth: 1 }] },
  };
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const body = responses[url.split("?")[0]];
    return new Response(JSON.stringify(body), { status: 200 });
  }));

  render(<App />);

  expect(await screen.findByText(/payments is the most likely cause: database time 300.0 ms/)).toBeTruthy();
  const rows = screen.getAllByRole("row").map((r) => r.textContent);
  expect(rows).toContain("1payments297.0Database time (p50)2");
  expect(screen.getAllByText("1 alert window").length).toBe(1);
});
