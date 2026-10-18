"""End-to-end check for build step 1: one checkout produces one trace spanning all services.

Run after `docker compose up -d --build`:
    python scripts/smoke_test.py
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

GATEWAY = "http://localhost:8080"
JAEGER = "http://localhost:16686"
EXPECTED_SERVICES = {"gateway", "orders", "inventory", "payments"}
DB_SERVICES = {"orders", "inventory", "payments"}


def http(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read() or b"null")


def retry(fn, what, timeout_s=180, every_s=3):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        try:
            result = fn()
            if result:
                return result
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            last = e
        time.sleep(every_s)
    sys.exit(f"FAIL: timed out waiting for {what} (last error: {last})")


def checkout():
    status, body = http("POST", f"{GATEWAY}/checkout", {"sku": "SKU-2", "quantity": 2})
    return body if status == 200 else None


def is_db_span(span):
    keys = {a["key"] for a in span.get("attributes", [])}
    return "db.system.name" in keys or "db.system" in keys


def rfc3339(t):
    return t.isoformat().replace("+00:00", "Z")


def find_full_trace():
    """Query Jaeger's stable api_v3 (OTLP JSON) and return {service: [spans]} for a complete trace."""
    now = datetime.now(timezone.utc)
    query = urllib.parse.urlencode({
        "query.serviceName": "gateway",
        "query.startTimeMin": rfc3339(now - timedelta(hours=1)),
        "query.startTimeMax": rfc3339(now),
        "query.searchDepth": "50",
    })
    _, body = http("GET", f"{JAEGER}/api/v3/traces?{query}")
    traces = {}
    for rs in body["result"]["resourceSpans"]:
        service = next(a["value"]["stringValue"] for a in rs["resource"]["attributes"]
                       if a["key"] == "service.name")
        for ss in rs["scopeSpans"]:
            for span in ss["spans"]:
                traces.setdefault(span["traceId"], {}).setdefault(service, []).append(span)
    for trace_id, by_service in traces.items():
        if EXPECTED_SERVICES <= by_service.keys():
            return trace_id, by_service
    return None


def main():
    order = retry(checkout, "gateway to accept a checkout")
    print(f"checkout ok: {order}")
    assert order["status"] == "CONFIRMED", order
    assert order["amountCents"] == 2 * 1299, order

    trace_id, by_service = retry(find_full_trace, "a trace covering all four services in Jaeger",
                                 timeout_s=60)

    print(f"trace {trace_id}: {sum(map(len, by_service.values()))} spans")
    for svc in sorted(by_service):
        names = sorted({s["name"] for s in by_service[svc]})
        print(f"  {svc:10s} {len(by_service[svc]):3d} spans  {names}")

    missing_db = [svc for svc in DB_SERVICES if not any(is_db_span(s) for s in by_service[svc])]
    if missing_db:
        sys.exit(f"FAIL: no database spans for {missing_db}")

    print("PASS: one trace spans gateway -> orders -> inventory/payments, with DB spans")


if __name__ == "__main__":
    main()
