# OpenAI Codex

- **Location:** user `~/.agents/skills/archonix/`; repository `.agents/skills/archonix/`
  (Codex scans `.agents/skills` from the working directory up to the repository root).
- **Install:** `archonix install --assistant codex --apply`, or
  `archonix install --assistant codex --scope project --project-dir . --apply`.
- **Invoke:** implicitly when the task matches the description, or explicitly with
  `$archonix` / `/skills` in the CLI or IDE extension.
- **Optional:** to disable implicit invocation, add `agents/openai.yaml` with
  `allow_implicit_invocation: false` inside the installed skill (Archonix does not ship it;
  the installer will report that file as unmanaged on later upgrades, which is expected).
- **Permissions:** Codex's sandbox and approval settings govern commands; Archonix does not
  modify them.
- **AGENTS.md:** Codex also reads `AGENTS.md`. You can reference Archonix there, but the
  skill does not require it.
- **Update / remove:** re-run install with `--apply`; `archonix uninstall --assistant codex --apply`.
- **Tested here:** install file layout and validation only. Not tested: Codex discovery.
