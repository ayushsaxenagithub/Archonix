# Contributing to Archonix

Thanks for helping. Archonix values small, evidence-backed changes. New here? Start with
[docs/good-first-issues.md](docs/good-first-issues.md).

## Workflow

1. **Discuss first for anything large.** Open an issue (bug or feature form) or a
   discussion before starting work that changes permissions, schemas, the CLI interface
   or the skill's workflow selection.
2. **Fork and branch.** Branch from `main` with a descriptive name, e.g.
   `fix/installer-symlink`, `feat/trivy-adapter`, `docs/troubleshooting-path`.
3. **Keep the change focused.** One concern per pull request; no drive-by reformatting.
4. **Validate locally** (below) and fill in the pull-request template, including what you
   could *not* verify.
5. **Review.** A maintainer reviews every pull request before merge; see
   [docs/maintainers.md](docs/maintainers.md) for the merge policy and required checks.

## Development setup

```bash
uv sync                 # creates .venv with dev tools (pytest, ruff, mypy, bandit, vulture)
uv run pytest           # full suite; real-tool integration tests skip when a tool is missing
uv run pytest -m "not integration"   # offline fixture tests only
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv build                # sdist + wheel
uv run archonix skill validate
```

CI also runs these; you can run them locally when the tools are available:

```bash
npx markdownlint-cli2 "**/*.md"            # Markdown formatting (config: .markdownlint-cli2.jsonc)
gitleaks git --no-banner --redact .        # secret scan of the history
uv run pytest -m integration -rs           # real-tool tests; shows which tools were skipped
```

Internal Markdown links are checked by `tests/test_docs_consistency.py`, so a plain
`uv run pytest` covers them. See [docs/ci.md](docs/ci.md) for every CI job.

Without uv: `python -m venv .venv && . .venv/bin/activate && pip install -e . pytest ruff mypy types-jsonschema bandit vulture`.

## Ground rules

- **Behaviour first.** Tests should exercise observable behaviour and boundaries (exit
  codes, report contents, refusals), not restate implementation details.
- **Fixtures vs real tools.** Parsers are tested against fixtures in
  `tests/fixtures/tool-output/`; prefer fixtures captured from real tool runs. Tests that
  run a real tool live in `tests/test_integration_real.py`, are marked `integration` and
  must skip (not fail) when the tool is absent.
- **No real secrets**, ever — not in fixtures, examples or tests. Build synthetic tokens at
  runtime if a pattern must be exercised (see `tests/test_redact.py`).
- **Honest status labels.** If you add a capability, update `docs/capabilities.md` with
  its real status. Do not document planned work as implemented.
- **Docs match the CLI.** `tests/test_docs_consistency.py` parses every `archonix …`
  command in the docs; keep it passing.
- **Schemas are versioned.** Backwards-incompatible changes to a schema need a new
  `schema_version` and a decision record in `docs/architecture-decisions/`.

## Adding a tool adapter

1. Subclass `archonix.adapters.base.Adapter` (see `python_tools.py` for examples) and set
   `requires` honestly: does it execute repository code? use the network? write caches?
2. Document the exit codes it can return and what each means.
3. Parse output defensively: malformed, truncated and unexpected output must produce
   `parse-error`, never `clean`.
4. Add fixture tests for findings, clean output, malformed output and every documented
   exit code; add an integration test if the tool can run offline.
5. Register it in `archonix/adapters/__init__.py` and document it in `docs/tool-adapters.md`.

## Pull requests

Describe what changed and why, list the commands you ran and their outcomes, and note
anything you could not verify.

## Test expectations

- Every bug fix comes with a test that fails without the fix.
- Safety-relevant code (permissions, subprocess execution, redaction, installer, write
  boundaries) needs negative-path tests: denied permissions, malformed or truncated tool
  output, invalid paths, symlink escapes, redaction misses.
- Use synthetic data only. Build credential-shaped strings at runtime (see
  `tests/test_redact.py`) so the repository never contains a realistic secret.
- Do not delete tests or loosen assertions to get CI green. If a test is wrong, explain
  why in the pull request.

## Review criteria

Reviewers check, in order: correctness and tests; safety (no weakened checks, honest
`requires` on adapters, no new network or code execution by default); compatibility of
the CLI, schemas and skill layout across Claude Code, Codex and Cursor; documentation and
`docs/capabilities.md` accuracy; and scope (only changes relevant to the stated purpose).

## Dependencies

Runtime dependencies are deliberately minimal (see
[ADR-0003](docs/architecture-decisions/0003-minimal-dependencies.md)). Adding one needs a
justification in the pull request; update `uv.lock` with `uv lock` in the same change.
