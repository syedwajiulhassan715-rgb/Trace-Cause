"""Group spans into fixed 10 s windows per service.

A request to a service is that service's SERVER span. Each span goes in the
window that contains its start time. Database and outgoing-call spans are not
requests; they feed each request's self-time and DB time (see selftime.py).
Pass whole traces in, so every request's children are present.
"""

import math
from collections import defaultdict
from dataclasses import dataclass

from .otlp import Span
from .selftime import request_times

WINDOW_NS = 10 * 1_000_000_000
# A window is "closed" once spans for it can no longer realistically arrive:
# requests time out after 30 s at most, but our workload's p99 is far below 15 s,
# and the Collector batches for well under a second.
GRACE_NS = 15 * 1_000_000_000
MS = 1_000_000


@dataclass(frozen=True)
class Bucket:
    service: str
    window_start_ns: int
    requests: int
    errors: int
    own_errors: int     # errors that started here, not in a downstream service (see selftime.py)
    mean_ms: float
    p50_ms: float
    p95_ms: float
    self_p50_ms: float  # time in the service's own code (excludes downstream services and DB)
    self_p95_ms: float
    db_p50_ms: float    # time in the service's database calls
    db_p95_ms: float
    closed: bool

    @property
    def error_rate(self) -> float:
        return self.errors / self.requests if self.requests else 0.0

    @property
    def own_error_rate(self) -> float:
        return self.own_errors / self.requests if self.requests else 0.0


def window_start(ns: int, width_ns: int = WINDOW_NS) -> int:
    return ns - ns % width_ns


def percentile(sorted_values, p):
    """Nearest-rank percentile: always an observed value, deterministic, no interpolation."""
    rank = max(1, math.ceil(p * len(sorted_values)))
    return sorted_values[rank - 1]


def _ms_percentiles(values_ns):
    v = sorted(x / MS for x in values_ns)
    return round(percentile(v, 0.50), 3), round(percentile(v, 0.95), 3)


def bucketize(spans: list[Span], now_ns: int, width_ns: int = WINDOW_NS, grace_ns: int = GRACE_NS) -> list[Bucket]:
    rt = {(r.trace_id, r.span_id): r for r in request_times(spans)}
    groups = defaultdict(list)
    for s in spans:
        if s.kind == "SERVER" and not s.is_admin:
            groups[(window_start(s.start_ns, width_ns), s.service)].append(s)

    out = []
    for (start, service), group in sorted(groups.items()):
        durations = sorted(s.duration_ns / MS for s in group)
        times = [rt[(s.trace_id, s.span_id)] for s in group]
        self_p50, self_p95 = _ms_percentiles(t.own_ns for t in times)
        db_p50, db_p95 = _ms_percentiles(t.db_ns for t in times)
        out.append(Bucket(
            service=service,
            window_start_ns=start,
            requests=len(group),
            errors=sum(s.error for s in group),
            own_errors=sum(t.own_error for t in times),
            mean_ms=round(sum(durations) / len(durations), 3),
            p50_ms=round(percentile(durations, 0.50), 3),
            p95_ms=round(percentile(durations, 0.95), 3),
            self_p50_ms=self_p50,
            self_p95_ms=self_p95,
            db_p50_ms=db_p50,
            db_p95_ms=db_p95,
            closed=start + width_ns + grace_ns <= now_ns,
        ))
    return out
