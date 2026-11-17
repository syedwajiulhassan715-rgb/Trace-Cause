from fastapi.testclient import TestClient
from otlp_fixtures import export, span

from tracecause.app import create_app
from tracecause.store import SpanStore

S = 1_000_000_000
MS = 1_000_000
T = "0af7651916cd43dd8448eb211c80319c"


def client(now_s=100):
    store = SpanStore(":memory:")
    return TestClient(create_app(store, clock_ns=lambda: now_s * S)), store


def payload():
    return export(
        ("orders", [
            span(T, "a1", "POST /orders", 1 * S, 1 * S + 30 * MS, attrs=[("http.route", "/orders")]),
            span(T, "a2", "POST /orders", 2 * S, 2 * S + 50 * MS, status=2, attrs=[("http.route", "/orders")]),
            span(T, "a3", "INSERT tracecause.orders", 1 * S, 1 * S + 2 * MS, parent="a1", kind=3,
                 attrs=[("db.system.name", "postgresql")]),
        ]),
        ("inventory", [span(T, "b1", "POST /reserve", 11 * S, 11 * S + 8 * MS, attrs=[("http.route", "/reserve")])]),
    )


def test_ingest_stores_spans_and_returns_otlp_response():
    c, store = client()
    r = c.post("/v1/traces", json=payload())
    assert r.status_code == 200
    assert r.json() == {}
    assert store.count() == 4


def test_malformed_payload_is_rejected_with_400():
    c, _ = client()
    assert c.post("/v1/traces", content=b"not json", headers={"Content-Type": "application/json"}).status_code == 400
    assert c.post("/v1/traces", json={"resourceSpans": [{"scopeSpans": [{"spans": [{}]}]}]}).status_code == 400


def test_buckets_endpoint():
    c, _ = client(now_s=100)
    c.post("/v1/traces", json=payload())
    r = c.get("/buckets", params={"start_s": 0, "end_s": 60})
    assert r.status_code == 200
    assert r.json() == [
        {"service": "orders", "window_start_s": 0, "requests": 2, "errors": 1, "error_rate": 0.5,
         "own_errors": 1,
         "mean_ms": 40.0, "p50_ms": 30.0, "p95_ms": 50.0,
         "self_p50_ms": 28.0, "self_p95_ms": 50.0, "db_p50_ms": 0.0, "db_p95_ms": 2.0, "closed": True},
        {"service": "inventory", "window_start_s": 10, "requests": 1, "errors": 0, "error_rate": 0.0,
         "own_errors": 0,
         "mean_ms": 8.0, "p50_ms": 8.0, "p95_ms": 8.0,
         "self_p50_ms": 8.0, "self_p95_ms": 8.0, "db_p50_ms": 0.0, "db_p95_ms": 0.0, "closed": True},
    ]


def test_buckets_filter_by_service():
    c, _ = client()
    c.post("/v1/traces", json=payload())
    r = c.get("/buckets", params={"start_s": 0, "end_s": 60, "service": "inventory"})
    assert [b["service"] for b in r.json()] == ["inventory"]


def test_buckets_default_to_last_five_minutes():
    c, _ = client(now_s=1000)
    c.post("/v1/traces", json=payload())  # spans at 1-11 s are older than 1000 - 300
    assert c.get("/buckets").json() == []


def test_buckets_only_cover_the_requested_windows():
    c, _ = client(now_s=100)
    c.post("/v1/traces", json=payload())  # same trace has spans at 1 s and 11 s
    assert [b["window_start_s"] for b in c.get("/buckets", params={"start_s": 0, "end_s": 10}).json()] == [0]


def test_health_reports_span_count():
    c, _ = client()
    c.post("/v1/traces", json=payload())
    assert c.get("/health").json() == {"status": "ok", "spans": 4}


def _steady_then_slow(store):
    """inventory: 6 requests per window; 10 ms in windows 0-9, 300 ms in windows 10-12."""
    from tracecause.otlp import Span
    spans = []
    for w in range(13):
        for i in range(6):
            start = w * 10 * S + i * S
            dur = (300 if w >= 10 else 10) * MS
            spans.append(Span("t%d_%d" % (w, i), "s", None, "inventory", "POST /reserve", "SERVER",
                              start, start + dur, False, "/reserve", False))
    store.add(spans)


def test_anomalies_threshold_flags_every_slow_window():
    c, store = client(now_s=1000)
    _steady_then_slow(store)
    alerts = c.get("/anomalies", params={"detector": "threshold", "start_s": 0, "end_s": 130}).json()
    assert [(a["service"], a["window_start_s"]) for a in alerts] == [("inventory", 100), ("inventory", 110), ("inventory", 120)]
    top = alerts[0]["evidence"][0]
    assert (top["signal"], top["value"], top["median"]) == ("self_ms", 300.0, 10.0)
    assert top["z"] == 290.0  # scale is the 1 ms floor: history is perfectly flat


def test_anomalies_persistence_waits_for_three_windows():
    c, store = client(now_s=1000)
    _steady_then_slow(store)
    alerts = c.get("/anomalies", params={"detector": "persistence", "start_s": 0, "end_s": 130}).json()
    assert [a["window_start_s"] for a in alerts] == [120]
    assert alerts[0]["detector"] == "persistence"


def test_anomalies_uses_history_before_the_requested_range():
    c, store = client(now_s=1000)
    _steady_then_slow(store)
    # Only ask about windows 110-129; the baseline must still come from windows 0-9.
    alerts = c.get("/anomalies", params={"detector": "threshold", "start_s": 110, "end_s": 130}).json()
    assert [a["window_start_s"] for a in alerts] == [110, 120]


def test_unknown_detector_is_rejected():
    c, _ = client()
    assert c.get("/anomalies", params={"detector": "magic"}).status_code == 422


def test_rootcause_ranks_the_slow_service_first():
    from tracecause.otlp import Span
    c, store = client(now_s=1000)
    _steady_then_slow(store)  # inventory slows down from window 10
    store.add([Span("o%d_%d" % (w, i), "s", None, "orders", "POST /orders", "SERVER",
                    w * 10 * S + i * S, w * 10 * S + i * S + 10 * MS, False, "/orders", False)
               for w in range(13) for i in range(6)])
    r = c.get("/rootcause", params={"detector": "persistence", "start_s": 0, "end_s": 130}).json()
    assert r["detector"] == "persistence"
    assert r["incident_windows_s"] == [120]
    assert r["ranking"] == [
        {"rank": 1, "service": "inventory", "score": 290.0, "signal": "self_ms", "depth": 0},
        {"rank": 2, "service": "orders", "score": 0.0, "signal": "self_ms", "depth": 0},
    ]


def test_rootcause_without_incident_is_empty():
    c, _ = client()
    c.post("/v1/traces", json=payload())
    assert c.get("/rootcause", params={"start_s": 0, "end_s": 60}).json() == {
        "detector": "persistence", "incidents_in_range": 0, "incident_windows_s": [], "ranking": []}


def test_rootcause_ranks_only_the_latest_incident():
    from tracecause.otlp import Span
    c, store = client(now_s=2000)
    spans = []
    for w in range(40):
        for i in range(6):
            start = w * 10 * S + i * S
            inv = 300 if 10 <= w < 13 else 10   # first incident: inventory
            pay = 300 if 30 <= w < 33 else 10   # later incident: payments
            spans.append(Span("i%d_%d" % (w, i), "s", None, "inventory", "POST", "SERVER", start, start + inv * MS, False, "/r", False))
            spans.append(Span("p%d_%d" % (w, i), "s", None, "payments", "POST", "SERVER", start, start + pay * MS, False, "/c", False))
    store.add(spans)
    r = c.get("/rootcause", params={"detector": "threshold", "start_s": 0, "end_s": 400}).json()
    assert r["incident_windows_s"] == [300, 310, 320]
    assert r["incidents_in_range"] == 2
    assert r["ranking"][0]["service"] == "payments"
