from tracecause.otlp import Span
from tracecause.store import SpanStore

S = 1_000_000_000


def mk(span_id, start_s, route="/x", trace="t1"):
    return Span(trace, span_id, None, "orders", "POST /x", "SERVER", start_s * S, start_s * S + 1000,
                False, route, False)


def test_round_trip():
    store = SpanStore(":memory:")
    a = mk("a", 5)
    assert store.add([a]) == 1
    assert store.spans_between(0, 10 * S) == [a]


def test_duplicate_spans_are_stored_once():
    store = SpanStore(":memory:")
    store.add([mk("a", 5)])
    assert store.add([mk("a", 5), mk("b", 6)]) == 1
    assert store.count() == 2


def test_range_is_half_open_on_start_time():
    store = SpanStore(":memory:")
    store.add([mk("a", 0), mk("b", 9), mk("c", 10)])
    assert [s.span_id for s in store.spans_between(0, 10 * S)] == ["a", "b"]


def test_admin_spans_are_dropped_at_ingest():
    store = SpanStore(":memory:")
    assert store.add([mk("a", 1, route="/admin/fault"), mk("b", 1)]) == 1
    assert store.count() == 1


def test_trace_lookup_returns_all_spans_of_a_trace():
    store = SpanStore(":memory:")
    store.add([mk("a", 1, trace="t1"), mk("b", 2, trace="t2"), mk("c", 3, trace="t1")])
    assert [s.span_id for s in store.trace("t1")] == ["a", "c"]
