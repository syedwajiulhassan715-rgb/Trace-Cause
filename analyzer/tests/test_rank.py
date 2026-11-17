from tracecause.buckets import WINDOW_NS
from tracecause.detect import Score
from tracecause.otlp import Span
from tracecause.rank import Candidate, call_graph, depths, rank

W = WINDOW_NS


def sp(span_id, service, kind, parent=None, trace="t1"):
    return Span(trace, span_id, parent, service, span_id, kind, 0, 1, False, None, False)


SPANS = [
    sp("gw", "gateway", "SERVER"), sp("gw-c", "gateway", "CLIENT", "gw"),
    sp("or", "orders", "SERVER", "gw-c"),
    sp("or-db", "orders", "CLIENT", "or"),
    sp("or-c1", "orders", "CLIENT", "or"), sp("in", "inventory", "SERVER", "or-c1"),
    sp("or-c2", "orders", "CLIENT", "or"), sp("pa", "payments", "SERVER", "or-c2"),
]
EDGES = {("gateway", "orders"), ("orders", "inventory"), ("orders", "payments")}


def z(service, window, signal, value):
    return Score(service, window * W, signal, 0.0, 0.0, 1.0, value)


def test_call_graph_from_spans():
    assert call_graph(SPANS) == EDGES


def test_depth_is_distance_from_the_entry_service():
    assert depths(EDGES) == {"gateway": 0, "orders": 1, "inventory": 2, "payments": 2}


def test_depths_survive_a_cycle():
    d = depths({("a", "b"), ("b", "a"), ("b", "c")})
    assert set(d) == {"a", "b", "c"}


def test_strongest_service_ranks_first():
    # Residual propagation: gateway's self-time moves a little, inventory's a lot.
    scores = [z("gateway", 1, "self_ms", 4.0), z("inventory", 1, "self_ms", 200.0), z("orders", 1, "self_ms", 0.5)]
    got = rank(scores, {1 * W}, EDGES)
    assert [c.service for c in got] == ["inventory", "gateway", "orders"]
    assert got[0] == Candidate("inventory", 200.0, "self_ms", 2)


def test_score_is_the_median_over_incident_windows():
    scores = [z("payments", 1, "db_ms", 10.0), z("payments", 2, "db_ms", 300.0), z("payments", 3, "db_ms", 20.0),
              z("orders", 1, "self_ms", 50.0), z("orders", 2, "self_ms", 1.0), z("orders", 3, "self_ms", 1.0)]
    got = {c.service: c.score for c in rank(scores, {1 * W, 2 * W, 3 * W}, EDGES)}
    # one big window does not decide it: median, not max
    assert got == {"payments": 20.0, "orders": 1.0}


def test_strongest_signal_per_window_is_used():
    scores = [z("payments", 1, "db_ms", 9.0), z("payments", 1, "self_ms", 2.0), z("payments", 1, "own_error_rate", 0.0)]
    (c,) = rank(scores, {1 * W}, EDGES)
    assert (c.score, c.signal) == (9.0, "db_ms")


def test_windows_outside_the_incident_are_ignored():
    scores = [z("orders", 0, "self_ms", 99.0), z("payments", 1, "db_ms", 5.0), z("orders", 1, "self_ms", 1.0)]
    assert [c.service for c in rank(scores, {1 * W}, EDGES)] == ["payments", "orders"]


def test_a_missing_window_counts_as_zero():
    # payments has no score in window 2 (too few requests): treat as no evidence, not as skipped
    scores = [z("payments", 1, "db_ms", 9.0), z("orders", 1, "self_ms", 6.0), z("orders", 2, "self_ms", 6.0)]
    got = {c.service: c.score for c in rank(scores, {1 * W, 2 * W}, EDGES)}
    assert got == {"payments": 4.5, "orders": 6.0}


def test_tie_goes_to_the_more_downstream_service():
    scores = [z("orders", 1, "self_ms", 5.0), z("payments", 1, "self_ms", 5.0)]
    assert [c.service for c in rank(scores, {1 * W}, EDGES)] == ["payments", "orders"]


def test_no_incident_means_no_ranking():
    assert rank([z("orders", 1, "self_ms", 5.0)], set(), EDGES) == []


def test_incidents_split_on_gaps_longer_than_the_allowed_quiet_time():
    from tracecause.rank import incidents
    # windows 1,2,3 then quiet for 3 windows (40-60 s), then 7,9 (one quiet window: same incident)
    got = incidents({1 * W, 2 * W, 3 * W, 7 * W, 9 * W}, max_gap_windows=2)
    assert got == [{1 * W, 2 * W, 3 * W}, {7 * W, 9 * W}]
    assert incidents(set(), max_gap_windows=2) == []
