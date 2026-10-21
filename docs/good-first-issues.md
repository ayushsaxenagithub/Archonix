# Good first issues

Starter tasks drawn from real gaps in v0.1. Each is small, self-contained and has a clear
test. Comment on (or open) a matching issue before starting so work is not duplicated.

1. **deptry adapter.** Add `DeptryAdapter` (`requires`: tool only; deptry parses imports
   without running code) that runs `deptry . --json-output <artifact>` and maps unused,
   missing and transitive dependency issues to `dead-code`/`dependency` findings. Start
   from `OsvScannerAdapter` in `src/archonix/adapters/dependency_tools.py`; record fixtures
   from a real run in `tests/fixtures/tool-output/`.
2. **Strip ANSI colour codes from stored excerpts.** gitleaks writes coloured log lines to
   stderr, which end up in `executions[].stderr.excerpt`. Strip escape sequences in
   `checks._stream` and test it with a fake tool that prints colour codes.
3. **Docker Compose image detection.** `inventory.py` detects Compose files but not the
   services they run (e.g. `image: postgres:16`). Parse `image:` lines conservatively
   (no YAML dependency) and record them as `file-pattern` detections with evidence.
4. **`archonix check list --format md` adds a "Tested" column** derived from adapter
   status, so the CLI output matches `docs/capabilities.md`. Test the rendered table.
5. **Troubleshooting entry for Windows paths.** Document what is and is not supported on
   Windows today (process-group termination, symlink tests) in `docs/troubleshooting.md`,
   keeping claims to what `runner.py` actually does.
6. **Inventory: `go.mod` dependency parsing.** Parse `require` blocks and map a few common
   modules (gin, echo, pgx) to detections, mirroring `_parse_package_json`.

For each: run `uv run pytest`, `uv run ruff check .` and `uv run mypy`, and fill in the
pull-request template.
