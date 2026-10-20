# Assistant compatibility

The skill is one directory in the [Agent Skills](https://agentskills.io) layout
(`SKILL.md` with `name`/`description` frontmatter plus supporting files). Each assistant
discovers it from a different location. Discovery paths below were checked against the
vendors' official documentation on **2026-10-21**; assistants change quickly, so
re-check if something does not load.

## Matrix

| Assistant | Install location (user / project) | Invocation | Status |
|---|---|---|---|
| Claude Code | `~/.claude/skills/archonix/` / `.claude/skills/archonix/` | automatic from the description, or `/archonix` | **Documented, install layout tested; discovery by the assistant not verified here** |
| OpenAI Codex (CLI/IDE) | `~/.agents/skills/archonix/` / `.agents/skills/archonix/` (scanned from cwd up to repo root) | automatic, or `$archonix` / `/skills` | **Documented, install layout tested; discovery not verified here** |
| Cursor | `~/.cursor/skills/archonix/` / `.cursor/skills/archonix/`; also reads `.agents/skills`, `.claude/skills`, `.codex/skills` | automatic, or `/archonix` in Agent chat | **Documented, install layout tested; discovery not verified here** |
| Other Agent Skills–compatible tools | tool-specific | tool-specific | Unverified — copy `skills/archonix/` where the tool looks for skills |
| Assistants without skill support | — | paste or reference `SKILL.md` as instructions | Manual; progressive loading of references depends on the assistant reading files |

"Install layout tested" means automated tests confirm that `archonix install` writes a
valid skill (frontmatter, name matching the directory, description ≤ 1024 characters,
working relative links) to the documented path, and that upgrade/removal behave safely.
No test in this repository launches an assistant and observes it load the skill, because
that requires each vendor's account and sends data to their service.

## Sources

- Claude Code skills: <https://code.claude.com/docs/en/skills>
- Codex skills: <https://developers.openai.com/codex/skills> (redirects to
  <https://learn.chatgpt.com/docs/build-skills>)
- Cursor skills: <https://cursor.com/docs/context/skills>

## Differences that matter

- **Permissions.** Each assistant has its own approval model for shell commands and file
  edits. Archonix's execution policy is guidance to the assistant plus enforcement inside
  the `archonix` CLI only; it does not change the assistant's settings.
- **Duplicates.** Cursor also reads `.claude/skills` and `.agents/skills`. If you install
  for several assistants in one project, Cursor may list the skill more than once; install
  once into `.agents/skills` for Codex + Cursor, and `.claude/skills` for Claude Code.
- **Invocation control.** None of the assistants needs extra frontmatter for Archonix.
  If you want explicit-only invocation, Claude Code and Cursor support
  `disable-model-invocation: true` and Codex supports `allow_implicit_invocation: false` in
  `agents/openai.yaml`; Archonix does not set these by default.
- **CLI availability.** The skill works without the CLI; with it, the assistant can
  produce schema-valid evidence. Make sure `archonix` is on the PATH the assistant uses.

Per-assistant notes: [`adapters/claude-code`](../adapters/claude-code/README.md),
[`adapters/codex`](../adapters/codex/README.md), [`adapters/cursor`](../adapters/cursor/README.md).
