"""Self-time: how much of a request's time a service spent itself, not waiting on others.

Span self-time = span duration minus the union of its children's intervals,
with children clipped to the parent. Using the union (not the sum) matters
when a span makes concurrent calls: their overlap must only be subtracted once.

Request time = for one SERVER span (one incoming request), add up the self-time
of every span this service produced while handling it, stopping where another
request begins (a SERVER span, usually in another service). That total is split:
- own_ns: the service's code, including the overhead of its outgoing calls
- db_ns:  its database client spans (they have no children, so self = duration)

Errors are attributed the same way. An error propagates up: when payments
fails, orders and gateway fail too. A failed request is an *own error* only if
none of the downstream requests it made (the SERVER spans it reached) failed.
If the downstream request never produced a span (connection refused), the
caller owns the error, because that is all the trace shows.

If a child span is missing (never arrived), its time stays with the parent:
we cannot attribute what we did not see. Analysing closed windows only keeps
this rare.
"""

from collections import defaultdict
from dataclasses import dataclass

from .otlp import Span

Key = tuple[str, str]  # (trace_id, span_id)


@dataclass(frozen=True)
class RequestTime:
    service: str
    trace_id: str
    span_id: str
    start_ns: int
    own_ns: int
    db_ns: int
    error: bool
    own_error: bool


def union_ns(intervals) -> int:
    total, cur_start, cur_end = 0, None, None
    for start, end in sorted(intervals):
        if cur_end is None or start > cur_end:
            if cur_end is not None:
                total += cur_end - cur_start
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    if cur_end is not None:
        total += cur_end - cur_start
    return total


def _children(spans: list[Span]) -> dict[Key, list[Span]]:
    kids = defaultdict(list)
    for s in spans:
        if s.parent_id:
            kids[(s.trace_id, s.parent_id)].append(s)
    return kids


def self_times(spans: list[Span]) -> dict[Key, int]:
    kids = _children(spans)
    out = {}
    for s in spans:
        clipped = []
        for c in kids.get((s.trace_id, s.span_id), []):
            start, end = max(c.start_ns, s.start_ns), min(c.end_ns, s.end_ns)
            if end > start:
                clipped.append((start, end))
        out[(s.trace_id, s.span_id)] = s.duration_ns - union_ns(clipped)
    return out


def request_times(spans: list[Span]) -> list[RequestTime]:
    kids = _children(spans)
    st = self_times(spans)
    out = []
    for root in spans:
        if root.kind != "SERVER":
            continue
        own = db = 0
        downstream_failed = False
        stack = [root]
        while stack:
            s = stack.pop()
            t = st[(s.trace_id, s.span_id)]
            if s.is_db:
                db += t
            else:
                own += t
            for c in kids.get((s.trace_id, s.span_id), []):
                if c.kind == "SERVER":  # another request; it gets its own entry
                    downstream_failed |= c.error
                else:
                    stack.append(c)
        out.append(RequestTime(root.service, root.trace_id, root.span_id, root.start_ns, own, db,
                               error=root.error, own_error=root.error and not downstream_failed))
    return out
