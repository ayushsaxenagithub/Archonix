# {{project}} — Architecture

Last updated: {{date}}

Edge labels: **verified** (seen in code/config), **inferred** (implied by dependencies or
conventions), **unknown** (not determinable statically).

## System context
```mermaid
flowchart LR
  user([User]) --> app[Application]
  app -. "inferred" .-> db[(Database)]
```

## Components
| Component | Responsibility | Path | Depends on | Evidence status |
|---|---|---|---|---|

## Request flow
```mermaid
sequenceDiagram
  participant Client
  participant API
  participant DB
  Client->>API: request
  API->>DB: query
  DB-->>API: rows
  API-->>Client: response
```

## Authentication and authorization

## Background processing
<!-- Queues, retries, schedules, idempotency -->

## Deployment topology

## Evidence
| Element | Relationship | Status | Source |
|---|---|---|---|
