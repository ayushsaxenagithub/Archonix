# Continuous integration

All jobs use `permissions: contents: read`, pin third-party actions to commit SHAs, check
out without persisting credentials, and run on `pull_request` (never
`pull_request_target`), so code from forks runs without secrets or write access.

## `.github/workflows/ci.yml` (every push to `main` and every pull request)

| Job | What it checks | Network |
|---|---|---|
| `test` (Ubuntu, macOS × Python 3.11, 3.12, 3.13) | `ruff check`, `ruff format --check`, `mypy`, offline fixture tests, real-tool integration tests (ruff, bandit, vulture, pytest, git; others skip), skill + example validation, internal Markdown links | package download only |
| `build` | `uv build`; installs the wheel into a fresh venv outside the checkout and runs the CLI, skill validation, inventory and an installer dry run | package download only |
| `docs` | markdownlint-cli2 with `.markdownlint-cli2.jsonc` | action download only |
| `secrets` | downloads gitleaks 8.30.1, verifies its SHA-256, scans the full Git history, then runs the real gitleaks adapter integration test | release download only |

## `.github/workflows/dependency-audit.yml`

`pip-audit` (pinned) over the exported `uv.lock`, runtime and dev groups. It queries
vulnerability databases, so it runs weekly, on manual dispatch, and on pull requests that
change `pyproject.toml` or `uv.lock`, rather than gating every pull request on an external
service.

## `.github/dependabot.yml`

Weekly version-update pull requests for the pinned GitHub Actions and the uv lockfile.

## What CI does not do

- No publishing, deployment or release creation.
- No external link checking (it would make results depend on third-party sites); internal
  links are checked offline by the test suite.
- semgrep and npm audit adapters are not exercised against real tools (fixture tests only).
- Windows is not in the matrix.

## Running the same checks locally

```bash
uv sync --locked
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -rs
uv build
npx markdownlint-cli2 "**/*.md"
gitleaks git --no-banner --redact .
uv export --format requirements-txt --frozen --no-emit-project --all-groups > /tmp/req.txt
uvx --from pip-audit==2.10.1 pip-audit --disable-pip -r /tmp/req.txt
```
