# Product discovery

Use for a new product or a substantial feature. For a small change, write a short change
note instead (`archonix docs init --set change-note`).

## 1. Gather before asking

Read existing specs, tickets, READMEs, ADRs, the requirements ledger and relevant code.
Many answers are already there.

## 2. Ask only material questions

Ask when the answer changes behaviour, architecture, security, cost or delivery. Prefer
one question at a time. Cover, where relevant:

- purpose and intended outcomes; target users, roles, permissions, key journeys
- core features and explicit exclusions
- business rules, calculations, validations, state transitions; edge and failure cases
- integrations and external systems
- data model, ownership, retention, audit needs
- authentication, authorization, tenant boundaries; privacy and regulatory constraints
- scale, latency, availability, reliability; accessibility, localization, devices
- deployment environment and operational constraints; budget and delivery constraints
- acceptance criteria and definition of done

## 3. Maintain the requirements ledger

Keep `docs/requirements.json` valid against `schemas/requirements.schema.json`:
stable ID (`REQ-001`), description, source (`user-confirmed`, `document`,
`repository-evidence`, `inferred`, `assumption`), priority (`must/should/could/wont`),
acceptance criteria (`AC-…`), dependencies, status, open questions (flag `critical`),
assumptions and verification method/evidence. Validate with
`archonix requirements validate docs/requirements.json`.

## 4. Discovery completion gate (substantial work)

Prepare, from `archonix docs init --set discovery` or the templates:
`docs/product-spec.md`, `docs/user-journeys.md`, `docs/business-rules.md`,
`docs/acceptance-criteria.md`, `docs/open-questions.md`.

Then summarize the proposed scope and get confirmation **only** for material decisions
not already approved. Critical unknowns must be answered or explicitly accepted as
assumptions (`accepted_as_assumption: true`) before requirements become `approved`;
non-critical unknowns can stay documented. Existing explicit authorization that covers
the scope counts — do not ask again.

## 5. Project agent context

Once requirements are approved, give every assistant the same project context:
`archonix agents init . --apply --allow-source-writes` drafts `.ai/instructions.md`, and
a requirements skill from the ledger. Fill in its TODOs, then run
`archonix agents sync . --apply --allow-source-writes` to write `AGENTS.md`, `CLAUDE.md`
and the skill folders. Both write into the repository, so they need the user's approval
for source changes.

## 6. Stack proposals (new projects)

Propose a stack with trade-offs (team familiarity, hosting, cost, ecosystem maturity,
security posture) and get approval when the choice materially affects the product.
Record the decision as an ADR (`templates/adr.md`).
