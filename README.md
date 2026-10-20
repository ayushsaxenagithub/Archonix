# Archonix

**From product understanding to production-ready software.**

Archonix is an open-source, model-agnostic software engineering skill system for AI
coding assistants. It gives an assistant structured workflows for understanding a product
or codebase, discovering requirements, designing and implementing changes, validating
behaviour, investigating risks and assessing release readiness, plus a small Python CLI
that produces the repeatable evidence those workflows rely on.

> Status: **v0.1, alpha.** Archonix does not make software secure or production-ready on
> its own. It helps an assistant (and you) work from evidence and report honestly about
> what was and was not verified. See [docs/capabilities.md](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/capabilities.md) for
> exactly what is implemented and tested.

## What is in the box

| Part | Path | What it is |
|---|---|---|
| Skill entry point | [`skills/archonix/SKILL.md`](https://github.com/ayushsaxenagithub/Archonix/blob/main/skills/archonix/SKILL.md) | Workflow selection and operating rules (Agent Skills format) |
| Workflow references | [`skills/archonix/references/`](https://github.com/ayushsaxenagithub/Archonix/tree/main/skills/archonix/references) | Discovery, implementation, bugs, review, testing, security, dead code, performance, release, architecture — loaded only when needed |
| Templates | [`skills/archonix/templates/`](https://github.com/ayushsaxenagithub/Archonix/tree/main/skills/archonix/templates) | Documents Archonix generates in *your* project (spec, journeys, ADRs, findings, …) |
| Schemas | [`skills/archonix/schemas/`](https://github.com/ayushsaxenagithub/Archonix/tree/main/skills/archonix/schemas) | Versioned JSON Schemas (v0.1) for requirements, config, inventory, executions, findings, reports, readiness, performance |
| CLI | [`src/archonix/`](https://github.com/ayushsaxenagithub/Archonix/tree/main/src/archonix) | Deterministic helpers: inventory, check planning/execution, report validation/rendering, readiness, diagrams, installer |
| Adapters | [`adapters/`](https://github.com/ayushsaxenagithub/Archonix/tree/main/adapters) | Thin install/usage notes for Claude Code, OpenAI Codex and Cursor |
| Examples | [`examples/`](https://github.com/ayushsaxenagithub/Archonix/tree/main/examples) | Synthetic repositories and example reports (clearly labelled) |

The skill content is the same for every assistant; adapters only document where each
assistant looks for skills.

## Quickstart

Requires Python 3.11+. Install the CLI in its own environment:

```bash
pipx install archonix              # from PyPI, once a release is published there
# or from source (always works):
git clone https://github.com/ayushsaxenagithub/Archonix.git
cd Archonix
pipx install .                     # or: uv tool install .   /   pip install .
```

The commands below use the synthetic projects in a clone of the repository:

```bash
archonix --version
archonix inventory examples/python-service          # static: reads files, runs nothing
archonix check plan examples/python-service --mode audit
```

Run a real check-to-report flow (needs any of `ruff`, `bandit`, `vulture` on PATH;
`pip install ruff bandit vulture`):

```bash
archonix check run examples/python-service --mode audit --out-dir /tmp/archonix-demo
archonix validate /tmp/archonix-demo/report.json
less /tmp/archonix-demo/report.md
```

Install the skill for your assistant (dry run first, then `--apply`):

```bash
archonix install --assistant claude                 # ~/.claude/skills/archonix
archonix install --assistant claude --apply
archonix install --assistant codex --scope project --project-dir . --apply   # .agents/skills/archonix
```

Without the CLI you can copy `skills/archonix/` into the assistant's skills directory by
hand; see [docs/installation.md](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/installation.md).

Then ask your assistant things like *"Use Archonix to understand this repository"*,
*"Discover requirements for a team invoicing feature"*, *"Fix this bug with Archonix"* or
*"Run an Archonix security audit"*.

## How it works

```mermaid
flowchart LR
  user([User request]) --> skill[SKILL.md: pick the smallest workflow]
  skill --> refs[Load only the relevant reference]
  refs --> cli{{archonix CLI, if installed}}
  cli --> inv[inventory: static, no execution]
  cli --> plan[check plan: what would run and why]
  plan --> run[check run: permitted tools only]
  run --> report[(report.json + report.md)]
  report --> ready[readiness assess: ready / not-ready / incomplete]
  ledger[(requirements ledger)] --> ready
```

- **Evidence over assumptions.** Every execution is recorded with command, cwd, tool
  version, UTC start time, duration, exit status and its tool-specific meaning, counts and
  parsing limitations. Unknown counts stay `null`.
- **Safe defaults.** Discovery mode executes nothing and uses no network. Running external
  tools, repository code (tests) or network-backed scanners each needs its own permission.
  Repository config can only *restrict* permissions. See
  [docs/trust-model.md](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/trust-model.md).
- **Honest results.** Tool findings are kept separate from tool failures; missing evidence
  makes a readiness verdict `incomplete`, never `ready`; a clean scan is never described as
  proof of security.

## Documentation

- [Installation](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/installation.md) · [CLI reference](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/cli.md) ·
  [Configuration](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/configuration.md) · [Workflows](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/workflows.md)
- [Permission and trust model](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/trust-model.md) · [Tool adapters](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/tool-adapters.md)
- [Assistant compatibility](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/assistants.md) · [Capabilities and status](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/capabilities.md)
- [Architecture](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/architecture.md) · [Decision records](https://github.com/ayushsaxenagithub/Archonix/tree/main/docs/architecture-decisions)
- [Troubleshooting](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/troubleshooting.md) · [Limitations and roadmap](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/roadmap.md)
- [Changelog](https://github.com/ayushsaxenagithub/Archonix/blob/main/CHANGELOG.md) ·
  [Releasing](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/releasing.md) ·
  [Continuous integration](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/ci.md) · [Maintainer policy](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/maintainers.md) ·
  [Good first issues](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/good-first-issues.md) · [Audit 2026-10](https://github.com/ayushsaxenagithub/Archonix/blob/main/docs/audits/2026-10-community-readiness.md)
- [Contributing](https://github.com/ayushsaxenagithub/Archonix/blob/main/CONTRIBUTING.md) · [Security policy](https://github.com/ayushsaxenagithub/Archonix/blob/main/SECURITY.md) · [Agent instructions](https://github.com/ayushsaxenagithub/Archonix/blob/main/AGENTS.md)

## License

[MIT](https://github.com/ayushsaxenagithub/Archonix/blob/main/LICENSE).
