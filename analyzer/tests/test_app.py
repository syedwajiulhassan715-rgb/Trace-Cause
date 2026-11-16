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
         "mean_ms": 40.0, "p50_ms": 30.0, "p95_ms": 50.0, "closed": True},
        {"service": "inventory", "window_start_s": 10, "requests": 1, "errors": 0, "error_rate": 0.0,
         "mean_ms": 8.0, "p50_ms": 8.0, "p95_ms": 8.0, "closed": True},
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


def test_health_reports_span_count():
    c, _ = client()
    c.post("/v1/traces", json=payload())
    assert c.get("/health").json() == {"status": "ok", "spans": 4}
