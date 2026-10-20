# CLI reference

`archonix [--version] COMMAND ...` — also runnable as `python -m archonix`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | negative result: validation failed, readiness `not-ready`, `--fail-on` threshold reached, smoke threshold failed |
| 2 | usage or input error |
| 3 | refused by policy (permission missing, write outside allowed location, installer conflict) |
| 4 | incomplete / unknown: readiness `incomplete`, or a check failed with `--fail-on-error` |

## Shared options

Commands that scan a repository accept:

| Option | Effect |
|---|---|
| `--mode {discovery,implementation,audit}` | permission defaults (default `discovery`) |
| `--allow-tools` | permit launching external tools (also lets `inventory` run `git status`) |
| `--allow-repo-code` | permit checks that execute repository code (tests) — `check`, `config show` |
| `--allow-network` | permit checks that use the network — `check`, `config show` |
| `--config FILE` | trusted config file; may grant permissions |
| `--no-repo-config` | ignore the repository's `archonix.toml` |
| `--exclude GLOB` | extra exclusion (repeatable) |
| `--max-files N` | stop scanning after N files |
| `--timeout SECONDS`, `--max-output-bytes N` | execution limits — `check`, `config show` |

Output options where shown: `--format`, `--out FILE` (refuses to overwrite unless
`--overwrite`).

## Commands

### `archonix inventory [PATH]`
Static inventory and stack detection. Reads files; never imports or executes repository
code. `--format md|json`.

```bash
archonix inventory . --format json --out inventory.json
```

### `archonix tools [--versions]`
Which supported tools are on PATH. `--versions` runs each tool's version command.

### `archonix config show [PATH]`
Effective configuration, the source of every value, and ignored repository settings.

### `archonix requirements validate FILE`
Schema plus semantic rules: unique IDs, known and acyclic dependencies, acceptance
criteria for approved work, critical-question gate, passing evidence for `verified`.

### `archonix requirements matrix FILE [--report REPORT ...]`
Acceptance traceability matrix. `check:<id>` evidence is resolved against the reports.

```bash
archonix requirements matrix docs/requirements.json --report .archonix/run/report.json
```

### `archonix check list`
Built-in checks, their requirements and verification status.

### `archonix check plan [PATH] [--checks a,b]`
What would run and why, or why not. Executes nothing.

### `archonix check run [PATH] [--checks a,b] [--out-dir DIR]`
Runs the permitted checks and builds a workflow report. Without `--out-dir` the report is
printed (`--format md|json`); with it, `report.json`, `report.md` and `artifacts/` are
written there (the directory must be new or empty unless `--overwrite`).
`--fail-on SEVERITY` exits 1 when findings at or above it exist; `--fail-on-error` exits 4
if a check failed or could not be parsed; `--workflow NAME` labels the report;
`--label-example` marks it as an example.

```bash
archonix check run . --mode audit --checks ruff,bandit --out-dir .archonix/run-1
archonix check run . --mode audit --allow-repo-code --checks pytest --format json
```

### `archonix validate FILE [--schema NAME]`
Validate a JSON document; the schema is inferred from `kind` when omitted.

### `archonix render FILE [--out FILE]`
Render a workflow report, readiness assessment, performance report, inventory or ledger
as Markdown.

### `archonix schema list`
List bundled schemas.

### `archonix readiness assess [--report R ...] [--ledger L] [--policy P]`
Policy-driven verdict: `ready` (exit 0), `not-ready` (1) or `incomplete` (4).

```bash
archonix readiness assess --policy examples/readiness-policy.toml \
  --report examples/reports/report.json --ledger examples/requirements/ledger.json
```

### `archonix architecture diagram [PATH] [--python-package DIR] [--depth N]`
Mermaid system-context diagram from the inventory, or a module import graph for a Python
package (parsed with `ast`). `--format md|mermaid`.

```bash
archonix architecture diagram examples/mixed-monorepo
archonix architecture diagram . --python-package src/archonix --format mermaid
```

### `archonix docs list` / `archonix docs init [PATH] --set NAME`
Project document templates for one workflow. Dry run unless `--apply`; writing also needs
`--allow-source-writes`; existing files are never overwritten.

```bash
archonix docs init . --set discovery --apply --allow-source-writes
```

### `archonix perf endpoints SPEC`
List endpoints from an OpenAPI JSON (or YAML with PyYAML installed) and flag GET/HEAD
endpoints without required parameters as smoke *candidates*.

### `archonix perf smoke --base-url URL --path P [...] --allow-network`
Bounded GET/HEAD smoke measurement. Options: `--requests` (≤500), `--concurrency` (≤10),
`--warmup` (≤20), `--timeout`, `--method GET|HEAD`, `--authorized-host HOST` (required
for non-loopback), `--auth-header-env VAR`, `--p95-ms`, `--max-error-rate`, `--revision`,
`--environment`, `--format md|json`, `--out`.

```bash
archonix perf smoke --base-url http://127.0.0.1:8000 --path /health --requests 100 --allow-network
```

### `archonix perf k6-script --base-url URL --path P [...]`
Generate a reviewable k6 scenario (`--vus`, `--duration`, `--p95-ms`, `--max-error-rate`,
`--out`). Archonix never runs load tests itself.

### `archonix install` / `archonix uninstall`
`--assistant {claude,codex,cursor}`, `--scope {user,project}`, `--project-dir DIR`,
`--apply`. Dry run without `--apply`. See [installation.md](installation.md).

### `archonix skill validate [PATH]` / `archonix skill path`
Validate a skill directory (frontmatter, name, description length, links, manifest
integrity); print the bundled skill location.
