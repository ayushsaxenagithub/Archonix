<!-- markdownlint-disable-file MD041 -->
## Purpose

<!-- What problem does this solve? Link the issue (e.g. "Fixes #12"). -->

## Scope

<!-- What changed, and what is deliberately NOT changed. Keep unrelated edits out. -->

## How this was tested

<!-- Exact commands and their outcomes. Say which tests are fixture-based and which ran a real tool. -->

- [ ] `uv run pytest` (result: )
- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run mypy`
- [ ] `uv run archonix skill validate` (if `skills/` changed)
- [ ] New or changed behaviour has tests, including failure paths

## Risk

<!-- Does this touch permissions, subprocess execution, redaction, the installer, schemas, or the CLI interface? What could break for users? -->

- [ ] No change to the public CLI interface or report/schema contracts, **or** the change is compatible and documented
- [ ] No weakening of a permission check, redaction rule or test
- [ ] `docs/capabilities.md` reflects the real status of anything added or changed

## Verification limitations

<!-- What could you NOT verify (tool not installed, OS not tested, network-only checks)? -->
