"""Per-service baselines (median + MAD) and two anomaly detectors.

Each closed window of a service is scored against that service's own recent
past: the previous `history` usable windows. The score is a robust z-score,

    z = (value - median) / max(1.4826 * MAD, floor)

Median and MAD ignore a few outliers that would drag a mean and standard
deviation around (a GC pause, a cold cache). 1.4826 * MAD equals the standard
deviation for normal data, so z reads like a usual z-score. The floor stops a
very steady signal (DB time is ~3 ms with almost no spread) from turning a
harmless 0.3 ms wobble into a huge z. Only rises count: a service getting
faster or failing less is not an incident.

Two detectors use the same scores:
- ThresholdDetector: any signal with z >= k in one window. Simple and fast,
  but one noisy window is enough to fire.
- PersistenceDetector: the same signal must have z >= k in `windows`
  consecutive windows. Slower to fire, but a single spike cannot trigger it.
"""

import statistics
from collections import defaultdict
from dataclasses import dataclass

from .buckets import WINDOW_NS, Bucket

MAD_TO_SIGMA = 1.4826


@dataclass(frozen=True)
class Signal:
    name: str
    attr: str
    floor: float


SIGNALS = (
    Signal("self_ms", "self_p50_ms", 1.0),     # ms
    Signal("db_ms", "db_p50_ms", 1.0),         # ms
    Signal("error_rate", "error_rate", 0.02),  # 2 percentage points
)


@dataclass(frozen=True)
class Score:
    service: str
    window_start_ns: int
    signal: str
    value: float
    median: float
    scale: float
    z: float


@dataclass(frozen=True)
class Alert:
    service: str
    window_start_ns: int
    detector: str
    evidence: tuple[Score, ...]  # the signals that crossed the threshold, highest z first


def robust_stats(values, floor):
    med = statistics.median(values)
    mad = statistics.median(abs(v - med) for v in values)
    return med, max(MAD_TO_SIGMA * mad, floor)


def score_series(buckets: list[Bucket], history: int = 30, min_history: int = 6,
                 min_requests: int = 5) -> list[Score]:
    """Score every usable window of every service against its trailing baseline."""
    by_service = defaultdict(list)
    for bk in buckets:
        if bk.closed and bk.requests >= min_requests:
            by_service[bk.service].append(bk)

    out = []
    for service in sorted(by_service):
        series = sorted(by_service[service], key=lambda x: x.window_start_ns)
        for i, bk in enumerate(series):
            past = series[max(0, i - history):i]
            if len(past) < min_history:
                continue
            for sig in SIGNALS:
                med, scale = robust_stats([getattr(p, sig.attr) for p in past], sig.floor)
                value = getattr(bk, sig.attr)
                z = max(0.0, (value - med) / scale)
                out.append(Score(service, bk.window_start_ns, sig.name, value, med, scale, round(z, 4)))
    return out


def _alerts(triggered: dict, detector: str) -> list[Alert]:
    return [Alert(service, start, detector, tuple(sorted(ev, key=lambda s: (-s.z, s.signal))))
            for (start, service), ev in sorted(triggered.items())]


@dataclass(frozen=True)
class ThresholdDetector:
    k: float = 3.0
    name: str = "threshold"

    def detect(self, scores: list[Score]) -> list[Alert]:
        triggered = defaultdict(list)
        for s in scores:
            if s.z >= self.k:
                triggered[(s.window_start_ns, s.service)].append(s)
        return _alerts(triggered, self.name)


@dataclass(frozen=True)
class PersistenceDetector:
    k: float = 3.0
    windows: int = 3
    name: str = "persistence"

    def detect(self, scores: list[Score]) -> list[Alert]:
        series = defaultdict(list)
        for s in scores:
            series[(s.service, s.signal)].append(s)

        triggered = defaultdict(list)
        for run_scores in series.values():
            run, prev_start = 0, None
            for s in sorted(run_scores, key=lambda x: x.window_start_ns):
                adjacent = prev_start is not None and s.window_start_ns - prev_start == WINDOW_NS
                if s.z >= self.k:
                    run = run + 1 if adjacent or run == 0 else 1
                else:
                    run = 0
                prev_start = s.window_start_ns
                if run >= self.windows:
                    triggered[(s.window_start_ns, s.service)].append(s)
        return _alerts(triggered, self.name)
