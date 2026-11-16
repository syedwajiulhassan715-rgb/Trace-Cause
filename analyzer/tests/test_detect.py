import pytest

from tracecause.buckets import WINDOW_NS, Bucket
from tracecause.detect import (PersistenceDetector, Score, ThresholdDetector, robust_stats, score_series)


def b(i, self_ms=10.0, db_ms=3.0, errors=0, requests=100, service="inventory", closed=True):
    return Bucket(service, i * WINDOW_NS, requests, errors, errors, 0.0, 0.0, 0.0,
                  self_ms, self_ms, db_ms, db_ms, closed)


def sc(i, z, signal="self_ms", service="inventory"):
    return Score(service, i * WINDOW_NS, signal, 0.0, 0.0, 1.0, z)


# --- baseline statistics -------------------------------------------------------------

def test_median_and_mad_scale():
    # median 100; sorted |deviations| = 0,0,0,0,10,10,10,10,20,20 -> MAD 10 -> scale 1.4826 * 10
    med, scale = robust_stats([80, 90, 100, 110, 120, 100, 90, 110, 100, 100], floor=1.0)
    assert med == 100
    assert scale == pytest.approx(14.826)


def test_floor_applies_when_history_is_flat():
    assert robust_stats([3.0] * 10, floor=1.0) == (3.0, 1.0)


# --- scoring -------------------------------------------------------------------------

def test_scores_against_trailing_history():
    hist = [80, 90, 100, 110, 120, 100, 90, 110, 100, 100]
    buckets = [b(i, self_ms=v) for i, v in enumerate(hist)] + [b(10, self_ms=130)]
    (last,) = [s for s in score_series(buckets) if s.window_start_ns == 10 * WINDOW_NS and s.signal == "self_ms"]
    assert last.median == 100
    assert last.z == pytest.approx(30 / 14.826, rel=1e-4)


def test_needs_minimum_history():
    buckets = [b(i) for i in range(6)]
    # windows 0-5 have fewer than 6 earlier windows, so nothing is scored
    assert score_series(buckets, min_history=6) == []
    assert {s.window_start_ns for s in score_series(buckets + [b(6)], min_history=6)} == {6 * WINDOW_NS}


def test_history_is_limited_to_last_n_windows():
    # Old windows at 1000 ms must not count once they fall out of the 6-window history.
    buckets = [b(i, self_ms=1000) for i in range(6)] + [b(i, self_ms=10) for i in range(6, 12)] + [b(12, self_ms=10)]
    last = [s for s in score_series(buckets, history=6) if s.window_start_ns == 12 * WINDOW_NS and s.signal == "self_ms"]
    assert last[0].median == 10


def test_open_and_tiny_windows_are_skipped():
    buckets = [b(i) for i in range(6)] + [b(6, requests=1, self_ms=999), b(7, closed=False, self_ms=999)]
    assert score_series(buckets) == []


def test_own_error_rate_signal_uses_its_floor():
    buckets = [b(i) for i in range(10)] + [b(10, errors=30)]
    err = [s for s in score_series(buckets) if s.window_start_ns == 10 * WINDOW_NS and s.signal == "own_error_rate"]
    assert err[0].z == pytest.approx(0.30 / 0.02)


def test_services_are_scored_separately():
    buckets = [b(i, service="a", self_ms=10) for i in range(10)] + [b(i, service="b", self_ms=500) for i in range(10)]
    buckets += [b(10, service="a", self_ms=10), b(10, service="b", self_ms=500)]
    assert all(s.z == 0 for s in score_series(buckets) if s.window_start_ns == 10 * WINDOW_NS)


# --- detectors -----------------------------------------------------------------------

def test_threshold_fires_on_a_single_window():
    alerts = ThresholdDetector(k=3).detect([sc(1, 1.0), sc(2, 3.5), sc(3, 0.2)])
    assert [(a.window_start_ns // WINDOW_NS, a.service) for a in alerts] == [(2, "inventory")]
    assert alerts[0].evidence[0].z == 3.5


def test_threshold_groups_signals_of_one_window():
    alerts = ThresholdDetector(k=3).detect([sc(1, 4.0, "self_ms"), sc(1, 5.0, "own_error_rate"), sc(1, 1.0, "db_ms")])
    assert len(alerts) == 1
    assert {e.signal for e in alerts[0].evidence} == {"self_ms", "own_error_rate"}


def test_persistence_ignores_short_spikes():
    scores = [sc(1, 9.0), sc(2, 9.0), sc(3, 0.0), sc(4, 9.0)]
    assert PersistenceDetector(k=3, windows=3).detect(scores) == []


def test_persistence_fires_from_the_nth_consecutive_window():
    scores = [sc(i, 5.0) for i in range(1, 6)]
    alerts = PersistenceDetector(k=3, windows=3).detect(scores)
    assert [a.window_start_ns // WINDOW_NS for a in alerts] == [3, 4, 5]


def test_persistence_requires_adjacent_windows():
    # a gap (no window 3) breaks the run
    scores = [sc(1, 5.0), sc(2, 5.0), sc(4, 5.0)]
    assert PersistenceDetector(k=3, windows=3).detect(scores) == []


def test_persistence_requires_the_same_signal():
    scores = [sc(1, 5.0, "self_ms"), sc(2, 5.0, "db_ms"), sc(3, 5.0, "self_ms")]
    assert PersistenceDetector(k=3, windows=3).detect(scores) == []
