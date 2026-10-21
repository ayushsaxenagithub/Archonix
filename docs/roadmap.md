# Known limitations and roadmap

## Limitations in v0.1

- Not a sandbox: launched tools run with your privileges. Use containers/VMs for
  untrusted code.
- Stack detection is strongest for Python and JavaScript/TypeScript; other ecosystems get
  language counts and manifest listing only. Detection reflects declared dependencies
  and configuration, not runtime behaviour.
- Adapters: ruff, bandit, vulture, pytest, gitleaks and semgrep (local rules) are verified
  against real tools in CI on every pull request, and osv-scanner in the scheduled
  dependency-audit workflow; semgrep registry rules and npm audit only against fixtures.
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

## v0.3 milestone: brief to working project

1. ✅ Project agent context: `.ai/` source, `archonix agents init` and `archonix agents sync`, generated
   `AGENTS.md`, `CLAUDE.md` and project skills ([project-agents.md](project-agents.md)).
2. Test plan: one test stub per acceptance criterion, named with its ID
   (a planned "tests scaffold" command for pytest, Jest and Vitest; not available yet).
3. Traceability from test results: `test:<id>` evidence resolved from JUnit reports.
4. Stack decision ADR with explicit approval, then a project skeleton from official
   generators.
5. Brief-to-working-app acceptance run in Claude Code, scored.

## Roadmap (not committed)

1. Adapters: Trivy, deptry, Knip, ESLint, mypy/tsc (OSV-Scanner added after 0.1.1; see CHANGELOG)
   (starter tasks in [good-first-issues.md](good-first-issues.md)).
2. Verify the semgrep-registry and npm-audit adapters against real tools (both need the
   network; candidates for the scheduled workflow).
3. JS/TS import graph using an established parser; framework route inventories.
4. Run user-approved k6/Locust scenarios with recorded methodology; revision comparison.
5. SARIF import/export for findings.
6. Windows support in CI.
7. Assistant smoke tests that run where vendor accounts are available.

Follow-ups from the [2026-10 audit](audits/2026-10-community-readiness.md): let repository
config only lower execution limits (R4); move gitleaks to `gitleaks dir` (R6).
