# ADR-0003: Python standard library first; one runtime dependency

- Status: accepted
- Date: 2026-10-21

## Context

Archonix runs in users' development environments and CI, often next to the project being
analysed. Every dependency adds supply-chain and conflict risk.

## Decision

Python ≥ 3.11 (for `tomllib`). Use argparse, tomllib, urllib, ast, xml.etree,
concurrent.futures. Depend only on `jsonschema` for standards-compliant validation.
Scanners are optional external tools, never Python dependencies.

## Alternatives

Click/Typer (nicer CLI, extra dependency); PyYAML for config (TOML suffices);
defusedxml (JUnit XML is produced only after repository code is already trusted).

## Consequences

Some ergonomics are plainer. YAML OpenAPI documents need PyYAML installed separately.
