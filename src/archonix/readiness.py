"""Policy-driven release readiness assessment.

Every rule evaluates to pass, fail or unknown. Any fail -> ``not-ready``; otherwise any
unknown -> ``incomplete``; only when every configured rule passes -> ``ready``. Missing
evidence is always unknown, never pass.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .errors import ArchonixError
from .findings import SEVERITIES
from .timeutil import utc_now

DEFAULT_POLICY: dict[str, Any] = {
    "name": "archonix-default",
    "rules": {
        "required_checks": [],
        "max_severity": "medium",
        "require_tests": True,
        "require_revision": True,
        "require_clean_worktree": True,
        "require_must_requirements_verified": True,
        "allow_unparsed_checks": False,
    },
}
KNOWN_RULES = set(DEFAULT_POLICY["rules"])
OPEN_STATUSES = {"scanner-reported", "verified", "hypothesis"}


def load_policy(path: Path | None) -> tuple[dict[str, Any], str]:
    if path is None:
        return DEFAULT_POLICY, "built-in default"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ArchonixError(f"cannot load readiness policy {path}: {exc}") from exc
    rules = data.get("rules", {})
    unknown = set(rules) - KNOWN_RULES
    if unknown:
        raise ArchonixError(f"unknown readiness rule(s) in {path}: {', '.join(sorted(unknown))}")
    max_sev = rules.get("max_severity")
    if max_sev is not None and max_sev not in SEVERITIES:
        raise ArchonixError(f"max_severity must be one of {', '.join(SEVERITIES)}")
    # Rules absent from a custom policy are disabled, not defaulted: the policy file is
    # the full statement of what this project requires.
    return {"name": data.get("name", path.stem), "rules": rules}, str(path)


def _rule(
    rid: str, desc: str, result: str, detail: str, evidence: list[str] | None = None
) -> dict[str, Any]:
    return {
        "id": rid,
        "description": desc,
        "result": result,
        "detail": detail,
        "evidence": evidence or [],
    }


def assess(
    policy: dict[str, Any],
    policy_source: str,
    reports: list[tuple[str, dict[str, Any]]],
    ledger: tuple[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    rules_cfg = policy["rules"]
    rules: list[dict[str, Any]] = []
    executions: dict[str, dict[str, Any]] = {}
    findings: list[dict[str, Any]] = []
    for _, rep in reports:
        for e in rep.get("executions", []):
            executions[e["check_id"]] = e
        findings += rep.get("findings", [])
    names = [n for n, _ in reports]

    for check_id in rules_cfg.get("required_checks", []):
        e = executions.get(check_id)
        desc = f"required check '{check_id}' ran and completed"
        if e is None:
            rules.append(
                _rule(
                    f"check:{check_id}",
                    desc,
                    "unknown",
                    "no execution record in the supplied reports",
                )
            )
        elif e["status"] in {"blocked", "skipped", "missing-tool"}:
            rules.append(
                _rule(f"check:{check_id}", desc, "unknown", f"not run: {e['outcome_detail']}")
            )
        elif e["outcome"] == "tests-failed":
            rules.append(
                _rule(f"check:{check_id}", desc, "fail", e["outcome_detail"] or "tests failed")
            )
        elif e["outcome"] in {"tool-error", "parse-error"} or e["status"] != "completed":
            rules.append(
                _rule(
                    f"check:{check_id}",
                    desc,
                    "unknown",
                    f"{e['status']}/{e['outcome']}: {e['outcome_detail']}",
                )
            )
        else:
            rules.append(
                _rule(
                    f"check:{check_id}",
                    desc,
                    "pass",
                    f"{e['outcome']} ({e['outcome_detail']})",
                    [f"exec {e['id']}"],
                )
            )

    max_sev = rules_cfg.get("max_severity")
    if max_sev:
        limit = SEVERITIES.index(max_sev)
        blocking = [
            f
            for f in findings
            if f["verification_status"] in OPEN_STATUSES
            and f["severity"] != "unknown"
            and SEVERITIES.index(f["severity"]) < limit
        ]
        unknown_sev = [
            f
            for f in findings
            if f["verification_status"] in OPEN_STATUSES and f["severity"] == "unknown"
        ]
        desc = f"no open findings more severe than '{max_sev}'"
        if not reports:
            rules.append(_rule("max-severity", desc, "unknown", "no reports supplied"))
        elif blocking:
            rules.append(
                _rule(
                    "max-severity",
                    desc,
                    "fail",
                    f"{len(blocking)} open finding(s) above '{max_sev}'",
                    [f["id"] for f in blocking[:20]],
                )
            )
        elif unknown_sev:
            rules.append(
                _rule(
                    "max-severity",
                    desc,
                    "unknown",
                    f"{len(unknown_sev)} finding(s) have unknown severity",
                )
            )
        else:
            rules.append(
                _rule(
                    "max-severity",
                    desc,
                    "pass",
                    f"{len(findings)} finding(s) reviewed against the threshold",
                )
            )

    if not rules_cfg.get("allow_unparsed_checks", True):
        bad = [e for e in executions.values() if e["outcome"] in {"parse-error", "tool-error"}]
        rules.append(
            _rule(
                "no-unparsed-checks",
                "every executed check produced interpretable output",
                "unknown" if bad else ("pass" if executions else "unknown"),
                ", ".join(f"{e['check_id']}: {e['outcome_detail']}" for e in bad)
                or ("all executed checks parsed" if executions else "no executions"),
            )
        )

    if rules_cfg.get("require_tests"):
        test_runs = [e for e in executions.values() if e.get("test_totals")]
        desc = "automated tests ran, at least one test executed, none failed"
        if not test_runs:
            rules.append(_rule("tests", desc, "unknown", "no test results in the supplied reports"))
        else:
            totals = [e["test_totals"] for e in test_runs]
            if any((t["failed"] or 0) > 0 or (t["errored"] or 0) > 0 for t in totals):
                rules.append(_rule("tests", desc, "fail", "failing or erroring tests reported"))
            elif any(t["total"] is None for t in totals):
                rules.append(_rule("tests", desc, "unknown", "test totals unknown"))
            elif sum(t["total"] for t in totals) == 0:
                rules.append(_rule("tests", desc, "unknown", "zero tests executed"))
            else:
                rules.append(
                    _rule(
                        "tests",
                        desc,
                        "pass",
                        f"{sum(t['total'] for t in totals)} tests",
                        [e["id"] for e in test_runs],
                    )
                )

    revisions = {rep["repository"].get("revision") for _, rep in reports}
    if rules_cfg.get("require_revision"):
        desc = "all reports were produced from the same recorded revision"
        if not reports or None in revisions:
            rules.append(
                _rule("revision", desc, "unknown", "revision not recorded in every report")
            )
        elif len(revisions) > 1:
            rules.append(
                _rule(
                    "revision",
                    desc,
                    "fail",
                    f"reports cover different revisions: "
                    f"{', '.join(sorted(r for r in revisions if r))}",
                )
            )
        else:
            rules.append(_rule("revision", desc, "pass", revisions.pop() or ""))

    if rules_cfg.get("require_clean_worktree"):
        dirty = [rep["repository"].get("dirty") for _, rep in reports]
        desc = "reports were produced from a clean working tree"
        if not reports or None in dirty:
            rules.append(_rule("clean-worktree", desc, "unknown", "working-tree status unknown"))
        elif any(dirty):
            rules.append(_rule("clean-worktree", desc, "fail", "uncommitted changes were present"))
        else:
            rules.append(_rule("clean-worktree", desc, "pass", "no uncommitted changes"))

    if rules_cfg.get("require_must_requirements_verified"):
        desc = "every 'must' requirement is verified"
        if ledger is None:
            rules.append(
                _rule("must-requirements", desc, "unknown", "no requirements ledger supplied")
            )
        else:
            musts = [
                r
                for r in ledger[1]["requirements"]
                if r["priority"] == "must" and r["status"] not in {"deferred", "rejected"}
            ]
            pending = [r["id"] for r in musts if r["status"] != "verified"]
            if not musts:
                rules.append(
                    _rule("must-requirements", desc, "unknown", "ledger has no 'must' requirements")
                )
            elif pending:
                rules.append(
                    _rule("must-requirements", desc, "fail", f"not verified: {', '.join(pending)}")
                )
            else:
                rules.append(_rule("must-requirements", desc, "pass", f"{len(musts)} verified"))

    results = {r["result"] for r in rules}
    verdict = (
        "not-ready"
        if "fail" in results
        else ("incomplete" if "unknown" in results or not rules else "ready")
    )
    limitations = [
        "The verdict reflects only the configured policy and the supplied evidence; it is not a "
        "guarantee of security, correctness or production fitness.",
    ]
    if not rules:
        limitations.append(
            "The policy defines no rules; the assessment is incomplete by definition."
        )
    return {
        "kind": "release-readiness",
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "policy": {"name": policy["name"], "source": policy_source},
        "verdict": verdict,
        "rules": rules,
        "inputs": {"reports": names, "ledger": ledger[0] if ledger else None},
        "limitations": limitations,
    }
