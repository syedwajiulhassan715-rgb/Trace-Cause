"""HTTP API: OTLP/HTTP JSON ingest from the Collector, and windowed per-service buckets."""

import json
import os
import time

from fastapi import FastAPI, HTTPException, Request

from .buckets import WINDOW_NS, bucketize, window_start
from .otlp import parse_export
from .store import SpanStore

S = 1_000_000_000


def create_app(store: SpanStore, clock_ns=time.time_ns) -> FastAPI:
    app = FastAPI(title="TraceCause analyzer")

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
        end = int(end_s * S) if end_s is not None else now
        start = int(start_s * S) if start_s is not None else end - 300 * S
        # Whole windows only: widen the range to window boundaries.
        start = window_start(start)
        end = window_start(end - 1) + WINDOW_NS
        out = []
        for b in bucketize(store.spans_between(start, end), now_ns=now):
            if service and b.service != service:
                continue
            out.append({
                "service": b.service,
                "window_start_s": b.window_start_ns // S,
                "requests": b.requests,
                "errors": b.errors,
                "error_rate": round(b.error_rate, 4),
                "mean_ms": b.mean_ms,
                "p50_ms": b.p50_ms,
                "p95_ms": b.p95_ms,
                "closed": b.closed,
            })
        return out

    @app.get("/health")
    def health():
        return {"status": "ok", "spans": store.count()}

    return app


def default_app() -> FastAPI:
    """Entry point for uvicorn: `uvicorn tracecause.app:default_app --factory`."""
    return create_app(SpanStore(os.environ.get("TRACECAUSE_DB", "/data/spans.db")))
