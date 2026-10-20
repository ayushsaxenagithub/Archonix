# Known limitations and roadmap

## Limitations in v0.1

- Not a sandbox: launched tools run with your privileges. Use containers/VMs for
  untrusted code.
- Stack detection is strongest for Python and JavaScript/TypeScript; other ecosystems get
  language counts and manifest listing only. Detection reflects declared dependencies
  and configuration, not runtime behaviour.
- Adapters: ruff, bandit, vulture, pytest and gitleaks are verified against real tools;
  semgrep and npm audit only against fixtures written from their documented formats.
- `npm audit` covers the root lockfile only; no Yarn/pnpm audit adapters.
- Architecture generation: inventory context diagram and Python import graph only. No
  JS/TS import graph, no route or data-model extraction.
- Performance: smoke measurement only; load tests are generated (k6) but not run;
  no automated revision comparison.
- Redaction is pattern-based and cannot catch every secret.
- Assistant discovery of the installed skill is documented but not exercised in
  automated tests.
- Readiness policies evaluate only the rules listed; there is no rule language.
- Windows: process-group termination falls back to killing the direct child; Windows is
  not tested in CI.

## Roadmap (not committed)

1. Adapters: Trivy, OSV-Scanner, pip-audit, deptry, Knip, ESLint, mypy/tsc
   (starter tasks in [good-first-issues.md](good-first-issues.md)).
2. Verify the semgrep adapter against real tool runs in CI.
3. JS/TS import graph using an established parser; framework route inventories.
4. Run user-approved k6/Locust scenarios with recorded methodology; revision comparison.
5. SARIF import/export for findings.
6. Windows support in CI.
7. Assistant smoke tests that run where vendor accounts are available.

Follow-ups from the [2026-10 audit](audits/2026-10-community-readiness.md): let repository
config only lower execution limits (R4); move gitleaks to `gitleaks dir` (R6).
