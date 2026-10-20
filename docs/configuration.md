# Configuration reference

Archonix reads TOML configuration validated against
[`config.schema.json`](../skills/archonix/schemas/config.schema.json).
`archonix config show .` prints the effective values and where each came from.

## Precedence (lowest → highest)

1. Built-in defaults, including the selected `--mode`'s permission defaults
2. User config — `$ARCHONIX_USER_CONFIG`, else `$XDG_CONFIG_HOME/archonix/config.toml`,
   else `~/.config/archonix/config.toml` (`ARCHONIX_USER_CONFIG=none` disables it)
3. Repository config — `archonix.toml` or `.archonix.toml` at the scanned root (not if it
   is a symlink; skipped with `--no-repo-config`)
4. Explicit `--config FILE`
5. Environment — `ARCHONIX_TIMEOUT_SECONDS`, `ARCHONIX_MAX_OUTPUT_BYTES`
6. Command-line flags

`inventory.exclude` and the redaction lists are **additive** across layers; other values
are replaced by higher layers.

## Trust: repository config is restrict-only

The repository is controlled by whoever wrote it, so in `archonix.toml`:

- `permissions.* = false` is honoured; `permissions.* = true` is **ignored**;
- `execution.env_passthrough` is **ignored** (it could pass your credentials to tools);
- `checks.<id>.extra_args` is **ignored** (it could make a tool load arbitrary code);
- `redaction.extra_patterns` is **ignored** (a crafted regular expression could stall
  redaction); `redaction.sensitive_env_names` is still honoured.

Exclusions added by repository config are honoured (they also apply to scanners) and are
listed in every report's `limitations`, so a repository cannot silently hide files.

Ignored settings are listed by `config show`, `check plan` and in reports under
`policy.ignored_settings` and `limitations`. User config and `--config` are trusted and
may set all of these.

## Keys

```toml
schema_version = "0.1"

[inventory]
exclude = ["fixtures", "docs/generated"]  # glob on directory/file name or relative path
max_files = 20000                         # scan stops and reports truncation
max_file_bytes = 1000000                  # larger manifests are listed but not parsed

[execution]
timeout_seconds = 300                     # per check; process group is killed on expiry
max_output_bytes = 2000000                # per stream; larger output is truncated and not parsed
env_passthrough = ["JAVA_HOME"]           # trusted layers only; added to the minimal base env

[permissions]                             # see trust-model.md
source_writes = false
artifact_writes = true
repo_code = false
external_tools = false
network = false
dependency_install = false
shared_environment = false
destructive = false

[redaction]
sensitive_env_names = ["INTERNAL_SERVICE_KEY"]   # values of these env vars are masked
extra_patterns = ["ACME-[0-9]{6}"]               # Python regexes; trusted layers only

[checks.bandit]
enabled = true
timeout_seconds = 120
extra_args = ["--severity-level", "medium"]      # trusted layers only
```

Default exclusions: `.git`, `.hg`, `.svn`, `node_modules`, `.venv`, `venv`, `env`,
`__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `.tox`, `.nox`, `.cache`,
`dist`, `build`, `.next`, `.nuxt`, `.turbo`, `coverage`, `htmlcov`, `.idea`, `.vscode`,
`target`, `vendor`, `.gradle`, `.terraform`, `.archonix`, `*.egg-info`.

## Mode defaults

| Permission | discovery | audit | implementation |
|---|---|---|---|
| artifact_writes | on | on | on |
| external_tools | off | on | on |
| repo_code | off | off | on |
| source_writes | off | off | on |
| network, dependency_install, shared_environment, destructive | off | off | off |

## Readiness policy file

Separate TOML file passed with `--policy`; see
[`examples/readiness-policy.toml`](../examples/readiness-policy.toml). Rules not listed
in a custom policy are not evaluated; unknown rule names are an error.
