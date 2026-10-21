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
| Skill entry point and workflow selection | Tested (structure); tested in Claude Code | `SKILL.md` validated (frontmatter, links, size). Claude Code 2.1.305 invoked the skill and followed the workflow in 4/4 acceptance tasks (opt-in run, 2026-10-21). Codex and Cursor not tested. |
| CLI acceptance suite (installed wheel, four scenario repositories) | Tested | `acceptance/cli_acceptance.py`; 60/60 locally; runs in the CI `build` job (tools not installed there are skipped) |
| Requirements ledger schema + semantic validation | Tested | IDs, dependencies, cycles, approval gates, evidence |
| Discovery document templates | Tested | `docs init --set discovery` |
| Acceptance traceability matrix | Tested | `check:<id>` evidence resolved against reports |
| Repository inventory (Python, JS/TS; manifests, lockfiles, configs, CI, containers, IaC) | Tested | Other languages: file counts and manifests only |
| Git revision / dirty status | Tested + real git | Dirty status needs `--allow-tools` |
| Tool availability and versions | Tested | |
| Safe subprocess execution (timeout, process-group kill, bounded output, minimal env) | Tested | |
| Execution records, findings, workflow reports (schemas, JSON + Markdown) | Tested | |
| Conservative finding deduplication | Tested | exact-identity merge; cross-tool overlaps linked |
| Layered secret redaction (output, details, limitations, retained artifacts incl. nested; unredactable artifacts reported) | Tested + real | best-effort, see trust model |
| Configuration precedence and restrict-only repo config | Tested | |
| Write boundaries, destructive gates (installer, docs init) | Tested | |
| ruff / bandit / vulture adapters | Tested + real | |
| pytest adapter (JUnit) | Tested + real | requires `--allow-repo-code` |
| gitleaks adapter | Tested + real | verified with gitleaks 8.30.1 locally and in the CI `secrets` job |
| semgrep-local adapter | Tested + real | real semgrep 1.182.0 in the CI `semgrep` job (findings, clean, invalid rules); semgrep tolerates some syntax errors without reporting them |
| semgrep-registry adapter | Tested (fixtures) + manual real run | needs the network to download `p/default`; verified by hand with 1.182.0, not in CI |
| npm audit adapter | Implemented, unverified here | network-dependent; not run |
| Release readiness (configurable policy) | Tested | |
| Inventory-derived Mermaid diagram | Tested | relationships labelled verified/inferred |
| Python module import graph (`ast`) | Tested | static imports only |
| Agent-assisted architecture diagrams, ADRs | Manual workflow | templates provided |
| OpenAPI endpoint listing | Tested | JSON; YAML needs PyYAML (untested) |
| API smoke measurement with percentile reliability | Tested | loopback server in tests |
| k6 scenario generation | Tested + real k6 | Archonix does not run load tests |
| Security manual review checklist | Manual workflow | |
| osv-scanner adapter (dependency vulnerabilities from lockfiles, multi-ecosystem) | Tested + real | real osv-scanner 2.7.0 locally and in the scheduled `Dependency audit` workflow (network); recorded fixtures in every CI run |
| Trivy, pip-audit, deptry, Knip, ESLint, tsc, mypy, ZAP adapters | Planned | manual workflow documented; pip-audit is lower priority because osv-scanner reads Python lockfiles without installing them |
| Dead-code cleanup proposals | Manual workflow | never automatic |
| Locust integration, revision-to-revision perf comparison | Planned | manual guidance only |
| Test stubs from acceptance criteria (`archonix tests scaffold`, pytest / Jest / Vitest) | Tested | stubs pending by default; real pytest and Vitest runs verified end to end (2026-10-21); Jest stubs checked as generated text only |
| Traceability from individual test results (pytest report cases, `--junit` for any runner, `test:<name>` refs) | Tested | JUnit formats recorded from pytest 9.1.1, Vitest 5.0.5, Jest 30.5.2 + jest-junit 17.0.0; jest `test.todo` detected as pending |
| Project agent context: `.ai/` → `AGENTS.md`, `CLAUDE.md` (`@AGENTS.md`), `.claude/skills`, `.agents/skills` (`archonix agents init` / `archonix agents sync`) | Tested (file generation, conflicts, symlink and manifest safety; acceptance AC-12) | Claude Code 2.1.305 loaded the generated `AGENTS.md` through the `CLAUDE.md` import and discovered the project skill (one manual run, 2026-10-21); Codex and Cursor not verified |
| Installer for Claude Code / Codex / Cursor | Tested (file layout) | assistant discovery not verified — see assistants.md |
| Installer path safety (manifest traversal, symlinked targets/subdirectories refused) | Tested | POSIX symlink tests; Windows not tested |
| Repository-local executables via relative `PATH` entries blocked | Tested | |
| CI: lint, types, tests, build smoke, markdownlint, gitleaks history scan | Configured; hosted runs recorded in GitHub Actions | see docs/ci.md |
| CI: dependency audit (pip-audit over uv.lock) | Configured (weekly / on dependency change); verified locally | network-dependent |
| Offline internal Markdown link check | Tested | external links are not checked |
| PyPI packaging (metadata, `twine check --strict`, isolated pipx install) | Verified locally; release workflow configured | not yet published; trusted-publisher setup is manual (docs/releasing.md) |
| Sandboxing of launched tools | Unsupported | use containers/VMs |
| Hosted service, telemetry, extra AI API | Unsupported by design | |
