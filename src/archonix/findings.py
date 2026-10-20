"""Finding construction, stable identifiers and conservative deduplication."""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

SEVERITIES = ("critical", "high", "medium", "low", "info", "unknown")


def stable_id(
    tool: str,
    rule_id: str | None,
    path: str | None,
    line: int | None,
    column: int | None,
    discriminator: str = "",
) -> str:
    """Deterministic ID from the identity of a finding, not from its message text."""
    raw = "\x1f".join(
        [tool, rule_id or "", path or "", str(line or ""), str(column or ""), discriminator]
    )
    return "ARX-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def make_finding(
    *,
    tool: str,
    check_id: str,
    category: str,
    title: str,
    severity: str,
    confidence: str,
    rule_id: str | None = None,
    message: str | None = None,
    path: str | None = None,
    line: int | None = None,
    end_line: int | None = None,
    column: int | None = None,
    symbol: str | None = None,
    original_severity: str | None = None,
    original_confidence: str | None = None,
    tool_version: str | None = None,
    evidence: str | None = None,
    remediation: str | None = None,
    references: list[str] | None = None,
    discriminator: str = "",
) -> dict[str, Any]:
    return {
        "id": stable_id(tool, rule_id, path, line, column, discriminator),
        "category": category,
        "title": title,
        "message": message,
        "severity": severity if severity in SEVERITIES else "unknown",
        "confidence": confidence,
        "source": {
            "kind": "scanner",
            "tool": tool,
            "tool_version": tool_version,
            "check_id": check_id,
            "rule_id": rule_id,
            "original_severity": original_severity,
            "original_confidence": original_confidence,
        },
        "location": None
        if path is None
        else {
            "path": path,
            "start_line": line,
            "end_line": end_line,
            "start_column": column,
            "symbol": symbol,
        },
        "evidence": evidence,
        "exploitability": None,
        "remediation": remediation,
        "verification_status": "scanner-reported",
        "references": references or [],
        "related_ids": [],
        "occurrences": 1,
    }


def _location_key(f: dict[str, Any]) -> tuple[str, int] | None:
    loc = f.get("location")
    if not loc or loc.get("start_line") is None:
        return None
    return (loc["path"], loc["start_line"])


def deduplicate(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge only exact duplicates (same stable ID: same tool, rule and location).

    Findings from different tools or rules at the same location are *not* merged; they
    are cross-linked through ``related_ids`` so a reviewer can judge whether they overlap.
    Similar messages at different locations are never merged.
    """
    merged: dict[str, dict[str, Any]] = {}
    for f in findings:
        existing = merged.get(f["id"])
        if existing is None:
            merged[f["id"]] = {**f, "related_ids": list(f.get("related_ids", []))}
        else:
            existing["occurrences"] = existing.get("occurrences", 1) + f.get("occurrences", 1)
    by_location: dict[tuple[str, int], list[str]] = {}
    for f in merged.values():
        key = _location_key(f)
        if key is not None:
            by_location.setdefault(key, []).append(f["id"])
    for ids in by_location.values():
        if len(ids) > 1:
            for fid in ids:
                rel = merged[fid]["related_ids"]
                rel.extend(i for i in ids if i != fid and i not in rel)
    order = {s: i for i, s in enumerate(SEVERITIES)}
    return sorted(
        merged.values(),
        key=lambda f: (
            order.get(f["severity"], 99),
            (f.get("location") or {}).get("path") or "",
            (f.get("location") or {}).get("start_line") or 0,
            f["id"],
        ),
    )


def severity_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(f["severity"] for f in findings)
    return {s: counts[s] for s in SEVERITIES if counts[s]}
