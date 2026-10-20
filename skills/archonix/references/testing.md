# Testing and acceptance traceability

## Choose tests by stack and risk

Unit and integration; end-to-end for critical journeys; API contract and regression;
database migration (up and down on a disposable database); authentication and
authorization (including denied paths and cross-tenant access); invalid-input and
boundary; property-based for parsers and calculations; concurrency and idempotency for
retries and payments; accessibility for user-facing UI; performance/load only with
authorization (see `performance.md`); mutation testing to evaluate weak suites.

## Gap assessment

1. Inventory test frameworks and locations (`archonix inventory`).
2. Map requirements/acceptance criteria to existing tests.
3. Identify untested high-risk areas (auth, money, data deletion, external calls).
4. Coverage tools show unexecuted code; they do not prove correctness.

## Running tests

Tests execute repository code. With the CLI:
`archonix check run . --checks pytest --mode audit --allow-repo-code --out-dir .archonix/tests`
records command, version, duration, exit status and totals from JUnit XML. Exit codes are
interpreted per tool (pytest: 0 passed, 1 failures, 5 no tests collected = not a pass).
Never run destructive tests against production or real customer data.

## Traceability matrix

Record evidence in the ledger (`verification.evidence[]`), using `check:<check_id>` to
link to a report execution, or a test path/manual note otherwise. Then:
`archonix requirements matrix docs/requirements.json --report .archonix/tests/report.json`.
Criteria with no evidence are reported as `missing`, not passed.
