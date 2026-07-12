# ADR 0001: Adopt a Modular Monolith

## Status

Accepted

## Context

BoardTrace needs capture ingestion, computer vision, engine analysis, report generation, persistence, and strict fair-play controls. It is early-stage and benefits from consistent controls and low operational overhead.

## Decision

Build a modular monolith with explicit capture, games, vision, engine analysis, reports, storage, and audit boundaries. Keep one backend codebase and coordinated deployment model; independently scalable workers do not imply early microservices.

## Consequences

- Security rules and state transitions are enforced consistently.
- Development, testing, deployment, and observability remain simpler.
- Internal interfaces require discipline to prevent coupling.
- Future extraction requires intentional contracts and migration work.

## Alternatives considered

- **Microservices from the start**: rejected due to premature deployment, tracing, authorization, schema, and consistency complexity.
- **Unstructured monolith**: rejected because it weakens security boundaries and future extraction.
- **Client-side engine analysis**: rejected because it violates the live-analysis lock.

## Conditions for future service extraction

Extract only with evidence of independent sustained scaling, clear ownership, isolated release cadence, specialized runtime needs, or a proven reliability bottleneck. First define a stable contract, data ownership, authorization, observability, failure handling, and migration path while preserving the live-analysis lock.
