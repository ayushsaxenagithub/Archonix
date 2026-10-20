# Architecture documentation and diagrams

## Evidence labels

Every relationship is one of:

- **verified** — seen directly in source/config (an import, a route registration, a
  connection string key, a CI job)
- **inferred** — implied (a declared dependency, naming, conventions)
- **unknown** — could not be determined statically (dynamic imports, runtime config)

Link important elements to source paths in an evidence table under each diagram.

## Generated diagrams (CLI)

- `archonix architecture diagram .` — system context from the inventory: projects,
  declared data stores/caches/queues/integrations (dashed, inferred), CI/container/
  infrastructure configuration.
- `archonix architecture diagram . --python-package src/app` — module dependency graph
  from parsing Python with `ast` (no execution); static imports are verified edges,
  `importlib`/`__import__` calls are listed as unknown.

## Agent-assisted diagrams (templates)

Use Mermaid for: API request/response sequences, entity relationships, authentication
and authorization flows, background processing (queues, retries, schedules), business
state machines, deployment topology. Templates: `templates/architecture.md`,
`templates/data-flows.md`. Build them from code you have read, and label each edge.

Static inspection does not reveal every runtime dependency; say so.

## Decisions

Record significant decisions as ADRs (`templates/adr.md`): context, decision,
alternatives considered, consequences, status (proposed/accepted/superseded).
