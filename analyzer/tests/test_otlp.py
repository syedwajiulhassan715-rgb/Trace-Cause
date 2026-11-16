from otlp_fixtures import export, span

from tracecause.otlp import Span, parse_export

T = "0af7651916cd43dd8448eb211c80319c"


def test_flattens_resource_spans_with_service_name():
    body = export(
        ("gateway", [span(T, "a1", "POST /checkout", 1_000, 5_000, kind=2,
                          attrs=[("http.route", "/checkout"), ("http.response.status_code", 200)])]),
        ("orders", [span(T, "b1", "INSERT tracecause.orders", 2_000, 3_000, parent="a1", kind=3,
                         attrs=[("db.system.name", "postgresql")])]),
    )
    spans = parse_export(body)
    assert spans == [
        Span(trace_id=T, span_id="a1", parent_id=None, service="gateway", name="POST /checkout",
             kind="SERVER", start_ns=1_000, end_ns=5_000, error=False, route="/checkout", is_db=False),
        Span(trace_id=T, span_id="b1", parent_id="a1", service="orders", name="INSERT tracecause.orders",
             kind="CLIENT", start_ns=2_000, end_ns=3_000, error=False, route=None, is_db=True),
    ]


def test_error_status_and_duration():
    (s,) = parse_export(export(("payments", [span(T, "c1", "POST /charge", 10, 1_000_010, status=2)])))
    assert s.error is True
    assert s.duration_ns == 1_000_000


def test_empty_parent_id_means_root():
    raw = span(T, "a1", "root", 0, 1)
    raw["parentSpanId"] = ""
    (s,) = parse_export(export(("gateway", [raw])))
    assert s.parent_id is None


def test_missing_service_name_is_unknown():
    body = {"resourceSpans": [{"resource": {}, "scopeSpans": [{"spans": [span(T, "a1", "x", 0, 1)]}]}]}
    assert parse_export(body)[0].service == "unknown"


def test_legacy_db_system_attribute_counts_as_db():
    (s,) = parse_export(export(("inventory", [span(T, "d1", "q", 0, 1, kind=3, attrs=[("db.system", "postgresql")])])))
    assert s.is_db


def test_admin_route_detection():
    (s,) = parse_export(export(("orders", [span(T, "e1", "PUT /admin/fault", 0, 1, attrs=[("http.route", "/admin/fault")])])))
    assert s.is_admin


def test_empty_payload():
    assert parse_export({}) == []
