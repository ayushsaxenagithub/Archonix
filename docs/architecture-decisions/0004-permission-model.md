# ADR-0004: Independent permissions; repository config is restrict-only

- Status: accepted
- Date: 2026-10-21

## Context
Running a scanner, running tests and calling a network service carry different risks.
Repositories are untrusted input: a malicious `archonix.toml` must not be able to make
Archonix run its code or leak credentials.

## Decision
Eight independent permissions; modes only supply defaults. Each adapter declares what it
needs, and the planner blocks checks whose needs are not permitted. Repository config may
only disable permissions and may not set environment passthrough or tool arguments. User
config, `--config` and CLI flags are trusted.

## Alternatives
A single "safe mode" flag (too coarse); trusting repository config (unsafe).

## Consequences
Users must opt in explicitly to test execution and network checks. Ignored repository
settings are reported so the behaviour is visible.
