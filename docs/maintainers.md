# Maintainer policy

## Required checks before merge

A pull request is mergeable only when all of these pass in GitHub Actions
([ci.md](ci.md)):

- `test` matrix (Ubuntu and macOS × Python 3.11–3.13): Ruff, format, mypy, fixture tests,
  real-tool integration tests, skill/schema/example validation
- `build`: sdist + wheel, isolated-install smoke test
- `docs`: markdownlint
- `secrets`: gitleaks history scan and real gitleaks adapter test

`Dependency audit` runs weekly and on dependency changes; a failure there blocks merging
the dependency change that caused it and gets an issue otherwise.

## Review before merge

- Every change, including the maintainer's own, goes through a pull request with at least
  one review. `CODEOWNERS` requests the maintainer automatically.
- Changes to `src/archonix/{runner,policy,config,install,redact,checks}.py`, adapters'
  `requires`, schemas, or `.github/workflows/` get an explicit safety review against
  [trust-model.md](trust-model.md).
- Squash-merge with a message that states what changed and how it was verified.

## Dependency changes

- New runtime dependencies need a written justification (ADR-0003).
- GitHub Actions stay pinned to full commit SHAs with a version comment; Dependabot
  proposes updates, and they are reviewed like code (check the upstream release notes).
- `uv.lock` changes must come from `uv lock`, not hand edits.

## Releases

- Version in `pyproject.toml` and `archonix/__init__.py` must match (tested).
- Release from a green `main` commit; regenerate `examples/reports/` if output formats
  changed; update `docs/capabilities.md` and `docs/roadmap.md`.
- Follow [releasing.md](releasing.md): publishing a GitHub release triggers
  `release.yml`, which uploads to PyPI through trusted publishing after approval on the
  `pypi` environment. Release notes state what was verified and what was not.

## Repository settings (recommended; not changed by code in this repository)

These are GitHub settings only an owner can change. Current state was read on 2026-10-21.

| Setting | Current | Recommendation |
|---|---|---|
| Branch protection / ruleset on `main` | not enabled | require PRs, one approval, and the required checks above; block force pushes |
| Private vulnerability reporting | disabled | enable it, then update SECURITY.md |
| Secret scanning + push protection | enabled | keep |
| Dependabot security updates | disabled | enable (version updates are configured in `.github/dependabot.yml`) |
| Discussions | enabled | keep; linked from the issue chooser |
| Merge methods | merge, squash and rebase allowed | allow squash only, to match the policy above |
| Delete head branches on merge | off | on |
| `pypi` / `testpypi` environments | none | create with a required reviewer (see releasing.md) |
