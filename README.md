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
- [x] 5. Baselines and detectors
- [x] 6. Root-cause ranking
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

### Baselines and detectors

Each closed window of a service is scored on three signals: `self_ms`
(`self_p50_ms`), `db_ms` (`db_p50_ms`) and `own_error_rate`. An error is the
service's *own* only if none of the downstream requests it made failed, so a
failure in payments is not also counted against orders and gateway. The baseline is that
service's previous 30 windows (at least 6; windows with fewer than 5 requests,
such as JVM warm-up, are skipped). The score is a one-sided robust z-score:

```
z = (value - median) / max(1.4826 * MAD, floor)      floor: 1 ms, or 0.02 for error rate
```

Median and MAD are not dragged around by a few outliers. The floor stops a very
steady signal from turning a tiny wobble into a huge z.

| Detector | Fires when | Trade-off |
|---|---|---|
| `threshold` (naive) | any signal has z >= 3 in one window | fast, but one noisy window is enough |
| `persistence` | the same signal has z >= 3 in 3 consecutive windows | ignores short spikes, alerts 20 s later |

```sh
curl "localhost:8000/anomalies?detector=threshold"
curl "localhost:8000/anomalies?detector=persistence&start_s=...&end_s=..."
```

Each alert lists its evidence: signal, value, baseline median, scale and z.
These parameters are defaults; they will be tuned on the tuning scenarios only
(step 7), and accuracy will be reported on held-out scenarios.

### Root-cause ranking

An incident is the set of windows in which the chosen detector fired. For each
service, take its strongest signal z in each incident window; the service's
score is the median of those over the incident (a missing window counts as 0).
On equal scores the more downstream service in the call graph (built from the
spans) ranks first. The ranking is deterministic.

```sh
curl "localhost:8000/rootcause?detector=persistence&start_s=...&end_s=..."
```

Most of the attribution happens before ranking: self-time removes the waiting a
service inherits from its callees, and own errors remove the failures it only
passed on. Example from one manual run (20 req/s, one 40 s fault per phase;
this is a demonstration, not the evaluation):

| Fault | Rank 1 (both detectors) | Signal | Other services |
|---|---|---|---|
| inventory `delayMs=150` | inventory | `self_ms` | z <= 0.15 |
| payments `errorRate=0.3` | payments | `own_error_rate` | z = 0 |
| orders `slowQueryMs=100` | orders | `db_ms` | z <= 0.05 |

During the payments error fault, orders and gateway reported the same number
of errors as payments (53 in one window), but all 53 were payments' own.

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
