# Project agent context (`.ai/`)

One source of truth for the instructions and skills *your* project gives to AI coding
assistants, rendered into the files each assistant reads.

`.ai/` is an Archonix convention, not an assistant standard; no assistant reads it
directly. `archonix agents sync` renders it into the locations below.

## Layout

```text
.ai/
├── instructions.md          # project-wide agent instructions (you own this file)
├── skills/<name>/SKILL.md   # project skills (Agent Skills format), loaded on demand
└── .sync-manifest.json      # written by sync: every generated file and its SHA-256
```

Generated outputs:

| Output | Read by | Source |
|---|---|---|
| `AGENTS.md` | Codex, Cursor, Claude Code 2.1.277+ (when no `CLAUDE.md` exists) | `.ai/instructions.md` plus a "generated" header |
| `CLAUDE.md` containing `@AGENTS.md` | Claude Code, including sessions and versions that read only `CLAUDE.md` | generated only if no `CLAUDE.md` exists |
| `.claude/skills/<name>/` | Claude Code | `.ai/skills/<name>/` (target `claude`) |
| `.agents/skills/<name>/` | Codex, and Cursor (which also reads `.agents/skills`) | `.ai/skills/<name>/` (target `agents`) |

Verified against vendor documentation on 2026-10-21:

- [Claude Code memory](https://code.claude.com/docs/en/memory) covers `AGENTS.md` support and `@AGENTS.md` imports.
- [Cursor rules](https://cursor.com/docs/context/rules) covers `AGENTS.md` at the root and in subdirectories.
- The skill locations are listed in [assistants.md](assistants.md).

## Workflow

```bash
archonix agents init .                                   # preview what would be drafted
archonix agents init . --apply --allow-source-writes     # draft .ai/ (never overwrites)
# review and edit .ai/instructions.md and .ai/skills/
archonix agents sync .                                   # preview outputs
archonix agents sync . --apply --allow-source-writes     # write AGENTS.md, CLAUDE.md, skills
archonix agents sync . --check                           # CI: exit 1 if outputs are stale
```

`init` drafts the files from static evidence only:

- the inventory (stack, layout, test and lint tools);
- `package.json` scripts;
- `docs/requirements.json`, if it is valid.

From the ledger it also writes a `<project>-requirements` skill holding the requirements
and acceptance criteria. Anything it cannot infer (purpose, conventions) is left as
`TODO`, never invented.

## Safety

- Both commands are dry runs unless `--apply`, and writing needs `--allow-source-writes`.
- `sync` never overwrites a file it did not write, or one you edited after it wrote it.
  Both cases are reported as conflicts. Edit `.ai/` instead.
- An existing hand-written `CLAUDE.md` is left alone. `sync` tells you to add a line
  `@AGENTS.md` to it.
- Skills that fail validation are skipped with a note. A skill removed from `.ai/` is
  removed from the outputs only if its generated copy is unchanged.
- No writes or deletes go through symlinks, and manifest entries that point outside the
  repository are refused.

## Limitations

- The draft is a starting point. A human or the assistant must fill in the TODOs and
  check the detected stack.
- Only the repository root is handled; nested `AGENTS.md` files for subprojects are not
  generated.
- Path-scoped rules (`.claude/rules/`, `.cursor/rules/`) are not generated yet.
