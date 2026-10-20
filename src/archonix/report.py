"""Assemble workflow reports and render JSON documents as Markdown."""

from __future__ import annotations

import hashlib
from typing import Any

from . import SCHEMA_VERSION, __version__
from .config import Settings
from .findings import deduplicate, severity_counts
from .inventory import summary as inventory_summary
from .timeutil import utc_now

BASE_LIMITATIONS = [
    "Automated checks cover only what the selected tools and rules detect; absence of "
    "findings is not proof of correctness or security.",
    "Scanner-reported findings are unverified until reviewed (see verification_status).",
]


def build_workflow_report(
    *,
    workflow: str,
    root: str,
    settings: Settings,
    inventory: dict[str, Any] | None,
    repository: dict[str, Any],
    executions: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    skipped: list[dict[str, str]],
    requested_checks: list[str] | None,
    example: bool = False,
) -> dict[str, Any]:
    findings = deduplicate(findings)
    generated = utc_now()
    ran = [e for e in executions if e["status"] not in {"blocked", "skipped"}]
    failed = [
        e
        for e in ran
        if e["outcome"] in {"tool-error", "parse-error", "tests-failed"}
        or e["status"] != "completed"
    ]
    limitations = list(BASE_LIMITATIONS)
    for e in executions:
        limitations += [f"{e['check_id']}: {x}" for x in e.get("parse_limitations", [])]
        if e["outcome"] == "parse-error":
            limitations.append(
                f"{e['check_id']}: output could not be parsed "
                f"({e['outcome_detail']}); its findings are unknown"
            )
        for stream in ("stdout", "stderr"):
            s = e.get(stream)
            if s and s["truncated"] and s["bytes_total"] > settings.max_output_bytes:
                limitations.append(f"{e['check_id']}: {stream} exceeded the capture limit")
    if settings.ignored:
        limitations += [f"ignored setting: {x}" for x in settings.ignored]
    if repository.get("dirty") is None and repository["vcs"] == "git":
        limitations.append(
            "working-tree status unknown; results may not match the recorded revision"
        )

    next_actions: list[str] = []
    if findings:
        next_actions.append(
            "Triage findings: confirm or mark false-positive, then remediate "
            "verified issues starting with the highest severity."
        )
    if failed:
        next_actions.append(
            "Investigate checks that failed or could not be parsed: "
            + ", ".join(e["check_id"] for e in failed)
        )
    blocked = [e for e in executions if e["status"] == "blocked"]
    if blocked:
        next_actions.append(
            "Checks blocked by policy ("
            + ", ".join(e["check_id"] for e in blocked)
            + ") can be enabled explicitly if they are authorized."
        )
    if not ran:
        next_actions.append("No checks ran; install a supported tool or adjust permissions.")

    digest = hashlib.sha256(f"{workflow}{root}{generated}".encode()).hexdigest()[:12]
    return {
        "kind": "workflow-report",
        "schema_version": SCHEMA_VERSION,
        "example": example,
        "report_id": f"RPT-{digest}",
        "workflow": workflow,
        "generated_at": generated,
        "generator": {"name": "archonix", "version": __version__},
        "scope": {"root": root, "mode": settings.mode, "requested_checks": requested_checks},
        "repository": repository,
        "policy": {
            "permissions": settings.permissions.as_dict(),
            "sources": {
                k: v for k, v in sorted(settings.sources.items()) if k.startswith("permissions.")
            },
            "ignored_settings": settings.ignored,
        },
        "inventory_summary": inventory_summary(inventory) if inventory else None,
        "executions": executions,
        "findings": findings,
        "skipped": skipped,
        "limitations": limitations,
        "next_actions": next_actions,
        "summary": {
            "checks_planned": len(executions),
            "checks_run": len(ran),
            "clean": sum(1 for e in ran if e["outcome"] == "clean"),
            "with_findings": sum(1 for e in ran if e["outcome"] == "findings"),
            "failed": len(failed),
            "not_run": len(executions) - len(ran),
            "findings_by_severity": severity_counts(findings),
        },
    }


def _md_escape(text: str | None) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def _tri(value: bool | None) -> str:
    return "unknown" if value is None else ("yes" if value else "no")


def _count(value: int | None) -> str:
    return "unknown" if value is None else str(value)


def render_workflow_report(r: dict[str, Any]) -> str:
    repo = r["repository"]
    s = r["summary"]
    out = []
    if r.get("example"):
        out += ["> **EXAMPLE REPORT** — generated from a synthetic fixture for documentation.", ""]
    out += [
        f"# Archonix {r['workflow']} report",
        "",
        f"- Report: `{r['report_id']}` (schema {r['schema_version']}, archonix "
        f"{r['generator']['version']})",
        f"- Generated (UTC): {r['generated_at']}",
        f"- Scope: `{r['scope']['root']}`; mode: {r['scope']['mode']}; requested checks: "
        f"{', '.join(r['scope']['requested_checks'] or ['all applicable'])}",
        f"- Repository: {repo['vcs']}; revision: {repo['revision'] or 'none recorded'}; "
        f"branch: {repo['branch'] or 'n/a'}; uncommitted changes: {_tri(repo['dirty'])}",
        "",
        "## Summary",
        "",
        f"- Checks: {s['checks_run']} run of {s['checks_planned']} considered — "
        f"{s['clean']} clean, {s['with_findings']} with findings, "
        f"{s['failed']} failed/unparsed, {s['not_run']} not run",
        "- Findings by severity: "
        + (", ".join(f"{k} {v}" for k, v in s["findings_by_severity"].items()) or "none reported"),
        "",
        "## Checks",
        "",
        "| Check | Status | Outcome | Exit | Duration (s) | Tool version | Detail |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in r["executions"]:
        out.append(
            f"| {e['check_id']} | {e['status']} | {e['outcome']} | "
            f"{'—' if e['exit_code'] is None else e['exit_code']} | "
            f"{'—' if e['duration_seconds'] is None else e['duration_seconds']} | "
            f"{e['tool_version'] or 'unknown'} | {_md_escape(e['outcome_detail'])} |"
        )
    tests = [e for e in r["executions"] if e.get("test_totals")]
    if tests:
        out += [
            "",
            "## Test results",
            "",
            "| Check | Total | Passed | Failed | Skipped | Errored |",
            "|---|---|---|---|---|---|",
        ]
        for e in tests:
            t = e["test_totals"]
            out.append(
                f"| {e['check_id']} | {_count(t['total'])} | {_count(t['passed'])} | "
                f"{_count(t['failed'])} | {_count(t['skipped'])} | {_count(t['errored'])} |"
            )
    out += ["", "## Findings", ""]
    if not r["findings"]:
        out.append("No findings were reported by the checks that ran.")
    else:
        out += [
            "| ID | Severity | Confidence | Category | Location | Source rule | Title | Status |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for f in r["findings"]:
            loc = f.get("location") or {}
            where = (
                f"{loc.get('path', '')}:{loc.get('start_line') or ''}".rstrip(":") if loc else "—"
            )
            src = f["source"]
            out.append(
                f"| `{f['id']}` | {f['severity']} | {f['confidence']} | {f['category']} | "
                f"`{_md_escape(where)}` | {src.get('tool')}:{src.get('rule_id')} | "
                f"{_md_escape(f['title'])[:160]} | {f['verification_status']} |"
            )
    out += ["", "## Commands executed", ""]
    ran = [e for e in r["executions"] if e["status"] not in {"blocked", "skipped"}]
    for e in ran:
        out.append(f"- `{' '.join(e['argv'])}` (cwd `{e['cwd']}`, started {e['started_at']})")
    if not ran:
        out.append("- none")
    if r["skipped"]:
        out += ["", "## Not run", ""] + [
            f"- **{x['check_id']}**: {x['reason']}" for x in r["skipped"]
        ]
    perms = r["policy"]["permissions"]
    out += [
        "",
        "## Effective permissions",
        "",
        ", ".join(f"{k}={'on' if v else 'off'}" for k, v in perms.items()),
    ]
    out += ["", "## Limitations", ""] + [f"- {x}" for x in r["limitations"] + repo.get("notes", [])]
    if r["next_actions"]:
        out += ["", "## Recommended next actions", ""] + [f"- {x}" for x in r["next_actions"]]
    return "\n".join(out) + "\n"


def render_readiness(r: dict[str, Any]) -> str:
    out = []
    if r.get("example"):
        out += ["> **EXAMPLE ASSESSMENT** — synthetic inputs, for documentation.", ""]
    out += [
        f"# Release readiness: **{r['verdict'].upper()}**",
        "",
        f"- Policy: {r['policy']['name']} ({r['policy']['source']})",
        f"- Generated (UTC): {r['generated_at']}",
        f"- Reports: {', '.join(r['inputs']['reports']) or 'none'}",
        f"- Requirements ledger: {r['inputs']['ledger'] or 'none'}",
        "",
        "| Rule | Result | Detail |",
        "|---|---|---|",
    ]
    for rule in r["rules"]:
        out.append(f"| {rule['id']} | {rule['result']} | {_md_escape(rule['detail'])} |")
    out += ["", "## Limitations", ""] + [f"- {x}" for x in r["limitations"]]
    return "\n".join(out) + "\n"


def render_performance(r: dict[str, Any]) -> str:
    m = r["methodology"]
    out = []
    if r.get("example"):
        out += ["> **EXAMPLE REPORT** — synthetic target, for documentation.", ""]
    out += [
        "# API smoke measurement",
        "",
        f"- Target: {r['target']['base_url']} (loopback: {r['target']['loopback']})",
        f"- Revision: {r.get('revision') or 'not recorded'}; environment: "
        f"{r.get('environment') or 'not recorded'}",
        f"- Method: {m['type']}; {m['requests_per_endpoint']} requests/endpoint, concurrency "
        f"{m['concurrency']}, warm-up {m['warmup_requests']}, timeout {m['timeout_seconds']}s",
        f"- Percentiles: {m['percentile_method']}; {m['reliability_rule']}",
        "",
        "| Endpoint | Samples | Errors | Timeouts | Status codes | p50 ms | p95 ms | p99 ms | "
        "RPS | Threshold |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    def pct(p: dict[str, Any]) -> str:
        if p["value"] is None:
            return "—"
        return f"{p['value']:.1f}" + ("" if p["reliable"] else " (insufficient samples)")

    for e in r["endpoints"]:
        lat = e["latency_ms"]
        codes = ", ".join(f"{k}x{v}" for k, v in sorted(e["status_codes"].items()))
        rps = "—" if e.get("throughput_rps") is None else f"{e['throughput_rps']:.1f}"
        out.append(
            f"| {e['method']} {e['path']} | {e['samples']} | {e['errors']} | {e['timeouts']} "
            f"| {codes or '—'} | {pct(lat['p50'])} | {pct(lat['p95'])} | {pct(lat['p99'])} "
            f"| {rps} | {e['threshold']['result']} |"
        )
    out += ["", "## Limitations", ""] + [f"- {x}" for x in r["limitations"]]
    return "\n".join(out) + "\n"


def render_any(document: dict[str, Any]) -> str:
    from .inventory import render_markdown as render_inventory
    from .requirements import render_ledger

    kind = document.get("kind")
    renderers = {
        "workflow-report": render_workflow_report,
        "release-readiness": render_readiness,
        "performance-report": render_performance,
        "inventory": render_inventory,
        "requirements-ledger": render_ledger,
    }
    if kind not in renderers:
        raise ValueError(f"no Markdown renderer for kind {kind!r}")
    return renderers[kind](document)
