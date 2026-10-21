# Release readiness

A readiness verdict is a statement about **configured policy and supplied evidence**,
not a guarantee.

## Gather evidence

1. Run the required checks on the release revision from a clean working tree:
   `archonix check run . --mode audit --allow-repo-code --out-dir .archonix/release`
   (use a fresh temporary directory instead of `.archonix/` if the user asked you not to
   modify files; see "Where reports and artifacts go" in `execution-policy.md`)
2. Make sure the requirements ledger reflects verification (`verified` + evidence).
3. Review open findings: mark `false-positive` or `fixed` with justification; do not
   silently drop them.

## Assess

```bash
archonix readiness assess --policy release-policy.toml \
  --report .archonix/release/report.json --ledger docs/requirements.json
```

Policy rules (TOML `[rules]`): `required_checks`, `max_severity`, `require_tests`,
`require_revision`, `require_clean_worktree`, `require_must_requirements_verified`,
`allow_unparsed_checks`, `allow_partial_scans`. Each rule is pass, fail or unknown.
`require_tests` passes only when test runs completed, counts are known and consistent,
at least one test actually executed (skipped tests do not count) and none failed. Any fail → `not-ready`; any
unknown → `incomplete`; only all-pass → `ready`. Missing evidence is never a pass.

## Also check (manual)

Migrations and rollback plan · configuration and secrets per environment · observability
(logs, metrics, alerts) · changelog and version bump · backwards compatibility and
deprecations · documentation updated · rollout strategy (flags, canary) and owner on call.

Deploying or publishing requires explicit authorization; readiness assessment does not
grant it. Record the result with `templates/release-readiness.md` if needed.
