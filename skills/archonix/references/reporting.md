# Evidence and completion reporting

## Status vocabulary

Use these labels for every claim:

- **Verified** — a command or test ran in this session; cite the command, working
  directory, exit code and the relevant counts or output.
- **Inferred** — derived from reading code/config, not executed. Say what it rests on.
- **Skipped** — not done; give the reason (not permitted, tool missing, out of scope).
- **Unsupported** — Archonix or the environment cannot do it.

Unknown counts stay unknown. "0 findings" from a check that did not run is wrong; say
"not run". A clean scan is never proof of security; passing tests are never proof of
correctness; coverage shows gaps, not correctness.

## Execution records

For every command that matters, record: command, working directory, tool version, start
time (UTC), duration, exit status and its meaning for that tool, test totals
(passed/failed/skipped/errored) when available, artifacts, and parsing limitations.
`archonix check run` produces these as `executions[]` in the workflow report.

## Findings

Every finding has a stable ID, category, source (tool and original rule ID, or
`reviewer`/`agent`), severity and confidence as separate fields, location, evidence,
exploitability or impact, remediation and verification status (`scanner-reported`,
`verified`, `hypothesis`, `false-positive`, `fixed`). Keep scanner output, independently
verified findings and hypotheses distinct. Deduplicate only exact duplicates; link
overlaps instead of merging them.

## Completion report structure

```text
## Summary            — outcome in two or three sentences
## Changes            — files/modules touched and why (requirement IDs)
## Verification       — commands run, exit codes, counts; label each Verified/Skipped
## Requirement coverage — REQ/AC IDs → evidence (or "not verified")
## Findings           — by severity, with verification status
## Not verified       — what was not checked and why
## Risks and limitations
## Next steps
```

Include repository revision and whether the working tree had uncommitted changes when
the evidence was gathered. Never fabricate a revision for a non-Git directory.
