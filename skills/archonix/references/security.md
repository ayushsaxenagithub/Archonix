# Security analysis

Combine maintained scanners with manual review. Confirm suspected defects with a local
reproduction against the code under review: a throwaway copy, synthetic data, a
temporary directory, and authorization to run the project's code. Never run exploit
payloads against live, shared or production systems or anyone else's services. Only
test running systems you are authorized to test. For a whole-codebase review, follow
`codebase-audit.md`.

## 1. Automated checks (when permitted)

`archonix check plan . --mode audit` shows which adapters apply:

| Check | Covers | Needs |
|---|---|---|
| `bandit` | Python security anti-patterns | tool |
| `ruff` (S rules) | flake8-bandit rules, when enabled in the repo's Ruff config | tool |
| `gitleaks` | secrets in working-tree files | tool |
| `semgrep-local` | repository-committed Semgrep rules | tool |
| `semgrep-registry` | Semgrep `p/default` registry rules | tool + network |
| `npm-audit` | npm dependency advisories (root lockfile) | tool + network |
| `osv-scanner` | dependency advisories from lockfiles in any directory (Python, npm, Go, Rust, Ruby, PHP, …) | tool + network |

Other maintained tools (manual workflow; no adapter yet): Trivy (images, IaC,
dependencies), pip-audit, ecosystem audit tools, and OWASP ZAP only against
authorized, isolated targets. Record their commands and outcomes the same way.

## 2. Manual review checklist

Authentication and sessions · object-level authorization and tenant isolation ·
injection (SQL, command, template, LDAP) and unsafe deserialization · secrets and
sensitive-data exposure · file uploads and path handling · input validation and output
encoding · cryptography and password storage · rate limits and abuse controls · webhook
signature verification · dependencies and supply chain (lockfiles, pinned CI actions,
install scripts) · infrastructure permissions (IAM, network exposure) · logging and error
disclosure · race conditions and unsafe state transitions.

## 3. Findings

Use `schemas/finding.schema.json`. Keep three kinds distinct:

- `scanner-reported` — tool output, not yet reviewed
- `verified` — you confirmed it with a local reproduction (record the steps and the
  observed result), or, where reproduction is not possible or not authorized, by
  tracing the exact code path (say which, and why no reproduction was run)
- `hypothesis` — plausible risk that needs confirmation

Severity (impact) and confidence (how sure) are separate. Preserve the tool's original
rule ID and severity. Provide remediation and references (CWE/OWASP) where known.
Record `docs/security-findings.md` from the template when the user wants a document.

## 4. Reporting limits

State which tools and rules ran, which were blocked or missing, and which areas were
reviewed manually. A clean scan is never a statement that the system is secure.
