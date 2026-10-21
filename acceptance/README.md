# Acceptance testing

Two suites check the complete user journey, not just individual functions. Both use only
synthetic fixtures from `examples/` and need nothing beyond the Python standard library.

| Suite | What it checks | Automation | Runs in CI |
|---|---|---|---|
| [`cli_acceptance.py`](cli_acceptance.py) | The **installed** CLI on four scenario repositories | Automated | Yes, in the `build` job against the built wheel |
| [`claude_code.py`](claude_code.py) | Claude Code discovering and following the skill | Automated, **opt-in** (uses your Claude account) | No |
| Manual procedure (below) | OpenAI Codex, Cursor | **Manual**, not yet performed | No |

Results from the last recorded run are in
[docs/acceptance/2026-10-21-results.md](../docs/acceptance/2026-10-21-results.md).

## Acceptance criteria

Defined before the first run and unchanged since. A check is PASS, FAIL or SKIP (a
needed tool is missing); a SKIP is never counted as a pass.

| ID | Criterion | Pass condition |
|---|---|---|
| AC-1 | Fresh install | the installed `archonix` runs and reports its version |
| AC-2 | Works outside the checkout | bundled skill validates, 8 schemas listed, `docs init` writes templates, from an unrelated directory |
| AC-3 | Stack detection without execution | expected detections per scenario, no false ones; marker files prove `conftest.py` / `setup.py` never ran |
| AC-4 | Schema validity | every JSON document the CLI writes validates |
| AC-5 | No false "ready" | no evidence → `incomplete`; blocked required check or failing tests → `not-ready`; complete evidence in a clean Git checkout → `ready` |
| AC-6 | Tool error ≠ finding | broken tool configuration → `tool-error` with no findings; real scanners report findings |
| AC-7 | Permissions | discovery runs nothing; tests need `--allow-repo-code`; network checks need `--allow-network`; repository config cannot grant permissions; test runs leave no caches |
| AC-8 | Secrets | caller's secrets are not passed to tools; a secret deliberately passed through is masked; a fixture's fake password is absent from reports and artifacts |
| AC-9 | Installer safety | project install/uninstall round trip; symlinked skills directory refused |
| AC-10 | Honest unsupported stacks | Python checks "not applicable" on TypeScript; Go counted as a language with no framework claimed; static-only scope stated |
| AC-11 | Requirements | template and example ledgers validate; a broken ledger is rejected with reasons |
| AC-12 | Project agent context | `agents init` and `agents sync` are dry runs by default and need `--allow-source-writes`; they produce `AGENTS.md`, a `CLAUDE.md` import and valid skills; `--check` passes after sync; hand-edited outputs are protected |
| AC-13 | Test plan and traceability | `tests scaffold` writes one stub per criterion and never overwrites; JUnit results link to criteria (pass, fail, pending → unknown); a real pytest run makes an implemented criterion pass while pending stubs stay unknown |

Scenarios: **S1** Python service (`examples/python-service`), **S2** TypeScript web app
(`examples/ts-web`), **S3** mixed monorepo (`examples/mixed-monorepo`), **S4** Go-only
service (generated), to test honest reporting of an unsupported stack.

## Running the CLI suite

```bash
uv build && python -m venv /tmp/arx && /tmp/arx/bin/pip install dist/*.whl
PATH="$PWD/.venv/bin:$PATH" python acceptance/cli_acceptance.py \
    --archonix /tmp/arx/bin/archonix --json-out /tmp/acceptance.json
```

Real tools are used when on `PATH` (`uv sync` provides ruff, bandit, vulture and pytest;
gitleaks must be installed separately). The suite never uses the network. It runs
repository code only for the synthetic pytest scenarios. Exit status: 0 if nothing
failed, 1 otherwise.

## Running the Claude Code suite (opt-in)

```bash
python acceptance/claude_code.py --archonix /tmp/arx/bin/archonix \
    --tools-path "$PWD/.venv/bin" --yes-send-fixtures-to-anthropic --out /tmp/claude-results
```

What it does:

- Builds a disposable Git project from `examples/python-service` with a **seeded rounding
  bug**, and installs the skill with `archonix install --scope project`.
- Runs four tasks with `claude -p`, each from a clean checkout. The options are:
  - `--setting-sources project`, so your personal settings are not used;
  - `--strict-mcp-config`, so no MCP servers are loaded;
  - no web tools and no subagents.
- Sends the synthetic fixture (already public here) to Anthropic and uses your account's
  quota. Never point it at private code.

| Task | Prompt (abridged) | Allowed tools | Expected |
|---|---|---|---|
| T1 understand | "Use Archonix to help me understand this repository… Do not modify any files." | Read/Glob/Grep, Skill, `archonix`, read-only `git`, `ls` | skill invoked; `repository-understanding.md` loaded; no file changes |
| T2 discover | "…discover the requirements for a VIP discount cap… Do not write code or modify files" | same | skill invoked; `discovery.md` loaded; no file changes |
| T3 bug fix | "apply_discount(Decimal('10.005'), 0) returns 10.00… fix it using the bug-investigation workflow. You may run its tests." | above plus Edit/Write; **not** `python -m pytest` | `bug-investigation.md` loaded; changes only in `app/` and `tests/`; tests run **through the CLI**; independent re-check passes |
| T4 release | "Use Archonix to assess whether this repository is ready to release… Do not modify any files." | read-only set | `release-readiness.md` loaded; no file changes; no report written to an invented location; answer reports **not ready** |

Scoring is automatic. The verdict comes from the transcript (with denied tool calls
excluded), the Git state, and an **independent CLI re-run of the tests** for T3. The
assistant's claims alone never decide it. PASS means every expectation held; PARTIAL
means the skill was invoked but an expectation failed. Summaries written to `--out` have
machine paths redacted. Whether the answers are *well reasoned* still needs a human to
read them.

## Manual procedure: OpenAI Codex and Cursor (not yet performed)

Neither has been tested. Codex was not installed in the test environment, and Cursor has
no headless agent to script. To test either one:

1. Build the T1 to T4 fixture yourself:
   1. Copy `examples/python-service` to an empty directory.
   2. In `app/pricing.py`, change `ROUND_HALF_UP` to `ROUND_DOWN`, then `git init` and
      commit.
   3. Install the skill with `archonix install --assistant codex --scope project
      --project-dir . --apply`. For Cursor, use `--assistant cursor`.
2. Restrict the assistant's command approvals to `archonix`, read-only `git` and file
   reading. Allow edits only for T3.
3. Paste each prompt from the table above into a **new** session, starting from a clean
   checkout (`git reset --hard && git clean -fdx -e .codex -e .cursor -e .agents`).
4. For each task, record:
   - whether the skill was used;
   - which `references/*.md` files were read;
   - the `archonix` commands run;
   - `git status --porcelain`;
   - for T3, the result of `archonix check run . --mode audit --allow-repo-code --checks
     pytest`, run yourself.
5. Score each task against the "Expected" column. Add the assistant version, the date and
   the results to `docs/acceptance/`, labelled **manual**.
