"""SQLite span store. One row per span; (trace_id, span_id) is the key, so Collector retries are harmless."""

import sqlite3
import threading

from .otlp import Span

_COLUMNS = ("trace_id", "span_id", "parent_id", "service", "name", "kind",
            "start_ns", "end_ns", "error", "route", "is_db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS spans (
    trace_id  TEXT    NOT NULL,
    span_id   TEXT    NOT NULL,
    parent_id TEXT,
    service   TEXT    NOT NULL,
    name      TEXT    NOT NULL,
    kind      TEXT    NOT NULL,
    start_ns  INTEGER NOT NULL,
    end_ns    INTEGER NOT NULL,
    error     INTEGER NOT NULL,
    route     TEXT,
    is_db     INTEGER NOT NULL,
    PRIMARY KEY (trace_id, span_id)
);
CREATE INDEX IF NOT EXISTS spans_start ON spans (start_ns);
"""


def _row_to_span(row) -> Span:
    d = dict(zip(_COLUMNS, row))
    d["error"] = bool(d["error"])
    d["is_db"] = bool(d["is_db"])
    return Span(**d)


class SpanStore:

    def __init__(self, path: str):
        # FastAPI runs sync endpoints in a thread pool; one connection guarded by a lock is enough here.
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(_SCHEMA)

    def add(self, spans: list[Span]) -> int:
        """Store spans, dropping fault-injector admin calls. Returns how many were new."""
        rows = [tuple(getattr(s, c) for c in _COLUMNS) for s in spans if not s.is_admin]
        with self._lock, self._db:
            before = self._db.total_changes
            self._db.executemany(
                f"INSERT OR IGNORE INTO spans ({', '.join(_COLUMNS)}) VALUES ({', '.join('?' * len(_COLUMNS))})",
                rows)
            return self._db.total_changes - before

    def spans_between(self, start_ns: int, end_ns: int) -> list[Span]:
        """Spans whose start time is in [start_ns, end_ns)."""
        return self._query("WHERE start_ns >= ? AND start_ns < ? ORDER BY start_ns, span_id", (start_ns, end_ns))

    def traces_between(self, start_ns: int, end_ns: int) -> list[Span]:
        """Every span of every trace that has a span starting in [start_ns, end_ns).

        Self-time needs a request's children even when they start after the window ends.
        """
        return self._query(
            "WHERE trace_id IN (SELECT DISTINCT trace_id FROM spans WHERE start_ns >= ? AND start_ns < ?)"
            " ORDER BY start_ns, span_id", (start_ns, end_ns))

    def trace(self, trace_id: str) -> list[Span]:
        return self._query("WHERE trace_id = ? ORDER BY start_ns, span_id", (trace_id,))

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM spans").fetchone()[0]

    def _query(self, where: str, params) -> list[Span]:
        with self._lock:
            rows = self._db.execute(f"SELECT {', '.join(_COLUMNS)} FROM spans {where}", params).fetchall()
        return [_row_to_span(r) for r in rows]
