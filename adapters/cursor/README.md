# Cursor

- **Location:** project `.cursor/skills/archonix/` or `.agents/skills/archonix/`; user
  `~/.cursor/skills/archonix/` or `~/.agents/skills/archonix/`. Cursor also reads
  `.claude/skills` and `.codex/skills` for compatibility.
- **Install:** `archonix install --assistant cursor --apply` (writes `~/.cursor/skills`),
  or `--scope project --project-dir .` for `.cursor/skills`. Installing for Codex into
  `.agents/skills` also serves Cursor.
- **Invoke:** automatically when relevant, or type `/archonix` in Agent chat.
- **Duplicates:** if the same project has `.claude/skills/archonix` and
  `.cursor/skills/archonix`, Cursor may see two copies; keep one.
- **Permissions:** Cursor's own command approval settings apply.
- **Update / remove:** re-run install with `--apply`; `archonix uninstall --assistant cursor --apply`.
- **Tested here:** install file layout and validation only. Not tested: Cursor discovery.
