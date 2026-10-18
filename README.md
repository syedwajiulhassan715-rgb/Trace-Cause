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
- [ ] 2. Load generator and fault injector
- [ ] 3. Span ingest and 10 s buckets
- [ ] 4. Self-time
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
```

| Component | Version |
|---|---|
| Java / Spring Boot | 21 / 4.1.1 |
| OpenTelemetry Java agent | 2.32.0 |
| OpenTelemetry Collector | 0.163.1 |
| Jaeger | 2.22.0 |
| Postgres | 17 |

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
