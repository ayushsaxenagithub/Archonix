# Installation

## Requirements

- Python **3.11 or newer** (uses the standard-library `tomllib`). CI tests 3.11–3.13.
- One runtime dependency: `jsonschema` (≥ 4.18).
- Optional tools Archonix can drive: ruff, bandit, vulture, pytest, gitleaks, semgrep,
  npm. None are required; missing tools are reported as skipped.

## Install the CLI

From a clone (no package has been published to PyPI):

```bash
git clone https://github.com/ayushsaxenagithub/Archonix.git
cd Archonix
pip install .              # into the active environment
# or isolated:
uv tool install .          # or: pipx install .
archonix --version
```

Building needs `hatchling`, which pip/uv download automatically.

## Install the skill

### With the CLI (recommended)

Every command below is a **dry run** until you add `--apply`.

```bash
archonix install --assistant claude                         # preview
archonix install --assistant claude --apply                 # ~/.claude/skills/archonix
archonix install --assistant codex --apply                  # ~/.agents/skills/archonix
archonix install --assistant cursor --apply                 # ~/.cursor/skills/archonix
archonix install --assistant claude --scope project --project-dir . --apply
archonix skill validate ~/.claude/skills/archonix           # check an installation
```

The installer:

- refuses to touch an existing `archonix` skill directory it did not create;
- records every file it writes, with its SHA-256, in `.archonix-manifest.json`;
- on upgrade, replaces only files that still match the manifest and reports files you
  edited as conflicts;
- removes files from older versions only if they are unchanged.

### Manually

Copy the whole skill directory; it is self-contained (instructions, templates, schemas):

```bash
mkdir -p ~/.claude/skills && cp -R skills/archonix ~/.claude/skills/      # Claude Code
mkdir -p ~/.agents/skills && cp -R skills/archonix ~/.agents/skills/      # Codex (also read by Cursor)
mkdir -p ~/.cursor/skills && cp -R skills/archonix ~/.cursor/skills/      # Cursor
```

Per-assistant details: [assistants.md](assistants.md) and [`adapters/`](../adapters/).

## Update

```bash
git pull && pip install .
archonix install --assistant claude --apply
```

## Remove

```bash
archonix uninstall --assistant claude              # preview
archonix uninstall --assistant claude --apply      # removes only unmodified managed files
pip uninstall archonix
```

Manual installs have no manifest; delete the directory yourself after checking it holds
nothing you want to keep.

## Verify the installation

```bash
archonix --version
archonix skill validate
archonix tools
archonix check list
```
