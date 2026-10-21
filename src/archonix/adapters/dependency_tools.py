"""Adapter for OSV-Scanner (dependency vulnerabilities across ecosystems)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..findings import make_finding
from ..policy import Requirements
from ..runner import RunResult
from .base import (
    STATUS_TESTED_REAL,
    Adapter,
    Context,
    ParseOutcome,
    load_json_output,
    relpath,
    unexpected_exit,
)

# Range types whose "fixed" events are package versions (GIT ranges hold commit SHAs).
_VERSION_RANGES = {"ECOSYSTEM", "SEMVER"}
_DB_SEVERITY = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MODERATE": "medium",
    "MEDIUM": "medium",
    "LOW": "low",
}
REPO_CONFIG_NAMES = ("osv-scanner.toml", ".osv-scanner.toml")


def _cvss_severity(score: object) -> str | None:
    """Map a CVSS base score (OSV ``max_severity``) to an Archonix severity."""
    try:
        value = float(str(score))
    except ValueError:
        return None
    if value >= 9.0:
        return "critical"
    if value >= 7.0:
        return "high"
    if value >= 4.0:
        return "medium"
    if value > 0:
        return "low"
    return "info"


def _exclude_args(excludes: list[str]) -> list[str]:
    args = []
    for pattern in excludes:
        # Plain names match a directory exactly; anything with glob syntax becomes g:<glob>.
        value = f"g:**/{pattern}" if any(c in pattern for c in "*?[") else pattern
        args += ["--x-exclude", value]
    return args


def _fixed_versions(vulns: list[dict[str, Any]], package: str) -> list[str]:
    fixed: list[str] = []
    for vuln in vulns:
        for affected in vuln.get("affected") or []:
            if (affected.get("package") or {}).get("name") != package:
                continue
            for rng in affected.get("ranges") or []:
                if rng.get("type") not in _VERSION_RANGES:
                    continue
                for event in rng.get("events") or []:
                    version = event.get("fixed")
                    if isinstance(version, str) and version not in fixed:
                        fixed.append(version)
    return fixed


class OsvScannerAdapter(Adapter):
    id = "osv-scanner"
    tool = "osv-scanner"
    executable = "osv-scanner"
    category = "dependency"
    description = (
        "OSV-Scanner over lockfiles and manifests (Python, npm, Go, Rust, Ruby, PHP, "
        "...) against the OSV database."
    )
    requires = Requirements(external_tool=True, network=True)
    status = STATUS_TESTED_REAL
    exit_codes = {
        0: "no vulnerabilities",
        1: "vulnerabilities found",
        127: "general error",
        128: "no package sources found",
    }
    notes = (
        "Reads lockfiles without installing or building anything; call analysis is "
        "disabled because it can run build scripts. Sends package names and versions "
        "(not source code) to osv.dev, and may resolve transitive dependencies of "
        "unpinned manifests through deps.dev. Respects .gitignore and the repository's "
        "osv-scanner.toml ignore list."
    )

    def applies(self, inventory: dict[str, Any], root: Path) -> tuple[bool, str]:
        sources = [
            ev.split(":", 1)[0]
            for d in inventory["detections"]
            if d["category"] == "package-manager"
            for ev in d["evidence"]
            if ev.endswith((": lockfile", ": requirements file"))
        ]
        if sources:
            return True, f"lockfiles or requirements files found ({', '.join(sorted(sources)[:3])})"
        return False, "no lockfiles or requirements files detected"

    def argv(self, ctx: Context) -> list[str]:
        return [
            "osv-scanner",
            "scan",
            "source",
            "--recursive",
            "--format",
            "json",
            "--no-call-analysis=all",
            "--verbosity",
            "error",
            *_exclude_args(ctx.excludes),
            *ctx.extra_args,
            ".",
        ]

    def interpret(self, result: RunResult, ctx: Context) -> ParseOutcome:
        if result.exit_code == 128:
            return ParseOutcome("tool-error", "exit code 128: no package sources found")
        if result.exit_code not in (0, 1):
            return unexpected_exit(result, self.exit_codes)
        data, err = load_json_output(result.stdout.text(), result.stdout.truncated)
        if err:
            return ParseOutcome("parse-error", err)
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            return ParseOutcome("parse-error", "expected an object with a 'results' array")
        findings = []
        skipped = 0
        for source in data["results"]:
            if not isinstance(source, dict):
                skipped += 1
                continue
            src = source.get("source") or {}
            path = relpath(str(src.get("path") or "unknown"), ctx.root)
            resolved = src.get("type") != "lockfile"  # versions inferred by osv-scanner
            for pkg in source.get("packages") or []:
                meta = pkg.get("package") or {}
                name, version = meta.get("name"), meta.get("version")
                vulns = {
                    v.get("id"): v for v in pkg.get("vulnerabilities") or [] if isinstance(v, dict)
                }
                groups = pkg.get("groups") or [
                    {"ids": [i], "aliases": [], "max_severity": ""} for i in vulns
                ]
                for group in groups:
                    ids = [i for i in group.get("ids") or [] if isinstance(i, str)]
                    if not name or not ids:
                        skipped += 1
                        continue
                    members = [vulns[i] for i in ids if i in vulns]
                    first = members[0] if members else {}
                    severity = _cvss_severity(group.get("max_severity"))
                    if severity is None:
                        db = str((first.get("database_specific") or {}).get("severity", ""))
                        severity = _DB_SEVERITY.get(db.upper(), "unknown")
                    aliases = sorted(set(group.get("aliases") or []) | set(ids))
                    cves = [a for a in aliases if a.startswith("CVE-")]
                    fixed = _fixed_versions(members, name)
                    refs = [
                        r["url"]
                        for r in first.get("references") or []
                        if isinstance(r, dict) and r.get("url")
                    ][:5]
                    summary = first.get("summary") or first.get("details") or ""
                    findings.append(
                        make_finding(
                            tool="osv-scanner",
                            check_id=self.id,
                            tool_version=ctx.tool_version,
                            category="dependency",
                            rule_id=ids[0],
                            title=f"{name} {version}: {ids[0]}"
                            + (f" ({', '.join(cves[:2])})" if cves else ""),
                            message=re.sub(r"\s+", " ", summary).strip()[:500] or None,
                            severity=severity,
                            confidence="medium" if resolved else "high",
                            original_severity=str(group.get("max_severity") or "") or None,
                            path=path,
                            symbol=f"{meta.get('ecosystem', '?')}:{name}@{version}",
                            evidence=f"aliases: {', '.join(aliases)}"
                            + (
                                "; version resolved by osv-scanner, not pinned in a lockfile"
                                if resolved
                                else ""
                            ),
                            remediation=(
                                f"upgrade {name} to a fixed version: {', '.join(fixed[:4])}"
                                if fixed
                                else "no fixed version listed; review the advisory"
                            ),
                            references=[*refs, f"https://osv.dev/vulnerability/{ids[0]}"],
                            discriminator=f"{path}|{name}|{version}|{ids[0]}",
                        )
                    )
        limitations = (
            [f"{skipped} unrecognised osv-scanner entries were ignored"] if skipped else []
        )
        configs = [n for n in REPO_CONFIG_NAMES if (ctx.root / n).is_file()]
        if configs:
            limitations.append(f"repository {configs[0]} may ignore vulnerabilities; review it")
        if findings:
            return ParseOutcome(
                "findings",
                f"{len(findings)} vulnerable package advisory group(s)",
                findings,
                limitations=limitations,
            )
        if result.exit_code == 1:
            return ParseOutcome(
                "parse-error", "exit code 1 but no vulnerabilities parsed", limitations=limitations
            )
        return ParseOutcome("clean", "no known vulnerabilities reported", limitations=limitations)
