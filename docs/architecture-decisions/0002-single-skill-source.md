# ADR-0002: One shared skill directory; thin assistant adapters

- Status: accepted
- Date: 2026-10-21

## Context

Claude Code, Codex and Cursor all read Agent Skills–style `SKILL.md` directories, but from
different locations and with different optional features and permission models.

## Decision

Ship a single self-contained `skills/archonix/` (instructions, references, templates,
schemas). Adapters are documentation plus installer target paths; they do not copy or
fork content. The wheel bundles the same directory for the installer.

## Alternatives

Per-assistant copies (drift); generating variants at build time (complexity without a
current need); keeping schemas/templates at the repository top level (manual installs
would need several copies).

## Consequences

Assistant-specific frontmatter is avoided. If an assistant needs a different format later,
an adapter may *generate* it from the shared source.
