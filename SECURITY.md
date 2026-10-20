# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately using GitHub's **"Report a vulnerability"**
(private vulnerability reporting) on this repository's Security tab. Do not open a
public issue for security problems. Include affected version/commit, reproduction steps
and impact. We aim to acknowledge reports within a reasonable time; this is a volunteer
project with no guaranteed response window.

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
