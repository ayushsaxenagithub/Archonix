# Acceptance traceability matrix

Basis: `verified` = resolved against supplied check executions; `recorded` = assertion recorded in the ledger, not machine-checked.

| Requirement | Priority | Status | Criterion | Method | Result | Basis | Evidence |
|---|---|---|---|---|---|---|---|
| REQ-001 | must | verified | AC-001-1 | automated-test | pass | verified | check:pytest -> completed/clean |
| REQ-001 | must | verified | AC-001-2 | automated-test | pass | recorded | tests/test_pricing.py::test_rejects_out_of_range_percent (recorded pass; not machine-checked) |
| REQ-002 | must | in-progress | AC-002-1 | automated-test | missing | none | — |
| REQ-003 | could | proposed | — | not-yet-defined | missing | none | — |
