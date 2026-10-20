# Instructions for AI agents working on this repository

This file is for agents *developing Archonix itself*. The skill Archonix ships for use on
other projects is in `skills/archonix/`.

## Layout

- `src/archonix/` — Python package and CLI (`cli.py` is the entry point).
- `src/archonix/adapters/` — one class per external tool; `requires` must be honest.
- `skills/archonix/` — the shipped skill: `SKILL.md`, `references/`, `templates/`,
  `schemas/`. It is the single source of truth and is bundled into the wheel.
- `tests/` — pytest; `tests/fixtures/` holds synthetic repos and recorded tool output.
- `docs/` — documentation about Archonix (not templates for user projects).
- `examples/` — synthetic projects and example reports; regenerate reports with
  `scripts/regenerate_examples.sh`.

## Commands

```bash
uv sync
uv run pytest                     # all tests
uv run pytest -m "not integration"
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run archonix skill validate
```

## Rules

- Keep the default experience offline and free of API keys.
- Never weaken a policy check, redaction rule or test to make something pass.
- New capabilities must be reflected in `docs/capabilities.md` with an accurate status.
- Commands shown in docs must exist (`tests/test_docs_consistency.py` enforces this).
- No real secrets or personal data in fixtures, examples or reports.
- Keep `SKILL.md` concise; put detail in `references/`.
