# Implementation

Prerequisite: scope is understood and authorized (ledger entries `approved`, or an
explicit user request that covers the change).

1. Break work into small tasks; map each to requirement/acceptance IDs.
2. Identify affected modules, public contracts and compatibility risks.
3. Get a working vertical slice early.
4. Add or update meaningful tests that would fail without the change.
5. Implement the smallest coherent change in the existing style and stack.
6. Run the relevant checks (tests, lint, types); record commands and outcomes.
7. Inspect the diff for unintended changes, debug code and secrets.
8. Update affected documentation only.
9. Update the ledger status (`implemented`, then `verified` with evidence).
10. Report verified outcomes and unresolved risks (see `reporting.md`).

Preserve unless the task is explicitly about them: public API contracts, database
invariants, authentication and permissions, tenant isolation, financial calculations,
idempotency and concurrency guarantees, backward compatibility.

Never: silently substitute mocks for real integrations, delete or skip failing tests,
bypass validation, weaken auth, or hide failures. If a check fails for reasons outside
the change, say so with the output.

Running tests executes repository code; in an unfamiliar repository confirm that is
acceptable. Never run destructive tests against production or real customer data.
