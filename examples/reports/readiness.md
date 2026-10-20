> **EXAMPLE ASSESSMENT** — synthetic inputs, for documentation.

# Release readiness: **NOT-READY**

- Policy: example-release-policy (examples/readiness-policy.toml)
- Generated (UTC): 2026-10-20T21:29:45Z
- Reports: examples/reports/report.json
- Requirements ledger: examples/requirements/ledger.json

| Rule | Result | Detail |
|---|---|---|
| check:ruff | pass | findings (4 finding(s)) |
| check:bandit | pass | findings (5 finding(s)) |
| check:pytest | pass | clean (3 passed, 0 skipped) |
| max-severity | fail | 1 open finding(s) above 'medium' |
| no-unparsed-checks | pass | all executed checks parsed |
| tests | pass | 3 tests |
| revision | unknown | revision not recorded in every report |
| clean-worktree | unknown | working-tree status unknown |
| must-requirements | fail | not verified: REQ-002 |

## Limitations

- The verdict reflects only the configured policy and the supplied evidence; it is not a guarantee of security, correctness or production fitness.
