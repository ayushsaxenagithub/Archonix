# ADR-0005: Readiness fails closed on missing evidence

- Status: accepted
- Date: 2026-10-21

## Context
A readiness tool that reports "ready" when a required check did not run, or ran zero
tests, gives false confidence.

## Decision
Rules evaluate to pass, fail or unknown. Missing reports, blocked/skipped/unparsed required
checks, unknown revision or working-tree state, zero tests and unknown severities are
`unknown`. Any fail → `not-ready`; otherwise any unknown → `incomplete`; only all-pass →
`ready`. An empty policy is `incomplete`.

## Consequences
Verdicts are conservative and may require extra evidence (for example, running from a
clean Git checkout). The verdict is never presented as a guarantee.
