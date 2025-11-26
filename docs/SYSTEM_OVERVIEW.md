# System Overview

This document outlines the high-level architecture of the Heimgewebe ecosystem and the roles of its core components.

## Core Components & Data Flow

1.  **Event Ingestion & Persistence (`chronik`)**
    -   **Repository**: `heimgewebe/chronik`
    -   **Role**: Acts as the central event store for the entire system. It ingests, persists, and provides an audit trail for all events, such as `aussen.event`, `os.context.*`, `policy.decision`, `review`, and `insight`.
    -   **Consumers**: Various tools and services within the ecosystem consume data from `chronik`.
