"""HTTP API: OTLP/HTTP JSON ingest from the Collector, windowed buckets, and anomalies."""

import json
import os
import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Request

from .buckets import WINDOW_NS, Bucket, bucketize, window_start
from .detect import PersistenceDetector, ThresholdDetector, score_series
from .otlp import parse_export
from .store import SpanStore

S = 1_000_000_000
HISTORY_WINDOWS = 30
DETECTORS = {"threshold": ThresholdDetector(), "persistence": PersistenceDetector()}


def create_app(store: SpanStore, clock_ns=time.time_ns) -> FastAPI:
    app = FastAPI(title="TraceCause analyzer")

    def window_range(start_s, end_s, now):
        """Whole windows covering [start_s, end_s); default: the last 5 minutes."""
        end = int(end_s * S) if end_s is not None else now
        start = int(start_s * S) if start_s is not None else end - 300 * S
        return window_start(start), window_start(end - 1) + WINDOW_NS

    def load_buckets(start, end, now) -> list[Bucket]:
        # Whole traces may reach into neighbouring windows; keep only the requested ones.
        return [b for b in bucketize(store.traces_between(start, end), now_ns=now)
                if start <= b.window_start_ns < end]

    @app.post("/v1/traces")
    async def ingest(request: Request):
        # OTLP/HTTP: the Collector's otlp_http exporter (encoding: json) posts here.
        # A 400 tells it the batch is bad and must not be retried.
        try:
            spans = parse_export(json.loads(await request.body()))
        except (ValueError, KeyError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f"bad OTLP payload: {e}")
        store.add(spans)
        return {}  # an empty ExportTraceServiceResponse means full success

    @app.get("/buckets")
    def buckets(start_s: float | None = None, end_s: float | None = None, service: str | None = None):
        now = clock_ns()
        start, end = window_range(start_s, end_s, now)
        return [{
            "service": b.service,
            "window_start_s": b.window_start_ns // S,
            "requests": b.requests,
            "errors": b.errors,
            "error_rate": round(b.error_rate, 4),
            "mean_ms": b.mean_ms,
            "p50_ms": b.p50_ms,
            "p95_ms": b.p95_ms,
            "self_p50_ms": b.self_p50_ms,
            "self_p95_ms": b.self_p95_ms,
            "db_p50_ms": b.db_p50_ms,
            "db_p95_ms": b.db_p95_ms,
            "closed": b.closed,
        } for b in load_buckets(start, end, now) if not service or b.service == service]

    @app.get("/anomalies")
    def anomalies(detector: Literal["threshold", "persistence"] = "persistence",
                  start_s: float | None = None, end_s: float | None = None):
        now = clock_ns()
        start, end = window_range(start_s, end_s, now)
        # The baseline needs the windows before the range, not just the range itself.
        history = load_buckets(start - HISTORY_WINDOWS * WINDOW_NS, end, now)
        scores = score_series(history, history=HISTORY_WINDOWS)
        return [{
            "service": a.service,
            "window_start_s": a.window_start_ns // S,
            "detector": a.detector,
            "evidence": [{"signal": e.signal, "value": e.value, "median": e.median,
                          "scale": round(e.scale, 4), "z": e.z} for e in a.evidence],
        } for a in DETECTORS[detector].detect(scores) if start <= a.window_start_ns < end]

    @app.get("/health")
    def health():
        return {"status": "ok", "spans": store.count()}

    return app


def default_app() -> FastAPI:
    """Entry point for uvicorn: `uvicorn tracecause.app:default_app --factory`."""
    return create_app(SpanStore(os.environ.get("TRACECAUSE_DB", "/data/spans.db")))
