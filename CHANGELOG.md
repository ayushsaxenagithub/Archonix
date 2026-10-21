# Changelog

All notable changes to Archonix are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (pre-1.0: minor versions may change
behaviour; patch versions are fixes).

## [Unreleased]

### Fixed

- Traceability matrix resolves `check:<id>` evidence before assigning a result: missing
  or unrun checks are `unknown` and failed tests are `fail`, even when the ledger records
  `pass`. Previously the recorded value decided the result. Rows gain a `basis` field
  (`verified`, `recorded`, `mixed`).

- Retained artifacts are redacted and listed on every exit path of a check, including
  timeouts and adapter errors. Previously, a timed-out tool's report kept any secret it
  contained and was missing from the execution record. Artifacts that cannot be redacted
  (binary, oversized, unreadable, symlinks) are now removed from the output directory and
  reported, rather than kept. An adapter that raises is recorded as `parse-error` instead
  of aborting the whole run.

- Timeout cleanup sends SIGKILL to the whole process group after the grace period even
  when the direct child already exited, so descendants that ignore SIGTERM no longer
  survive a timeout.

- Skill: explicit rule for where reports and artifacts go (named location, else
  `.archonix/<run>/` when repository changes are allowed, else a fresh temporary
  directory, else stdout), and to state the path used. Found in acceptance testing:
  told not to modify files, an assistant invented a directory three levels above the
  repository.

- The `pytest` check sets `PYTHONDONTWRITEBYTECODE=1` for the test process only, so a run
  no longer leaves `__pycache__` directories in the repository (`.pytest_cache` was already
  disabled). Found in acceptance testing; nothing is deleted and other tools are unaffected.

- Skill: the bug-investigation and implementation workflows (and `SKILL.md`) now name the
  CLI test-verification command (`archonix check run . --mode audit --allow-repo-code
  --checks pytest`, only when authorized) and require reporting tests as **not run** with
  the exact command otherwise. Found in acceptance testing with Claude Code: a correct
  bug fix was left unverified because the bug workflow did not point to the permitted
  CLI path. With the fix, the same task reproduced the bug and verified the fix.

### Added

- Acceptance suites: `acceptance/cli_acceptance.py` (installed CLI on four scenario
  repositories, criteria AC-1..AC-11; runs in CI) and `acceptance/claude_code.py` (opt-in
  Claude Code run of four tasks with automatic, transcript-based scoring), plus a manual
  procedure for Codex and Cursor. Results: `docs/acceptance/2026-10-21-results.md`.

- `osv-scanner` check: dependency vulnerabilities from lockfiles and requirements files in
  any directory and many ecosystems (Python, npm, Go, Rust, Ruby, PHP, …). Requires
  `--allow-network`; call analysis is disabled so no build scripts run. Verified against
  osv-scanner 2.7.0, with recorded fixtures and a scheduled real-tool CI job.
- CI `semgrep` job: the `semgrep-local` adapter is now verified against real semgrep
  1.182.0 on every pull request (findings, clean scan, invalid rules).

## [0.1.1] - unreleased

First version intended for PyPI. **Upgrade from 0.1.0**: it contains installer and
redaction security fixes.

### Security

- `uninstall`/`install` refuse manifest entries that are absolute, contain `..` or resolve
  outside the skill directory; previously a crafted manifest could delete files elsewhere.
- The installer refuses symlinked targets and path components (project scope: anywhere
  below the project root) instead of writing or deleting through them.
- Repository `archonix.toml` may no longer supply redaction regular expressions.
- Empty and relative `PATH` entries are ignored, so a repository cannot shadow a tool.
- Outcome details, parse limitations and nested retained artifacts are redacted;
  artifacts that cannot be redacted are named in the report.

### Fixed

- Clean errors instead of tracebacks for unreadable input files.
- `referencing` is declared as a runtime dependency; `scripts/` is included in the sdist.
- `SECURITY.md` describes the reporting channel that actually exists.

### Added

- CI: markdownlint, gitleaks history scan, real gitleaks adapter test, offline internal
  link check, scheduled pip-audit, Dependabot; contributor templates and maintainer policy.
- Release workflow for PyPI trusted publishing and a release checklist.
- Complete package metadata (project URLs, classifiers) and absolute README links so the
  PyPI project page renders correctly.

## [0.1.0] - 2026-10-21

Initial release (GitHub pre-release only; not published to PyPI). See the
[v0.1.0 release notes](https://github.com/ayushsaxenagithub/Archonix/releases/tag/v0.1.0).
Affected by the security issues fixed in 0.1.1.

[Unreleased]: https://github.com/ayushsaxenagithub/Archonix/compare/v0.1.0...HEAD
[0.1.1]: https://github.com/ayushsaxenagithub/Archonix/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ayushsaxenagithub/Archonix/releases/tag/v0.1.0
