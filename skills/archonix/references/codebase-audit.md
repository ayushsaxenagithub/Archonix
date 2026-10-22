# Whole-codebase audit

Use when the user asks to check, audit or review a whole codebase, not a single diff.
Scanners help, but most real defects are found by checking the code against what the
project promises. Every finding needs a reproduction before it is reported.

## 1. Fix the scope and the evidence baseline

Record the revision and whether the working tree has uncommitted changes. Decide what is
in scope: production code, tests, examples, infrastructure. Agree on permissions up
front (static only, or also running tests and reproductions). Then:

```bash
archonix inventory . --format md
archonix check plan . --mode audit
```

## 2. Turn the project's promises into checks

Collect what the project claims about itself, from the README, docs, security policy,
capability lists, docstrings, CLI help, schemas and the requirements ledger. Write each
claim as a checkable statement, for example "reports are written only inside the chosen
output location", "a skipped test never counts as passed", or "users of tenant A cannot
read tenant B's records". These statements are your audit checklist. A promise with no
code enforcing it is itself a finding.

## 3. Split the code by risk

Review in this order and spend most time at the top:

1. **Trust boundaries**: where untrusted input enters, such as request handlers,
   parsers of files or tool output, repository-controlled config, webhooks and
   uploads.
2. **Write and delete paths**: filesystem writes, installers, migrations, anything that
   follows a path or a symlink.
3. **Verdict logic**: authorization decisions, validation, pass/fail and "ready"
   calculations, money and quota arithmetic.
4. **Process and resource handling**: subprocesses, timeouts, cleanup, concurrency,
   retries.
5. Everything else.

## 4. Review each area against the promises

For each area, read the code with the relevant claims in mind, and look for paths that
break them: error and timeout branches, empty or unknown values, symlinks, unexpected
formats, missing permissions. Note each suspected defect with file:line and the claim
it breaks. Use the security checklist in `security.md` for the trust boundaries.

## 5. Reproduce before reporting

Confirm every suspected defect with the smallest reproduction you can, before it goes
in the report:

- Work on a **throwaway local copy** of the code under review, with synthetic data, in
  a temporary directory. Never use live, shared or production systems, and never target
  other people's services (see `execution-policy.md`).
- Running a reproduction runs the project's code, so it needs the same authorization as
  running its tests.
- Record the reproduction steps, and the observed versus expected result.
- A finding you could not reproduce stays a **hypothesis**, with what you tried.
- After a fix, run the same reproduction again to show the defect is gone. Keep it as a
  regression test where possible.

## 6. Triage scanner output

Automated checks are evidence of coverage, not the audit itself.

- Separate findings in production code from findings in tests, examples and fixtures.
- Summarise low-severity findings outside production code as counts per rule, rather
  than listing hundreds of rows.
- Deliberately vulnerable examples or fixtures belong out of the scan. Suggest
  `--exclude examples` (a trusted CLI flag), and say that you excluded them.
- A check that did not run is "not run", not "0 findings". A partial scan is partial.

## 7. Triage test failures

Before reporting a failing test as a product defect, use the triage in `testing.md`:
rerun it alone, check whether it depends on the environment, and classify it as a
product, test or environment problem.

## 8. Report

Use `reporting.md`. Order findings by severity. Each one gets:

- the claim it breaks;
- file:line;
- the reproduction and its result;
- its status: verified by reproduction, or hypothesis;
- a suggested fix.

List the areas you reviewed and the ones you did not.
