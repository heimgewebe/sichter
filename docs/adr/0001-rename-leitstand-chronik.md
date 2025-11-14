# ADR 0001: Rename leitstand to chronik and introduce leitstand UI

## Status

Proposed

## Context

The repository currently named `leitstand` serves as an event ingest, persistence, and audit system. This is functionally an event store or a chronicle of events.

A new UI/Dashboard is planned, which will provide a system overview and control room. This new component is semantically the actual "Leitstand" (German for control room).

This naming mismatch (backend being called control room) is confusing and hinders clarity in the system architecture.

## Decision

To align repository names with their semantic roles, we will perform the following restructuring:

1.  **Rename the Backend Repository**: The existing `heimgewebe/leitstand` repository will be renamed to `heimgewebe/chronik`. Its role is strictly defined as the event store.
2.  **Create a New UI Repository**: A new repository, `heimgewebe/leitstand`, will be created to house the new UI/Dashboard. This will be the central control room for the Heimgewebe ecosystem.

This change clarifies the distinction between the data backend (`chronik`) and the user-facing control plane (`leitstand`).

## Consequences

- **Pros**:
    - Aligns repository names with their actual function.
    - Improves architectural clarity and makes the system easier to understand for new contributors.
    - Separates concerns between the backend data layer and the frontend presentation layer.

- **Cons**:
    - Requires a coordinated renaming effort across all dependent repositories.
    - Potential for temporary disruption in CI/CD pipelines if not managed carefully.
    - All documentation, CI workflows, and internal references must be updated.
