import { describe, expect, it } from "vitest";
import { alertWindows, type Alert, type Bucket, explain, formatValue, niceMax, orderServices, series } from "./model";

function bucket(service: string, t: number, over: Partial<Bucket> = {}): Bucket {
  return {
    service, window_start_s: t, requests: 100, errors: 0, error_rate: 0, own_errors: 0,
    mean_ms: 5, p50_ms: 5, p95_ms: 8, self_p50_ms: 1, self_p95_ms: 2, db_p50_ms: 3, db_p95_ms: 4,
    closed: true, ...over,
  };
}

describe("orderServices", () => {
  it("puts known services in call order, then others alphabetically", () => {
    expect(orderServices(["payments", "zeta", "gateway", "alpha", "orders"]))
      .toEqual(["gateway", "orders", "payments", "alpha", "zeta"]);
  });
});

describe("series", () => {
  const buckets = [
    bucket("orders", 20, { self_p50_ms: 7 }),
    bucket("orders", 10, { self_p50_ms: 4, own_errors: 25 }),
    bucket("orders", 30, { closed: false }),
    bucket("payments", 10),
  ];

  it("returns closed windows of one service, oldest first", () => {
    expect(series(buckets, "orders", "self_ms")).toEqual([{ t: 10, v: 4 }, { t: 20, v: 7 }]);
  });

  it("reports own errors as a percentage of requests", () => {
    expect(series(buckets, "orders", "own_error_rate")[0]).toEqual({ t: 10, v: 25 });
  });
});

describe("alertWindows", () => {
  it("collects the window starts alerted for a service", () => {
    const alerts: Alert[] = [
      { service: "orders", window_start_s: 10, detector: "threshold", evidence: [] },
      { service: "payments", window_start_s: 20, detector: "threshold", evidence: [] },
      { service: "orders", window_start_s: 30, detector: "threshold", evidence: [] },
    ];
    expect([...alertWindows(alerts, "orders")]).toEqual([10, 30]);
  });
});

describe("niceMax", () => {
  it("rounds up to 1, 2 or 5 times a power of ten", () => {
    expect(niceMax(0)).toBe(1);
    expect(niceMax(0.7)).toBe(1);
    expect(niceMax(3.2)).toBe(5);
    expect(niceMax(201)).toBe(500);
    expect(niceMax(20)).toBe(20);
  });
});

describe("formatValue", () => {
  it("formats per signal unit", () => {
    expect(formatValue("self_ms", 201.06)).toBe("201.1 ms");
    expect(formatValue("own_error_rate", 0.304)).toBe("30.4 %");
  });
});

describe("explain", () => {
  const alerts: Alert[] = [
    { service: "payments", window_start_s: 10, detector: "persistence",
      evidence: [{ signal: "db_ms", value: 303.5, median: 2.8, scale: 1, z: 300.7 }] },
    { service: "payments", window_start_s: 20, detector: "persistence",
      evidence: [{ signal: "db_ms", value: 310.0, median: 2.8, scale: 1, z: 307.2 }] },
  ];

  it("states the top service with its strongest evidence, from the numbers only", () => {
    const rc = { detector: "persistence", incident_windows_s: [10, 20],
      ranking: [{ rank: 1, service: "payments", score: 304, signal: "db_ms", depth: 2 }] };
    expect(explain(rc, alerts)).toBe(
      "payments is the most likely cause: database time 310.0 ms against a baseline of 2.8 ms " +
      "(z = 307.2), across 2 alert windows.");
  });

  it("says nothing without an incident", () => {
    expect(explain({ detector: "persistence", incident_windows_s: [], ranking: [] }, alerts)).toBeNull();
  });
});
