# Claude Code

- **Location:** personal `~/.claude/skills/archonix/`; project `.claude/skills/archonix/`
  (commit it to share with a team).
- **Install:** `archonix install --assistant claude --apply`, or
  `archonix install --assistant claude --scope project --project-dir . --apply`, or copy
  `skills/archonix/` there manually.
- **Invoke:** ask for an Archonix workflow (the description triggers automatic loading) or
  type `/archonix`.
- **Required features:** skills support; file reading for progressive loading of
  `references/`. Running the CLI requires shell access approved in Claude Code.
- **Permissions:** Claude Code's own permission prompts/allowlists govern shell commands
  and edits. Archonix's policy is guidance plus CLI enforcement; it does not change them.
- **Update / remove:** re-run install with `--apply`; `archonix uninstall --assistant claude --apply`.
- **Troubleshooting:** frontmatter must start on line 1; if you created the skills
  directory during a session, use `/reload-skills` or restart.
- **Tested here:** install/upgrade/uninstall file layout and skill validation (automated).
  Not tested: Claude Code loading and following the skill.
