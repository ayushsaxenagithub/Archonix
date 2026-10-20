> **EXAMPLE REPORT** — generated from a synthetic fixture for documentation.

# Archonix audit report

- Report: `RPT-7ef44d9f9d45` (schema 0.1, archonix 0.1.0)
- Generated (UTC): 2026-10-20T21:29:45Z
- Scope: `examples/python-service`; mode: audit; requested checks: ruff, bandit, vulture, pytest
- Repository: none; revision: none recorded; branch: n/a; uncommitted changes: unknown

## Summary

- Checks: 4 run of 4 considered — 1 clean, 3 with findings, 0 failed/unparsed, 0 not run
- Findings by severity: high 1, medium 4, low 4, info 3

## Checks

| Check | Status | Outcome | Exit | Duration (s) | Tool version | Detail |
|---|---|---|---|---|---|---|
| ruff | completed | findings | 1 | 0.038 | 0.17.1 | 4 finding(s) |
| bandit | completed | findings | 1 | 0.132 | 1.9.4 | 5 finding(s) |
| vulture | completed | findings | 3 | 0.04 | 2.16 | 3 finding(s) |
| pytest | completed | clean | 0 | 0.123 | 9.1.1 | 3 passed, 0 skipped |

## Test results

| Check | Total | Passed | Failed | Skipped | Errored |
|---|---|---|---|---|---|
| pytest | 3 | 3 | 0 | 0 | 0 |

## Findings

| ID | Severity | Confidence | Category | Location | Source rule | Title | Status |
|---|---|---|---|---|---|---|---|
| `ARX-31037a45378a1cb8` | high | high | security | `app/ops.py:11` | bandit:B602 | B602 subprocess_popen_with_shell_equals_true: subprocess call with shell=True identified, security issue. | scanner-reported |
| `ARX-3dd1669aaf66da6a` | medium | high | security | `app/ops.py:6` | ruff:S105 | S105: Possible hardcoded password assigned to: "DATABASE_PASSWORD" | scanner-reported |
| `ARX-1cc90bf34bce190f` | medium | high | security | `app/ops.py:11` | ruff:S602 | S602: `subprocess` call with `shell=True` identified, security issue | scanner-reported |
| `ARX-85db76d6492bd7d5` | medium | high | security | `tests/test_pricing.py:9` | ruff:S101 | S101: Use of `assert` detected | scanner-reported |
| `ARX-a82ee3e4aeca07d8` | medium | high | security | `tests/test_pricing.py:13` | ruff:S101 | S101: Use of `assert` detected | scanner-reported |
| `ARX-5729952f9a1924bf` | low | high | security | `app/ops.py:3` | bandit:B404 | B404 blacklist: Consider possible security implications associated with the subprocess module. | scanner-reported |
| `ARX-ea9f6b84a5c204cf` | low | medium | security | `app/ops.py:6` | bandit:B105 | B105 hardcoded_password_string: Possible hardcoded password: '[REDACTED]' | scanner-reported |
| `ARX-711cde12b127fda6` | low | high | security | `tests/test_pricing.py:9` | bandit:B101 | B101 assert_used: Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | scanner-reported |
| `ARX-a86cb7afae5ddda9` | low | high | security | `tests/test_pricing.py:13` | bandit:B101 | B101 assert_used: Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | scanner-reported |
| `ARX-8ef3be49c6338bb0` | info | low | dead-code | `app/ops.py:6` | vulture:unused variable | unused variable 'DATABASE_PASSWORD' | scanner-reported |
| `ARX-10c862a5e7eca4c2` | info | low | dead-code | `app/ops.py:9` | vulture:unused function | unused function 'ping' | scanner-reported |
| `ARX-0227e113d187dd86` | info | low | dead-code | `app/pricing.py:13` | vulture:unused function | unused function 'legacy_rounding' | scanner-reported |

## Commands executed

- `ruff check --output-format json --no-cache --no-fix --extend-exclude .git,.hg,.svn,node_modules,.venv,venv,env,__pycache__,.mypy_cache,.pytest_cache,.ruff_cache,.tox,.nox,.cache,dist,build,.next,.nuxt,.turbo,coverage,htmlcov,.idea,.vscode,target,vendor,.gradle,.terraform,.archonix,*.egg-info .` (cwd `examples/python-service`, started 2026-10-20T21:29:44Z)
- `bandit -r . -f json -q -x */.git/*,*/.hg/*,*/.svn/*,*/node_modules/*,*/.venv/*,*/venv/*,*/env/*,*/__pycache__/*,*/.mypy_cache/*,*/.pytest_cache/*,*/.ruff_cache/*,*/.tox/*,*/.nox/*,*/.cache/*,*/dist/*,*/build/*,*/.next/*,*/.nuxt/*,*/.turbo/*,*/coverage/*,*/htmlcov/*,*/.idea/*,*/.vscode/*,*/target/*,*/vendor/*,*/.gradle/*,*/.terraform/*,*/.archonix/*,*.egg-info` (cwd `examples/python-service`, started 2026-10-20T21:29:44Z)
- `vulture . --min-confidence 60 --exclude */.git/*,*/.hg/*,*/.svn/*,*/node_modules/*,*/.venv/*,*/venv/*,*/env/*,*/__pycache__/*,*/.mypy_cache/*,*/.pytest_cache/*,*/.ruff_cache/*,*/.tox/*,*/.nox/*,*/.cache/*,*/dist/*,*/build/*,*/.next/*,*/.nuxt/*,*/.turbo/*,*/coverage/*,*/htmlcov/*,*/.idea/*,*/.vscode/*,*/target/*,*/vendor/*,*/.gradle/*,*/.terraform/*,*/.archonix/*,*.egg-info` (cwd `examples/python-service`, started 2026-10-20T21:29:44Z)
- `pytest -q -p no:cacheprovider --junitxml=/var/folders/c0/_c37y8zn2lv8w7y1fwl_1_ww0000gn/T/archonix-pytest-cg5vis3o/pytest-junit.xml` (cwd `examples/python-service`, started 2026-10-20T21:29:44Z)

## Effective permissions

source_writes=off, artifact_writes=on, repo_code=on, external_tools=on, network=off, dependency_install=off, shared_environment=off, destructive=off

## Limitations

- Automated checks cover only what the selected tools and rules detect; absence of findings is not proof of correctness or security.
- Scanner-reported findings are unverified until reviewed (see verification_status).
- not a Git repository; no revision recorded

## Recommended next actions

- Triage findings: confirm or mark false-positive, then remediate verified issues starting with the highest severity.
