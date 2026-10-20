# ADR-0001: Record decisions; version schemas from 0.1

- Status: accepted
- Date: 2026-10-21

## Context

Archonix emits JSON consumed by people, assistants and CI. Consumers need a stable
contract, and maintainers need to remember why choices were made.

## Decision

Keep decision records here. Every Archonix JSON document carries `schema_version` (starting
at `0.1`) and, for top-level documents, a `kind` used to infer the schema. Findings and
execution records are embedded in workflow reports rather than stored separately.

## Alternatives

Unversioned output (breaks consumers silently); a separate file per finding (harder to
keep consistent with the run that produced it).

## Consequences

Incompatible schema changes require a version bump and an ADR. Validation can infer
schemas automatically.
