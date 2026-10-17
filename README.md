# TraceCause

Root-cause analysis on OpenTelemetry traces: find which service in a small
microservice system caused a slowdown, and explain it in plain language.

## Goal
Inject faults (slow query, error spike, added delay) into a demo microservice
system, detect the anomaly against a per-service baseline, and rank the most
likely root-cause service from the call graph. An LLM is used only to write the
explanation, never to decide.

## Status (work in progress)
- [ ] Demo services with OpenTelemetry tracing (Java)
- [ ] Fault injector
- [ ] Trace storage and queries
- [ ] Baseline anomaly detector
- [ ] Root-cause ranking
- [ ] Evaluation: top-1 / top-3 accuracy on N injected faults
- [ ] Dashboard (TypeScript/React)

## Planned stack
Java, OpenTelemetry, Docker Compose, Postgres, TypeScript/React
