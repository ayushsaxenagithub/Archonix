# Contributing to Archonix

Thanks for helping. Archonix values small, evidence-backed changes.

## Development setup

```bash
uv sync                 # creates .venv with dev tools (pytest, ruff, mypy, bandit, vulture)
uv run pytest           # full suite; real-tool integration tests skip when a tool is missing
uv run pytest -m "not integration"   # offline fixture tests only
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv build                # sdist + wheel
```

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
