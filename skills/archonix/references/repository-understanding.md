# Repository understanding

Goal: an accurate, evidence-backed picture of the codebase before changing it.

## Steps

1. **Bound the scope.** Confirm the root path (and sub-projects if a monorepo). Skip
   generated files, dependencies, caches, build output and binaries. Do not follow
   symlinks outside the root.
2. **Inventory without executing.** Run `archonix inventory . --format md` if available.
   Otherwise read manifests (`pyproject.toml`, `requirements*.txt`, `package.json`,
   lockfiles, `go.mod`, …), CI files, container and infrastructure files.
3. **Map the structure.** Identify entry points (CLI mains, servers, handlers, workers,
   scheduled jobs), frontend vs backend boundaries, API style and specs, data stores and
   migrations, queues and background jobs, authentication and external integrations.
4. **Find the quality gates.** Test frameworks and locations, linters, formatters, type
   checkers, CI jobs and release configuration.
5. **Record evidence.** For each claim note the file path(s). Mark relationships that are
   only implied by declared dependencies as *inferred*.
6. **Note unknowns.** Runtime configuration (env vars, feature flags, platform settings)
   is often invisible statically. List what would need confirmation.

## Output

A concise summary (purpose, stack, structure, how to build/test, risks), optionally
`docs/technology-stack.md` and `docs/architecture.md` from the templates, plus a diagram
(see `architecture.md`). Do not rewrite existing documentation unless asked.

Preserve the existing stack. Propose migrations only when the user asks.
