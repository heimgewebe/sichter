# ADR 0001: Rename leitstand to chronik

## Status

Accepted

## Context

The repository formerly named `leitstand` served as an event ingest, persistence, and audit system. This is functionally an event store or a chronicle of events.

This naming (backend being called control room) was confusing and hindered clarity in the system architecture.

## Decision

The backend repository has been renamed from `heimgewebe/leitstand` to `heimgewebe/chronik`. Its role is strictly defined as the event store.

## Consequences

- **Pros**:
    - Aligns repository name with its actual function.
    - Improves architectural clarity and makes the system easier to understand for new contributors.
