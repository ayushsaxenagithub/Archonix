# Test plan from acceptance criteria

Turns the acceptance criteria in `docs/requirements.json` into tests, and links real
test results back to those criteria in the traceability matrix. The ledger needs no
extra evidence entries for this.

## The naming convention

A test is linked to an acceptance criterion by the ID in its name:

| Framework | Convention | Example |
|---|---|---|
| pytest | `test_<id>__<words>`: the ID lower-cased with `-` → `_`, ended by `__` | `test_ac_001_1__discount_applies` ↔ `AC-001-1` |
| Jest, Vitest, any JUnit producer | the literal ID anywhere in the test name, conventionally a title prefix | `"AC-001-1: discount applies"` |

AC IDs cannot contain `_`, so the pytest form decodes unambiguously. Hand-written tests
can follow the same convention. Tests that don't follow it can be linked with an
explicit `test:<name>` evidence entry in the ledger. Accepted forms are:

- a test name;
- `classname::name`;
- a pytest node ID such as `tests/test_x.py::test_name`.

## Scaffold the tests

```bash
archonix tests scaffold . --framework pytest                                  # preview
archonix tests scaffold . --framework pytest --apply --allow-source-writes
archonix tests scaffold . --framework vitest --typescript --apply --allow-source-writes
archonix tests scaffold . --framework jest --failing --apply --allow-source-writes
```

- The command writes one file per requirement under `tests/acceptance/` (`--out-dir`
  changes this), with one stub per acceptance criterion. It skips requirements that
  are `rejected` or `deferred`, or that have no criteria.
- Stubs are **pending** by default (`pytest.skip`, `test.skip`). Pending tests are
  reported as skipped, which counts as *unknown*, never passed. `--failing` makes them
  fail until implemented, for test-first work.
- `test.todo` is never generated. jest-junit 17 reports it like a passing test (see
  below).
- Existing files are never overwritten, and writing needs `--allow-source-writes`.

Replace each stub body with a real test, and keep the name prefix.

## Link results to criteria

```bash
# pytest through Archonix: the report records every test case
archonix check run . --mode audit --allow-repo-code --checks pytest --out-dir .archonix/tests
archonix requirements matrix docs/requirements.json --report .archonix/tests/report.json

# any runner that writes JUnit XML (Jest with jest-junit, Vitest --reporter=junit, …)
archonix requirements matrix docs/requirements.json --junit junit.xml
```

| Test result | Criterion evidence |
|---|---|
| passed | pass |
| failed or errored | fail |
| skipped (pending stub) | unknown |

A criterion passes only if **every** linked test passes and any other evidence it has
(ledger `check:` / `test:` entries) also passes. A test that names an ID missing from
the ledger is reported as a warning, which catches typos.

## Known limitations

- jest-junit 17 lists `test.todo` with no skipped marker, but leaves it out of the
  suite's `tests=` count. Archonix detects that mismatch and treats the suite's
  unmarked zero-time cases as pending. A genuine 0 ms pass in such a suite becomes
  "unknown", never the reverse. Prefer `test.skip` for pending tests.
- pytest only runs the scaffolded files if `tests/acceptance` is on its test path.
  Add it to `testpaths` if you restrict them.
- Only the pytest check records test cases inside workflow reports. Jest and Vitest
  results are read from their JUnit files with `--junit`.
- Results recorded from formats verified on 2026-10-21: pytest 9.1.1, Vitest 5.0.5, and
  Jest 30.5.2 with jest-junit 17.0.0.
