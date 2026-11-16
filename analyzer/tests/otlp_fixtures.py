"""Hand-built OTLP JSON payloads, shaped like what the Collector's otlp_http exporter sends."""


def attr(key, value):
    if isinstance(value, bool):
        v = {"boolValue": value}
    elif isinstance(value, int):
        v = {"intValue": str(value)}  # OTLP JSON encodes int64 as a string
    else:
        v = {"stringValue": value}
    return {"key": key, "value": v}


def span(trace_id, span_id, name, start_ns, end_ns, parent=None, kind=2, status=0, attrs=()):
    s = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "kind": kind,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": [attr(k, v) for k, v in attrs],
        "status": {"code": status} if status else {},
    }
    if parent:
        s["parentSpanId"] = parent
    return s


def export(*by_service):
    """export(("gateway", [span, ...]), ("orders", [...]))"""
    return {"resourceSpans": [
        {"resource": {"attributes": [attr("service.name", svc)]},
         "scopeSpans": [{"scope": {"name": "test"}, "spans": spans}]}
        for svc, spans in by_service
    ]}
