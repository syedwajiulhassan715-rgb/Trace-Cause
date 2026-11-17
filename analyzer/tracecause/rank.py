"""Rank services by how likely they are to be the root cause of an incident.

An incident is the set of windows in which a detector fired. For each service
and incident window, take its strongest signal (the highest z among self_ms,
db_ms and own_error_rate). The service's score is the median of that over the
incident windows; a window where the service has no score counts as 0. The
median means one odd window cannot decide the ranking.

Most of the "who caused it" work already happened before ranking: self-time
and own errors remove what a service only inherited from its callees. Ranking
then mostly sorts by score. The call graph breaks ties: with equal evidence,
the service further downstream ranks first, because a problem deep in the call
chain shows up in everything that calls it, never the other way round.

Everything here is deterministic: same spans in, same ranking out.
"""

import statistics
from collections import defaultdict
from dataclasses import dataclass

from .buckets import WINDOW_NS
from .detect import Score
from .otlp import Span


@dataclass(frozen=True)
class Candidate:
    service: str
    score: float   # median over incident windows of the strongest z
    signal: str    # the signal behind most of that score
    depth: int     # call-graph distance from the entry service (gateway = 0)


def call_graph(spans: list[Span]) -> set[tuple[str, str]]:
    """Edges caller -> callee: a SERVER span whose parent span belongs to another service."""
    by_key = {(s.trace_id, s.span_id): s for s in spans}
    edges = set()
    for s in spans:
        if s.kind == "SERVER" and s.parent_id:
            parent = by_key.get((s.trace_id, s.parent_id))
            if parent and parent.service != s.service:
                edges.add((parent.service, s.service))
    return edges


def depths(edges: set[tuple[str, str]]) -> dict[str, int]:
    """Shortest call distance from an entry service (one nobody calls). Cycles are safe."""
    services = {a for a, _ in edges} | {b for _, b in edges}
    callees = defaultdict(set)
    for a, b in edges:
        callees[a].add(b)
    roots = services - {b for _, b in edges} or set(sorted(services)[:1])
    depth = {r: 0 for r in roots}
    frontier = sorted(roots)
    while frontier:
        nxt = []
        for a in frontier:
            for b in sorted(callees[a]):
                if b not in depth:
                    depth[b] = depth[a] + 1
                    nxt.append(b)
        frontier = nxt
    for s in services:  # unreachable members of a cycle
        depth.setdefault(s, 0)
    return depth


def incidents(alert_windows: set[int], max_gap_windows: int = 3) -> list[set[int]]:
    """Split alert windows into incidents, oldest first.

    Up to `max_gap_windows` quiet windows (30 s by default) inside an incident
    are allowed, since a detector can flicker; a longer quiet period starts a new
    incident. Without this, two unrelated faults in one time range would be
    ranked as one.
    """
    out: list[set[int]] = []
    prev = None
    for w in sorted(alert_windows):
        if prev is None or (w - prev) // WINDOW_NS - 1 > max_gap_windows:
            out.append(set())
        out[-1].add(w)
        prev = w
    return out


def rank(scores: list[Score], incident_windows: set[int], edges: set[tuple[str, str]]) -> list[Candidate]:
    if not incident_windows:
        return []
    best = defaultdict(dict)           # service -> window -> (z, signal)
    per_signal = defaultdict(lambda: defaultdict(list))  # service -> signal -> [z per window]
    for s in scores:
        if s.window_start_ns not in incident_windows:
            continue
        cur = best[s.service].get(s.window_start_ns)
        if cur is None or (s.z, s.signal) > cur:
            best[s.service][s.window_start_ns] = (s.z, s.signal)
        per_signal[s.service][s.signal].append(s.z)

    depth = depths(edges)
    windows = sorted(incident_windows)
    out = []
    for service, by_window in best.items():
        score = statistics.median(by_window.get(w, (0.0, ""))[0] for w in windows)
        signal = max(per_signal[service].items(),
                     key=lambda kv: (statistics.median(kv[1] + [0.0] * (len(windows) - len(kv[1]))), kv[0]))[0]
        out.append(Candidate(service, round(score, 4), signal, depth.get(service, 0)))
    return sorted(out, key=lambda c: (-c.score, -c.depth, c.service))
