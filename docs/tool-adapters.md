# Tool adapters

Each adapter declares how it is invoked, when it applies, what it requires, and how exit
codes and output are interpreted. `archonix check list --format json` prints the same
information from the code. "Tested version" is the version used for the recorded real-tool
runs in this repository; other versions with the same output format are expected to work
but are not verified.

Common behaviour: argv invocation from the repository root; Archonix exclusions are passed
to the tool; outputs larger than `max_output_bytes` are not parsed (`parse-error`);
unexpected exit codes are `tool-error`, never `clean`; findings keep the tool's rule ID and
severity in `source`.

| Check | Invocation | Exit codes | Network | Filesystem effects | Tested |
|---|---|---|---|---|---|
| `ruff` | `ruff check --output-format json --no-cache --no-fix --extend-exclude … .` | 0 none · 1 violations · 2 error | none | none (`--no-cache`, `--no-fix`) | real 0.17.1 + fixtures |
| `bandit` | `bandit -r . -f json -q -x <globs>` | 0 none · 1 issues · 2 error | none | none | real 1.9.4 + fixtures |
| `vulture` | `vulture . --min-confidence 60 --exclude <globs>` | 0 none · 1 invalid input · 2 bad args · 3 dead code | none | none | real 2.16 + fixtures |
| `pytest` | `pytest -q -p no:cacheprovider --junitxml=<artifact>` | 0 pass · 1 failures · 2 interrupted · 3 internal · 4 usage · 5 no tests | if tests use it | whatever the tests do; JUnit XML in the artifact dir; `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider` so no `__pycache__`/`.pytest_cache` is left in the repository | real 9.1.1 + fixtures |
| `gitleaks` | `gitleaks detect --no-git --source . --no-banner --redact --report-format json --report-path <artifact> --exit-code 1` | 0 none · 1 leaks · other error | none | report file in artifact dir | real 8.30.1 + fixtures |
| `semgrep-local` | `semgrep scan --json --metrics=off --disable-version-check --quiet --config <.semgrep.yml\|.semgrep> …` | 0 done · 1 findings (with `--error`) · 2–8 errors | none expected with local rules | semgrep's own cache | real 1.182.0 in CI + fixtures |
| `semgrep-registry` | as above with `--config p/default` | as above | downloads rules | cache | fixtures + manual real run (1.182.0) |
| `npm-audit` | `npm audit --json` (root `package-lock.json`) | 0 none · 1 vulns *or* error (distinguished by JSON `error`) | sends dependency tree to the registry | npm cache/logs | fixtures only |
| `osv-scanner` | `osv-scanner scan source --recursive --format json --no-call-analysis=all --verbosity error --x-exclude … .` | 0 none · 1 vulns · 127 error · 128 no package sources | sends package names/versions to osv.dev; may resolve unpinned manifests via deps.dev | none | real 2.7.0 + recorded fixtures |

## Interpretation details

- **ruff**: rules matching `S` + three digits (flake8-bandit) are `security`/`medium`;
  everything else is `lint`/`low`, confidence `high` (deterministic rules).
- **bandit**: severity and confidence map directly from `issue_severity` /
  `issue_confidence`; CWE links and `more_info` become references; bandit's own `errors`
  mark the scan **partial** (`coverage.complete = false`, outcome detail
  "(partial scan)") and are listed as limitations.
- **vulture**: `info` severity; confidence `medium` for ≥ 90 %, else `low`. A vulture
  percentage expresses "no static reference", not proof of non-use.
- **pytest**: totals from JUnit XML; each failure/error becomes a `test-failure` finding.
  Exit 5 (no tests collected) is a `tool-error`, not a pass. A missing or malformed JUnit
  file leaves all counts `null`.
- **gitleaks**: the matched secret text is never copied into the report; only rule,
  location and entropy.
- **semgrep**: `ERROR`→high, `WARNING`→medium, `INFO`→low; `metadata.confidence` →
  confidence; `errors[]` marks the scan as partial (`coverage.complete = false`).
- **osv-scanner**: one finding per package × advisory group (OSV de-duplicates aliases
  into groups); severity from the group's CVSS `max_severity` (≥ 9 critical, ≥ 7 high,
  ≥ 4 medium, otherwise low), falling back to the GitHub database label, else `unknown`.
  Confidence is `high` for versions pinned in a lockfile and `medium` for transitive
  versions osv-scanner resolved itself. Fixed versions come only from ECOSYSTEM/SEMVER
  ranges (never commit SHAs). Call analysis is disabled because Rust call analysis runs
  build scripts. Known gaps: npm lockfile entries without a `resolved` registry URL are
  skipped by osv-scanner; files ignored by `.gitignore` are not scanned; a repository
  `osv-scanner.toml` can ignore advisories (reported as a limitation). It overlaps with
  `npm-audit` for npm lockfiles; findings from both are kept separately.
- **npm audit** (report v2): one finding per vulnerable package; `moderate`→medium;
  advisory URLs become references.

## Documented manual workflows (no adapter in v0.1)

Trivy, OSV-Scanner, pip-audit, deptry, Knip, ESLint, tsc, mypy, OWASP ZAP and k6 runs are
described in the skill references. Record their command, version, exit code and outcome
in the same report structure by hand, or add an adapter (see CONTRIBUTING.md).
