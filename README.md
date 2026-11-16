# TraceCause

Root-cause analysis on OpenTelemetry traces: find which service in a small
microservice system caused a slowdown, and explain it in plain language.

## Goal
Inject faults (slow query, error spike, added delay) into a demo microservice
system, detect the anomaly against a per-service baseline, and rank the most
likely root-cause service from the call graph. An LLM is used only to write the
explanation, never to decide.

## Status (work in progress)
- [x] 1. Demo services with OpenTelemetry tracing (Java)
- [x] 2. Load generator and fault injector
- [x] 3. Span ingest and 10 s buckets
- [x] 4. Self-time
- [ ] 5. Baselines and detectors
- [ ] 6. Root-cause ranking
- [ ] 7. Evaluation: top-1 / top-3 accuracy on injected faults
- [ ] 8. Dashboard (TypeScript/React)

## Architecture (so far)

```
client -> gateway -> orders -> inventory
                          \--> payments
          (orders, inventory, payments write to Postgres)

each service: OpenTelemetry Java agent --OTLP/HTTP--> Collector --OTLP/gRPC--> Jaeger
                                                                \--OTLP/HTTP JSON--> analyzer (Python)
```

| Component | Version |
|---|---|
| Java / Spring Boot | 21 / 4.1.1 |
| OpenTelemetry Java agent | 2.32.0 |
| OpenTelemetry Collector | 0.163.1 |
| Jaeger | 2.22.0 |
| Postgres | 17 |
| Analyzer | Python 3.13, FastAPI 0.163.1 |

## Analyzer

The Collector sends every span batch to the analyzer as OTLP JSON. The analyzer
stores spans in SQLite (one row per span, keyed by trace and span id, so a
retried batch is not counted twice) and groups each service's incoming
requests (its SERVER spans) into 10 s windows by start time.

```sh
curl localhost:8000/health
curl "localhost:8000/buckets?service=inventory"            # last 5 minutes
curl "localhost:8000/buckets?start_s=1794868650&end_s=1794868710"
```

Each bucket has `requests`, `errors`, `error_rate`, `mean_ms`, `p50_ms`, `p95_ms`
(nearest-rank), the self-time fields below, and `closed`. A window is closed 15 s after it ends; until then
late spans may still arrive, so detectors should only judge closed windows.
Calls to `/admin/fault` are dropped at ingest.

### Self-time

A slow service makes every service above it slow too, because they wait for
it. Total latency therefore points at the wrong place. Self-time removes the
waiting:

- **span self-time** = span duration minus the *union* of its children's time
  intervals, clipped to the span (concurrent calls are subtracted once, not twice);
- **request time** = for one incoming request (SERVER span), the self-time of
  every span that service made while handling it, split into
  `self` (its own code, including outgoing-call overhead) and `db` (its SQL calls).

Buckets report `self_p50_ms`, `self_p95_ms`, `db_p50_ms`, `db_p95_ms`. Measured on
the running stack (p50 per 10 s window, ms):

| Phase | gateway total / self | orders total / self | inventory self / db | payments self / db |
|---|---|---|---|---|
| no fault | 21 / 2.5 | 19 / 4.6 | 1.0 / 2.9 | 1.0 / 2.9 |
| inventory `delayMs=200` | 223 / 2.6 | 220 / 4.9 | **201** / 3.1 | 1.0 / 3.0 |
| payments `slowQueryMs=300` | 321 / 2.2 | 319 / 4.1 | 0.9 / 2.9 | 1.0 / **304** |

## Load and faults

Every service has an admin endpoint, `/admin/fault`, that sets one fault:

| Fault | What it does | Where it shows in the trace |
|---|---|---|
| `delayMs` | sleeps inside the request handler | the service's own (self) time |
| `slowQueryMs` | runs `pg_sleep` before each SQL statement | a slow database span in that service |
| `errorRate` | answers HTTP 500 with this probability (seeded) | error status on that service's span, 502 upstream |

Nothing about the fault is written into the trace, so the analyzer has to find it.
Host ports: gateway 8080, orders 8081, inventory 8082, payments 8083.

```sh
python -m loadgen.load --rate 20 --duration 60 --seed 1     # seeded open-loop load
python -m loadgen.faults set inventory --delay-ms 200
python -m loadgen.faults set payments --error-rate 0.3 --seed 7
python -m loadgen.faults show
python -m loadgen.faults clear                               # all services
```

The load generator is open loop: requests go out on a fixed Poisson schedule
whether or not earlier ones are done, so a slowdown is not hidden by the client
backing off.

## Run

Requires Docker. No local JDK is needed; services build inside Docker.

```sh
docker compose up -d --build
curl -X POST localhost:8080/checkout -H "Content-Type: application/json" \
     -d '{"sku":"SKU-1","quantity":2}'
```

Jaeger UI: http://localhost:16686

The compose file has local-only default credentials. To override them, copy
`.env.example` to `.env`.

## Tests

Service unit tests (Maven in Docker):

```sh
docker run --rm -v "$PWD/services":/src -v tracecause-m2:/root/.m2 -w /src \
    maven:3.9-eclipse-temurin-21 mvn -B test
```

End-to-end tracing check (stack must be running; Python 3, stdlib only):

```sh
python scripts/smoke_test.py
```

Analyzer tests (Python 3.13):

```sh
cd analyzer
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # bin/ on Linux/macOS
.venv/Scripts/python -m pytest -q
```

Load generator and fault-injector tests (Python 3, stdlib only):

```sh
python -m unittest discover -s loadgen/tests -t .
```
