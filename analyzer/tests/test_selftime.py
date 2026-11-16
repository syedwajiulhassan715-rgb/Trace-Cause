from tracecause.otlp import Span
from tracecause.selftime import RequestTime, request_times, self_times, union_ns

MS = 1_000_000


def sp(span_id, service, kind, start_ms, end_ms, parent=None, is_db=False, trace="t1"):
    return Span(trace, span_id, parent, service, span_id, kind, start_ms * MS, end_ms * MS, False, None, is_db)


# gateway -> orders -> (inventory || payments), with overlapping calls from orders (40-60 ms).
TRACE = [
    sp("gw", "gateway", "SERVER", 0, 100),
    sp("gw-c", "gateway", "CLIENT", 5, 95, parent="gw"),
    sp("or", "orders", "SERVER", 10, 90, parent="gw-c"),
    sp("or-db", "orders", "CLIENT", 12, 20, parent="or", is_db=True),
    sp("or-c1", "orders", "CLIENT", 25, 60, parent="or"),
    sp("in", "inventory", "SERVER", 27, 58, parent="or-c1"),
    sp("in-db", "inventory", "CLIENT", 30, 35, parent="in", is_db=True),
    sp("or-c2", "orders", "CLIENT", 40, 80, parent="or"),
    sp("pa", "payments", "SERVER", 42, 78, parent="or-c2"),
    sp("pa-db", "payments", "CLIENT", 45, 75, parent="pa", is_db=True),
]


def test_union_merges_overlaps():
    assert union_ns([(25, 60), (40, 80), (12, 20)]) == 63
    assert union_ns([]) == 0
    assert union_ns([(0, 10), (10, 20)]) == 20


def test_span_self_time_subtracts_union_of_children():
    st = {k[1]: v / MS for k, v in self_times(TRACE).items()}
    assert st == {
        "gw": 10, "gw-c": 10,
        "or": 17,            # 80 - |12-20 ∪ 25-60 ∪ 40-80| = 80 - 63
        "or-db": 8, "or-c1": 4, "or-c2": 4,
        "in": 26, "in-db": 5,
        "pa": 6, "pa-db": 30,
    }


def test_per_request_own_and_db_time():
    got = {r.service: (r.own_ns / MS, r.db_ns / MS) for r in request_times(TRACE)}
    assert got == {
        "gateway": (20, 0),     # server 10 + outgoing call overhead 10
        "orders": (25, 8),      # server 17 + call overheads 4 + 4; DB 8
        "inventory": (26, 5),
        "payments": (6, 30),
    }


def test_request_time_carries_the_server_span_identity():
    r = next(r for r in request_times(TRACE) if r.service == "inventory")
    assert r == RequestTime(service="inventory", trace_id="t1", span_id="in", start_ns=27 * MS,
                            own_ns=26 * MS, db_ns=5 * MS, error=False, own_error=False)


def test_children_are_clipped_to_parent():
    # Clock skew: child appears to run past its parent's end.
    st = self_times([sp("p", "a", "SERVER", 0, 10), sp("c", "a", "INTERNAL", 5, 30, parent="p")])
    assert st[("t1", "p")] == 5 * MS


def test_missing_child_means_all_time_is_self():
    # The downstream span never arrived: we cannot tell, so the caller keeps the time.
    st = self_times([sp("p", "a", "SERVER", 0, 10)])
    assert st[("t1", "p")] == 10 * MS


def test_traces_do_not_mix():
    spans = [sp("p", "a", "SERVER", 0, 10, trace="t1"), sp("c", "a", "INTERNAL", 0, 10, parent="p", trace="t2")]
    assert self_times(spans)[("t1", "p")] == 10 * MS


def test_nested_server_in_same_service_starts_a_new_request():
    # A service calling itself is two requests, not one.
    spans = [
        sp("a1", "svc", "SERVER", 0, 50),
        sp("a1-c", "svc", "CLIENT", 10, 40, parent="a1"),
        sp("a2", "svc", "SERVER", 12, 38, parent="a1-c"),
    ]
    got = sorted((r.span_id, r.own_ns / MS) for r in request_times(spans))
    assert got == [("a1", 24), ("a2", 26)]


def _err(span_id, service, kind, start_ms, end_ms, parent=None, error=False):
    return Span("t1", span_id, parent, service, span_id, kind, start_ms * MS, end_ms * MS, error, None, False)


def test_error_is_owned_by_the_deepest_failing_request():
    # payments fails; orders and gateway fail only because of it.
    spans = [
        _err("gw", "gateway", "SERVER", 0, 50, error=True),
        _err("gw-c", "gateway", "CLIENT", 5, 45, parent="gw", error=True),
        _err("or", "orders", "SERVER", 10, 40, parent="gw-c", error=True),
        _err("or-c1", "orders", "CLIENT", 12, 20, parent="or"),
        _err("in", "inventory", "SERVER", 13, 19, parent="or-c1"),
        _err("or-c2", "orders", "CLIENT", 22, 35, parent="or", error=True),
        _err("pa", "payments", "SERVER", 23, 34, parent="or-c2", error=True),
    ]
    got = {r.service: (r.error, r.own_error) for r in request_times(spans)}
    assert got == {
        "gateway": (True, False),
        "orders": (True, False),
        "inventory": (False, False),
        "payments": (True, True),
    }


def test_error_without_a_failing_downstream_request_is_owned():
    # The call to payments never produced a server span (e.g. connection refused): orders owns it.
    spans = [
        _err("or", "orders", "SERVER", 0, 10, error=True),
        _err("or-c", "orders", "CLIENT", 2, 8, parent="or", error=True),
    ]
    (r,) = request_times(spans)
    assert (r.error, r.own_error) == (True, True)
