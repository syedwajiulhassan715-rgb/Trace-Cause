from tracecause.buckets import Bucket, bucketize, percentile, window_start
from tracecause.otlp import Span

S = 1_000_000_000  # ns per second
MS = 1_000_000


def server(service, start_s, dur_ms, error=False, span_id=None):
    start = int(start_s * S)
    return Span(trace_id="t", span_id=span_id or f"{service}{start_s}{dur_ms}", parent_id=None,
                service=service, name="POST /x", kind="SERVER", start_ns=start,
                end_ns=start + dur_ms * MS, error=error, route="/x", is_db=False)


def test_window_start_floors_to_10s():
    assert window_start(0) == 0
    assert window_start(9 * S + 999) == 0
    assert window_start(10 * S) == 10 * S
    assert window_start(27 * S) == 20 * S


def test_percentile_nearest_rank():
    data = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert percentile(data, 0.5) == 50     # rank ceil(5) = 5
    assert percentile(data, 0.95) == 100   # rank ceil(9.5) = 10
    assert percentile([7], 0.95) == 7


def test_groups_server_spans_by_service_and_window():
    spans = [
        server("orders", 1, 10), server("orders", 2, 20), server("orders", 3, 30, error=True),
        server("orders", 12, 40),
        server("payments", 4, 5),
    ]
    got = bucketize(spans, now_ns=100 * S)
    assert got == [
        # no child spans, so all time is self-time and there is no DB time
        Bucket("orders", 0, 3, 1, 20.0, 20.0, 30.0, 20.0, 30.0, 0.0, 0.0, True),
        Bucket("payments", 0, 1, 0, 5.0, 5.0, 5.0, 5.0, 5.0, 0.0, 0.0, True),
        Bucket("orders", 10 * S, 1, 0, 40.0, 40.0, 40.0, 40.0, 40.0, 0.0, 0.0, True),
    ]


def test_only_server_spans_count_as_requests():
    db = Span("t", "db1", "s1", "orders", "INSERT", "CLIENT", 1 * S, 1 * S + 3 * MS, False, None, True)
    got = bucketize([server("orders", 1, 10), db], now_ns=100 * S)
    assert [b.requests for b in got] == [1]


def test_self_and_db_time_per_bucket():
    # orders spends 30 ms; 10 ms of it waiting on inventory, 5 ms in its database.
    spans = [
        server("orders", 1, 30, span_id="or"),
        Span("t", "db", "or", "orders", "INSERT", "CLIENT", 1 * S + 1 * MS, 1 * S + 6 * MS, False, None, True),
        Span("t", "call", "or", "orders", "POST", "CLIENT", 1 * S + 10 * MS, 1 * S + 20 * MS, False, None, False),
        Span("t", "inv", "call", "inventory", "POST /reserve", "SERVER", 1 * S + 11 * MS, 1 * S + 19 * MS,
             False, "/reserve", False),
    ]
    by_service = {b.service: b for b in bucketize(spans, now_ns=100 * S)}
    # orders own: server 30 - 5 - 10 = 15, plus call overhead 10 - 8 = 2
    assert (by_service["orders"].self_p50_ms, by_service["orders"].db_p50_ms) == (17.0, 5.0)
    assert (by_service["inventory"].self_p50_ms, by_service["inventory"].db_p50_ms) == (8.0, 0.0)


def test_admin_spans_are_ignored():
    admin = Span("t", "ad", None, "orders", "PUT /admin/fault", "SERVER", 1 * S, 1 * S + MS, False,
                 "/admin/fault", False)
    assert bucketize([admin], now_ns=100 * S) == []


def test_window_is_open_until_grace_has_passed():
    spans = [server("orders", 1, 10)]
    # window [0, 10) closes at 10 s + 15 s grace
    assert bucketize(spans, now_ns=24 * S)[0].closed is False
    assert bucketize(spans, now_ns=25 * S)[0].closed is True


def test_error_rate_property():
    b = Bucket("orders", 0, 4, 1, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, True)
    assert b.error_rate == 0.25
