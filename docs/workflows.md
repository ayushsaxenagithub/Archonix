# Example workflows

These show how the skill and CLI combine. Commands in each step are what an assistant (or
you) would run; the skill references describe the judgement around them.

## Understand an unfamiliar repository (discovery mode, nothing executed)

```bash
archonix inventory . --format md
archonix architecture diagram . --out docs/architecture-context.md
archonix check plan . --mode audit          # what could be checked next, and what it needs
```

The assistant then reads entry points and key modules and writes a short summary with
evidence paths, labelling inferred relationships. See
[`examples/reports/inventory-mixed-monorepo.md`](../examples/reports/inventory-mixed-monorepo.md)
and [`examples/reports/architecture-mixed-monorepo.md`](../examples/reports/architecture-mixed-monorepo.md).

## Discover requirements for a substantial feature

```bash
archonix docs init . --set discovery                                   # preview
archonix docs init . --set discovery --apply --allow-source-writes
archonix requirements validate docs/requirements.json
```

The assistant fills the ledger from existing documents first, asks only material questions
(one at a time), marks critical unknowns, and asks for confirmation of the scope only where
it is not already approved.

## Fix a bug (proportionate)

No discovery documents. Reproduce with a failing test, fix, then:

```bash
archonix check run . --mode audit --allow-repo-code --checks pytest
```

Report: reproduction, root cause, fix, the test that now passes, and anything not verified.

## Whole-codebase audit

For "check / audit / review the whole codebase", the skill loads
`references/codebase-audit.md`. The method:

1. Turn the project's own documented promises into checks.
2. Split the code by risk: trust boundaries, write paths, verdict logic, process
   handling.
3. Review each area against those promises.
4. Confirm every finding with a local reproduction on a throwaway copy before reporting
   it.

Scanner output is triaged (production code separated from tests and examples), and
failing tests are triaged before they are called bugs.

```bash
out="$(mktemp -d)"   # reports outside the repository being audited
archonix check run . --mode audit --exclude examples --out-dir "$out"
```

## Security audit

```bash
archonix check plan . --mode audit
archonix check run . --mode audit --checks bandit,ruff,gitleaks,semgrep-local --out-dir .archonix/security
```

The assistant reviews scanner findings (marking each verified, hypothesis or
false-positive), performs the manual checklist in `references/security.md`, and lists
what was not covered. Example: [`examples/reports/report.md`](../examples/reports/report.md).

## Dead-code investigation

```bash
archonix check run . --mode audit --checks vulture --format json
```

Each candidate is checked for dynamic/framework/external references before any removal is
proposed as a separate change.

## API smoke check

```bash
archonix perf endpoints openapi.json
archonix perf smoke --base-url http://127.0.0.1:8000 --path /health --requests 100 \
  --p95-ms 200 --allow-network
```

Example: [`examples/reports/perf.md`](../examples/reports/perf.md).

## Release readiness

```bash
archonix check run . --mode audit --allow-repo-code --checks ruff,bandit,pytest --out-dir .archonix/release
archonix requirements matrix docs/requirements.json --report .archonix/release/report.json
archonix readiness assess --policy release-policy.toml \
  --report .archonix/release/report.json --ledger docs/requirements.json
```

Example: [`examples/reports/readiness.md`](../examples/reports/readiness.md) — `NOT-READY`
because of an open high-severity finding and an unverified `must` requirement, with
revision and working-tree rules `unknown` because the example ran outside Git.

## How workflows share state

One ledger (`docs/requirements.json`) holds requirement and acceptance IDs. Implementation
notes and tests cite those IDs; workflow reports hold executions and findings; the
traceability matrix joins them; readiness reads reports + ledger. Each workflow writes only
its own documents.
