# Audit: community readiness and CI hardening (2026-10-21)

Scope: subprocess execution, permissions and repository-config trust, installer, report
redaction and error handling, packaging, CI, and contributor workflow. Baseline commit
`f59803d` (v0.1.0). Each defect was reproduced with a script before the fix and has a
regression test in `tests/test_hardening.py` unless noted.

## Confirmed defects (fixed)

| ID | Severity | Confidence | Defect and evidence | Impact | Fix |
|---|---|---|---|---|---|
| D1 | High | High | `uninstall` deleted any path listed in `.archonix-manifest.json` whose hash matched. A manifest with `../../../../victim.txt` deleted a file outside the skill directory. | In project scope the manifest is repository-controlled: `archonix uninstall --assistant claude --scope project --apply` on a malicious checkout could delete user files with known content. | Manifest entries must be plain relative paths with no `..`, no absolute paths and no backslashes, and must resolve inside the target. Otherwise the manifest is refused as a conflict and nothing is deleted. |
| D2 | High | High | With `references/` replaced by a symlink to another directory, `install --apply` wrote 13 files into that directory and `uninstall --apply` deleted them there. | A repository-controlled symlink redirects writes and deletes outside the skill directory. | No existing path component between the target and a file may be a symlink. The target itself may not be a symlink. In project scope, no component below the project root may be one (user scope still allows a symlinked `~/.claude` from dotfiles). Copies use `follow_symlinks=False`, and checks are repeated right before each write. Empty-directory pruning uses `os.walk(followlinks=False)`. |
| D3 | Medium | High | Repository `archonix.toml` could set `redaction.extra_patterns`. `(a+)+$` took 0.66 s on 25 characters and grows exponentially, a ReDoS in redaction. Repository exclusions such as `*` were applied to scanners without appearing in reports. | A repository could stall report generation, or hide every file from scanners while the report looked clean. | Repository config may no longer supply regexes (the setting is ignored and recorded). Exclusions added by repository config are listed in report `limitations`. |
| D4 | Medium | High | With `.` on `PATH`, `archonix` run from the repository root executed a repository-local `./ruff`. | Repository code ran under a check that is declared not to execute repository code. | `build_env` and `run` drop empty and relative `PATH` entries, and executables are resolved to absolute paths. |
| D5 | Medium | High | `outcome_detail` and `parse_limitations` were written unredacted. An npm error summary containing `https://user:pass@registry…` reached the report verbatim. Retained artifacts in subdirectories, binary files and files over 20 MB were silently left unredacted. Separately, JSON-quoted keys (`"api_key": "…"`) were not matched by the assignment pattern. | Credentials echoed by tools could persist in reports and artifacts. | Details and limitations are redacted. Artifact redaction walks the whole tree without following symlinks, and every file it cannot redact is named in the report. The assignment pattern accepts quoted keys. |
| D6 | Low | High | `archonix validate <directory>` and `archonix perf endpoints <missing-file>` ended in Python tracebacks. | Confusing errors; the exit codes did not follow the documented contract. | Clean messages with exit 1 or 2. |
| D7 | Low | High | `referencing` was imported directly but not declared, and the sdist omitted `scripts/` even though the docs reference it. | Fragile installs if jsonschema changes its dependency; incomplete source distribution. | Declared `referencing>=0.28.4` and added `scripts` to the sdist. A test fails if a third-party import is not declared. |
| D8 | Medium | High | `SECURITY.md` told reporters to use private vulnerability reporting, but the repository API reports `{"enabled": false}`. | Reporters had no working private channel and might disclose publicly. | `SECURITY.md` now describes the actual process. Enabling the setting is recommended in `docs/maintainers.md`; no settings were changed. |

## Recommendations (not defects; not all implemented)

| ID | Recommendation | Status |
|---|---|---|
| R1 | Add job timeouts, secret scanning, Markdown lint, an offline internal-link check, a dependency audit and Dependabot to CI | Implemented (see `docs/ci.md`) |
| R2 | Add a PR template, issue forms, CODEOWNERS, a maintainer policy and starter tasks | Implemented |
| R3 | Protect `main` (require PRs, reviews and checks; block force pushes) | Documented only; this is a repository setting |
| R4 | Repository config can raise per-check timeouts up to 24 h | Follow-up: consider letting repository config only lower limits |
| R5 | Reader threads can outlive the timeout join if a process escapes the process group (e.g. calls `setsid`) | Follow-up: low impact, since capture is bounded and daemon threads exit with the process |
| R6 | The gitleaks adapter uses the deprecated `detect --no-git` | Verified working with 8.30.1. Follow-up: switch to `gitleaks dir` once the minimum supported version is decided |

## Verified unchanged (no defect found)

- CI already used `permissions: contents: read`, SHA-pinned actions, `persist-credentials: false` and `pull_request` (not `pull_request_target`).
- Runner: argv only, no shell, minimal environment, process-group kill on timeout, bounded capture (existing tests).
- Repository config was already restrict-only for permissions, `env_passthrough` and `extra_args` (existing tests).
- An sdist rebuilds into a complete wheel with the bundled skill (39 files).
- `gitleaks git` over the full history: no leaks (gitleaks 8.30.1).
- `pip-audit` 2.10.1 over the locked runtime and dev dependencies: no known vulnerabilities (2026-10-21).
