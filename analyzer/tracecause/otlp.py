"""Turn an OTLP/JSON ExportTraceServiceRequest into flat Span rows.

OTLP JSON details handled here (OTLP spec, JSON protobuf encoding):
- traceId/spanId are hex strings; an absent or empty parentSpanId means a root span.
- 64-bit integers (timestamps, intValue) arrive as strings.
- enums (span kind, status code) arrive as integers.
"""

from dataclasses import dataclass

KINDS = {0: "UNSPECIFIED", 1: "INTERNAL", 2: "SERVER", 3: "CLIENT", 4: "PRODUCER", 5: "CONSUMER"}
STATUS_ERROR = 2


@dataclass(frozen=True)
class Span:
    trace_id: str
    span_id: str
    parent_id: str | None
    service: str
    name: str
    kind: str
    start_ns: int
    end_ns: int
    error: bool
    route: str | None
    is_db: bool

    @property
    def duration_ns(self) -> int:
        return self.end_ns - self.start_ns

    @property
    def is_admin(self) -> bool:
        """Fault-injector control calls; never part of the workload we analyse."""
        return (self.route or "").startswith("/admin/")


def _value(v):
    for key in ("stringValue", "boolValue", "doubleValue"):
        if key in v:
            return v[key]
    if "intValue" in v:
        return int(v["intValue"])
    return None


def _attrs(items):
    return {a["key"]: _value(a.get("value", {})) for a in items or []}


def parse_export(body: dict) -> list[Span]:
    out = []
    for rs in body.get("resourceSpans", []):
        service = _attrs(rs.get("resource", {}).get("attributes")).get("service.name") or "unknown"
        for ss in rs.get("scopeSpans", []):
            for s in ss.get("spans", []):
                attrs = _attrs(s.get("attributes"))
                out.append(Span(
                    trace_id=s["traceId"],
                    span_id=s["spanId"],
                    parent_id=s.get("parentSpanId") or None,
                    service=service,
                    name=s.get("name", ""),
                    kind=KINDS.get(int(s.get("kind", 0)), "UNSPECIFIED"),
                    start_ns=int(s["startTimeUnixNano"]),
                    end_ns=int(s["endTimeUnixNano"]),
                    error=int(s.get("status", {}).get("code", 0)) == STATUS_ERROR,
                    route=attrs.get("http.route"),
                    is_db="db.system.name" in attrs or "db.system" in attrs,
                ))
    return out
