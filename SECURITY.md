# Security policy

## Reporting a vulnerability

Do **not** put vulnerability details in a public issue, pull request or discussion.

GitHub private vulnerability reporting is **not currently enabled** on this repository
(checked 2026-10-21), so the "Report a vulnerability" button is not available. Until it
is enabled:

1. Open a public issue titled **"Security contact request"** that contains *no* details
   of the problem — only that you have something to report privately.
2. The maintainer will reply with a private channel (for example a draft security
   advisory that you are invited to).
3. Then share the affected version or commit, reproduction steps and impact.

If the Security tab does show "Report a vulnerability", use that instead; this file will
be updated when the setting changes. This is a volunteer project with no guaranteed
response window; please allow reasonable time before any public disclosure.

## Scope

In scope: the `archonix` Python package and CLI (for example: a way to make it execute a
check that the effective policy should block, write outside the selected output location,
escape the installer's manifest boundaries, or persist an unredacted value that a
documented redaction layer should have caught), and the skill instructions where they
would lead an assistant to bypass the documented trust model.

Out of scope: vulnerabilities in third-party tools Archonix launches (report those
upstream), behaviour of the host AI assistant, and secrets that match no documented
redaction pattern (redaction is documented as best-effort).

## What Archonix does and does not protect

Archonix is **not a sandbox**. Its CLI decides which tools to launch and confines its own
writes, but a launched tool runs with your privileges. Running tests or some linters on a
repository executes that repository's code. See [docs/trust-model.md](docs/trust-model.md).

Never commit real credentials to this repository; all examples use synthetic values.
