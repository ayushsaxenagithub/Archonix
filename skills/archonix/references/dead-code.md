# Dead-code and dependency analysis

Discovery and cleanup are separate steps. Never delete uncertain findings automatically.

## Discovery

- Python: `archonix check run . --checks vulture --mode audit` (unused functions,
  classes, variables, imports). deptry finds unused/missing dependencies (manual in v0.1).
- JavaScript/TypeScript: Knip (manual in v0.1; it loads project config and can execute
  it, so treat it as repository code execution).
- Also look for unused routes, views, components, models/fields, configuration keys,
  background tasks and feature flags by searching references.

## Account for invisible references

Dynamic imports and `importlib`, reflection, dependency injection, framework registration
(Django apps/admin, Flask blueprints, pytest fixtures, Celery tasks, signals), plugins and
entry points, scheduled jobs, templates referencing names, generated code, conditional
features, and external consumers of public APIs or packages.

## Classify

| Confidence | Meaning |
|---|---|
| high | no static reference, not public, not framework-registered, and you checked the dynamic paths |
| medium | no static reference; dynamic use unlikely but not ruled out |
| low | tool-reported only, or name patterns suggest framework/dynamic use |

Vulture's own percentages are tool confidence in "no static reference", not proof of
non-use; Archonix maps them to at most `medium`.

## Cleanup proposal

Produce `docs/dead-code-analysis.md` with evidence per item, then propose removals as a
separate, reviewable change with tests passing before and after. Database field removal
requires compatibility analysis and a staged migration (stop writing → stop reading →
drop), never a single destructive step.
