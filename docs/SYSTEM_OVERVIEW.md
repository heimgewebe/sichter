# System Overview

This document outlines the high-level architecture of the Heimgewebe ecosystem and the roles of its core components.

## Core Components & Data Flow

1.  **Event Ingestion & Persistence (`chronik`)**
    -   **Repository**: `heimgewebe/chronik` (formerly `heimgewebe/leitstand`)
    -   **Role**: Acts as the central event store for the entire system. It ingests, persists, and provides an audit trail for all events, such as `aussen.event`, `os.context.*`, `policy.decision`, `review`, and `insight`.
    -   **Consumers**: Various tools and services within the ecosystem consume data from `chronik`.

2.  **UI/Dashboard (`leitstand`)**
    -   **Repository**: `heimgewebe/leitstand` (New, Planned)
    -   **Role**: Serves as the primary user interface and control room for the ecosystem. It provides dashboards, visualizations, and system overviews.
    -   **Data Sources**: This UI will read data from `chronik`, `semantAH`, and `hausKI` to provide a comprehensive view of the system's state and activity.

This clear separation ensures that the backend data layer (`chronik`) is decoupled from the frontend presentation layer (`leitstand`), improving modularity and clarity.
