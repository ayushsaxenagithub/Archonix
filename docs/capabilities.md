# Capabilities and status

Status labels:

- **Tested** — implemented and covered by automated tests in this repository (fixture
  tests; "+ real" means a real-tool integration test also ran in the development
  environment).
- **Implemented, unverified here** — code exists and is fixture-tested, but the real tool
  was not available to verify against.
- **Manual workflow** — documented instructions in the skill; no automation.
- **Planned / unsupported** — not available in v0.1.

| Capability | Status | Notes |
|---|---|---|
| Skill entry point and workflow selection | Tested (structure) | `SKILL.md` validated (frontmatter, links, size). Whether an assistant follows it is not machine-verified. |
| Requirements ledger schema + semantic validation | Tested | IDs, dependencies, cycles, approval gates, evidence |
| Discovery document templates | Tested | `docs init --set discovery` |
| Acceptance traceability matrix | Tested | `check:<id>` evidence resolved against reports |
| Repository inventory (Python, JS/TS; manifests, lockfiles, configs, CI, containers, IaC) | Tested | Other languages: file counts and manifests only |
| Git revision / dirty status | Tested + real git | Dirty status needs `--allow-tools` |
| Tool availability and versions | Tested | |
| Safe subprocess execution (timeout, process-group kill, bounded output, minimal env) | Tested | |
| Execution records, findings, workflow reports (schemas, JSON + Markdown) | Tested | |
| Conservative finding deduplication | Tested | exact-identity merge; cross-tool overlaps linked |
| Layered secret redaction | Tested + real | best-effort, see trust model |
| Configuration precedence and restrict-only repo config | Tested | |
| Write boundaries, destructive gates (installer, docs init) | Tested | |
| ruff / bandit / vulture adapters | Tested + real | |
| pytest adapter (JUnit) | Tested + real | requires `--allow-repo-code` |
| gitleaks adapter | Implemented, unverified here | gitleaks not installed in the dev environment |
| semgrep (local rules / registry) adapters | Implemented, unverified here | semgrep not installed |
| npm audit adapter | Implemented, unverified here | network-dependent; not run |
| Release readiness (configurable policy) | Tested | |
| Inventory-derived Mermaid diagram | Tested | relationships labelled verified/inferred |
| Python module import graph (`ast`) | Tested | static imports only |
| Agent-assisted architecture diagrams, ADRs | Manual workflow | templates provided |
| OpenAPI endpoint listing | Tested | JSON; YAML needs PyYAML (untested) |
| API smoke measurement with percentile reliability | Tested | loopback server in tests |
| k6 scenario generation | Tested + real k6 | Archonix does not run load tests |
| Security manual review checklist | Manual workflow | |
| Trivy, OSV-Scanner, pip-audit, deptry, Knip, ESLint, tsc, mypy, ZAP adapters | Planned | manual workflow documented |
| Dead-code cleanup proposals | Manual workflow | never automatic |
| Locust integration, revision-to-revision perf comparison | Planned | manual guidance only |
| Installer for Claude Code / Codex / Cursor | Tested (file layout) | assistant discovery not verified — see assistants.md |
| Sandboxing of launched tools | Unsupported | use containers/VMs |
| Hosted service, telemetry, extra AI API | Unsupported by design | |
