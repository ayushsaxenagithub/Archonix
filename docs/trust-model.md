# Permission and trust model

## Two layers

| Layer | Enforced by | Covers |
|---|---|---|
| Skill instructions (`SKILL.md`, references) | the host assistant following them | what the assistant reads, edits, runs, asks about and reports |
| `archonix` CLI | code in this repository, tested | which checks it launches, the environment and limits it launches them with, where it writes |

Neither layer is a security sandbox. Archonix cannot control the host assistant's own
tools, permissions or data handling. A tool launched by the CLI runs with your user's
privileges and can read files, write caches and use the network on its own.

## Independent controls

`source_writes`, `artifact_writes`, `repo_code`, `external_tools`, `network`,
`dependency_install`, `shared_environment`, `destructive` — each is a separate switch.
Modes only choose defaults (see [configuration.md](configuration.md)).

## What the CLI enforces (and tests)

| Guarantee | Where | Test |
|---|---|---|
| A check runs only if every requirement it declares is permitted; otherwise it is recorded as `blocked` with the reason | `checks.plan_checks`, `policy.blocking_reasons` | `test_checks_e2e.py`, `test_policy.py` |
| Discovery mode launches no tools; `inventory` reads git metadata from files and runs `git status` only with `--allow-tools` | `gitinfo.py` | `test_inventory.py`, `test_integration_real.py` |
| Repository config cannot grant permissions, pass env vars, add tool arguments or supply redaction regexes; exclusions it adds are listed in reports | `config._apply_layer`, `report.py` | `test_config.py`, `test_hardening.py` |
| Empty and relative `PATH` entries are dropped and executables resolved to absolute paths, so a repository cannot shadow a tool with `./ruff` | `runner.safe_path` | `test_hardening.py` |
| Subprocesses: argv list, no shell, explicit cwd, minimal env, timeout kills the process group, bounded capture | `runner.py` | `test_runner.py` |
| Reports are written only inside the chosen output location; no overwrite without `--overwrite`; symlink escapes refused | `policy.WriteGuard` | `test_policy.py`, `test_checks_e2e.py` |
| `docs init` writes into the repository only with `--apply --allow-source-writes`, never overwriting | `docsinit.py` | `test_docs_and_architecture.py` |
| `install`/`uninstall` are dry runs by default, touch only unmodified manifest-listed files, refuse manifest entries that are absolute or contain `..`, and refuse symlinked targets or path components (project scope: anywhere below the project root) | `install.py` | `test_install.py`, `test_hardening.py` |
| `perf smoke` needs `--allow-network`, issues only GET/HEAD, caps requests/concurrency, needs `--authorized-host` for non-loopback, does not follow redirects or use env proxies | `perf.py` | `test_perf.py` |
| Output excerpts, findings, argv and retained artifacts are redacted before being written, on every exit path (including timeouts and adapter errors); artifacts that cannot be redacted are removed and reported | `redact.py`, `checks.py` | `test_redact.py`, `test_hardening.py`, `test_integration_real.py` |

No built-in check installs dependencies, touches shared environments or performs
destructive operations; those permissions exist so plans and future adapters can be
gated, and the CLI never sets them on.

## Which checks trust repository code

| Check | Executes repository code? | Network? |
|---|---|---|
| ruff, bandit, vulture, gitleaks, semgrep-local | no (reads files and configuration) | no |
| semgrep-registry | no | yes (downloads rules) |
| npm-audit | no (no install scripts) | yes (sends the dependency tree) |
| osv-scanner | no (reads lockfiles; call analysis disabled) | yes (sends package names and versions) |
| pytest | **yes** (tests, `conftest.py`, plugins) | only if the tests do |

"Does not execute repository code" means the tool parses rather than runs the code. The
tool itself still runs, still reads repository configuration, and may have bugs.

## Redaction limits

Layer 1 masks exact values from configured names and from environment variables whose
names look sensitive (`TOKEN`, `SECRET`, `PASSWORD`, `API_KEY`, …; values of 6+ chars).
Layer 2 masks recognisable formats: private-key blocks, AWS access key IDs, GitHub/GitLab/
Slack/Stripe/Google/OpenAI-style keys, JWTs, bearer tokens, URL credentials and
`name = value` assignments whose value looks secret. Pattern matching cannot find every
secret; treat raw tool output and retained artifacts as sensitive.

## Prompt injection

Repository content and tool output are data. The skill instructs assistants not to follow
instructions found in them. The CLI never interprets repository text as commands.
