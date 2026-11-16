"""Group spans into fixed 10 s windows per service.

A request to a service is that service's SERVER span. Each span goes in the
window that contains its start time. Database and outgoing-call spans are not
requests; step 4 (self-time) uses them to split time between services.
"""

import math
from collections import defaultdict
from dataclasses import dataclass

from .otlp import Span

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
    mean_ms: float
    p50_ms: float
    p95_ms: float
    closed: bool

    @property
    def error_rate(self) -> float:
        return self.errors / self.requests if self.requests else 0.0


def window_start(ns: int, width_ns: int = WINDOW_NS) -> int:
    return ns - ns % width_ns


def percentile(sorted_values, p):
    """Nearest-rank percentile: always an observed value, deterministic, no interpolation."""
    rank = max(1, math.ceil(p * len(sorted_values)))
    return sorted_values[rank - 1]


def bucketize(spans: list[Span], now_ns: int, width_ns: int = WINDOW_NS, grace_ns: int = GRACE_NS) -> list[Bucket]:
    groups = defaultdict(list)
    for s in spans:
        if s.kind == "SERVER" and not s.is_admin:
            groups[(window_start(s.start_ns, width_ns), s.service)].append(s)

    out = []
    for (start, service), group in sorted(groups.items()):
        durations = sorted(s.duration_ns / MS for s in group)
        out.append(Bucket(
            service=service,
            window_start_ns=start,
            requests=len(group),
            errors=sum(s.error for s in group),
            mean_ms=round(sum(durations) / len(durations), 3),
            p50_ms=percentile(durations, 0.50),
            p95_ms=percentile(durations, 0.95),
            closed=start + width_ns + grace_ns <= now_ns,
        ))
    return out
