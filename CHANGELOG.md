# Changelog

All notable changes to Archonix are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (pre-1.0: minor versions may change
behaviour; patch versions are fixes).

## [Unreleased]

### Added

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
