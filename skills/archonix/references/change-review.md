# Change review

1. Establish what the change is meant to do (PR description, linked requirement IDs).
2. Read the full diff and enough surrounding code to judge it.
3. Check, in priority order:
   - correctness against the intent and acceptance criteria; edge cases and failure paths
   - security: authentication/authorization on new paths, object-level access, input
     validation, injection, secrets, unsafe deserialization, logging of sensitive data
   - data: migrations, invariants, backward compatibility, idempotency, concurrency
   - public contracts: API/CLI/schema changes and their consumers
   - tests: do they exercise the change and would they fail without it?
   - unintended changes: unrelated edits, debug code, generated files
4. Optionally run checks on the changed area (`archonix check run --checks ruff,bandit`).
5. Report findings with severity and confidence, file:line, a concrete failure scenario
   and a suggested fix. Separate blocking issues from suggestions. Do not claim you ran
   tests you did not run.
