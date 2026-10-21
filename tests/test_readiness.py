from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from conftest import REPO_ROOT

from archonix.cli import main
from archonix.errors import ArchonixError
from archonix.readiness import assess, load_policy
from archonix.schemas import validate

POLICY = {
    "name": "t",
    "rules": {
        "required_checks": ["pytest"],
        "max_severity": "medium",
        "require_tests": True,
        "require_revision": True,
        "require_clean_worktree": True,
    },
}


def report(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "repository": {"vcs": "git", "revision": "c" * 40, "branch": "main", "dirty": False},
        "executions": [
            {
                "id": "exec-pytest",
                "check_id": "pytest",
                "status": "completed",
                "outcome": "clean",
                "outcome_detail": "2 passed",
                "test_totals": {"total": 2, "passed": 2, "failed": 0, "skipped": 0, "errored": 0},
            }
        ],
        "findings": [],
    }
    base.update(overrides)
    return base


def verdict(
    rep: dict[str, Any] | None,
    policy: dict[str, Any] = POLICY,
    ledger: tuple[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    out = assess(policy, "test", [("r.json", rep)] if rep else [], ledger)
    validate(out, "release-readiness")
    return out


def test_all_evidence_present_is_ready() -> None:
    assert verdict(report())["verdict"] == "ready"


def test_missing_evidence_is_incomplete_never_ready() -> None:
    assert verdict(None)["verdict"] == "incomplete"
    no_pytest = report(executions=[])
    assert verdict(no_pytest)["verdict"] == "incomplete"
    unknown_rev = report(
        repository={"vcs": "none", "revision": None, "branch": None, "dirty": None}
    )
    assert verdict(unknown_rev)["verdict"] == "incomplete"


def test_blocked_required_check_is_unknown() -> None:
    blocked = report(
        executions=[
            {
                "id": "e",
                "check_id": "pytest",
                "status": "blocked",
                "outcome": "not-run",
                "outcome_detail": "not permitted",
                "test_totals": None,
            }
        ]
    )
    out = verdict(blocked)
    assert out["verdict"] == "incomplete"
    assert out["rules"][0]["result"] == "unknown"


def test_failures_are_not_ready() -> None:
    finding = {"id": "ARX-1", "severity": "high", "verification_status": "scanner-reported"}
    assert verdict(report(findings=[finding]))["verdict"] == "not-ready"
    fp = {**finding, "verification_status": "false-positive"}
    assert verdict(report(findings=[fp]))["verdict"] == "ready"
    failing = copy.deepcopy(report())
    failing["executions"][0].update(
        outcome="tests-failed",
        test_totals={"total": 2, "passed": 1, "failed": 1, "skipped": 0, "errored": 0},
    )
    assert verdict(failing)["verdict"] == "not-ready"
    assert (
        verdict(
            report(repository={"vcs": "git", "revision": "c" * 40, "branch": "m", "dirty": True})
        )["verdict"]
        == "not-ready"
    )


def test_zero_tests_and_unknown_severity_are_unknown() -> None:
    zero = copy.deepcopy(report())
    zero["executions"][0]["test_totals"]["total"] = 0
    assert verdict(zero)["verdict"] == "incomplete"
    unk = {"id": "ARX-2", "severity": "unknown", "verification_status": "scanner-reported"}
    assert verdict(report(findings=[unk]))["verdict"] == "incomplete"


def test_must_requirements_rule() -> None:
    ledger = json.loads((REPO_ROOT / "examples/requirements/ledger.json").read_text())
    policy = {"name": "t", "rules": {"require_must_requirements_verified": True}}
    assert verdict(report(), policy)["verdict"] == "incomplete"  # no ledger supplied
    assert verdict(report(), policy, ("l.json", ledger))["verdict"] == "not-ready"  # REQ-002


def test_empty_policy_is_incomplete() -> None:
    assert verdict(report(), {"name": "empty", "rules": {}})["verdict"] == "incomplete"


def test_policy_loading(tmp_path: Path) -> None:
    p = tmp_path / "p.toml"
    p.write_text('[rules]\nmax_severity = "urgent"\n')
    with pytest.raises(ArchonixError):
        load_policy(p)
    p.write_text("[rules]\nrequire_magic = true\n")
    with pytest.raises(ArchonixError, match="unknown readiness rule"):
        load_policy(p)
    policy, source = load_policy(REPO_ROOT / "examples/readiness-policy.toml")
    assert policy["name"] == "example-release-policy" and source.endswith("readiness-policy.toml")


def test_cli_exit_codes() -> None:
    example = REPO_ROOT / "examples/reports/report.json"
    ledger = REPO_ROOT / "examples/requirements/ledger.json"
    policy = REPO_ROOT / "examples/readiness-policy.toml"
    assert (
        main(
            [
                "readiness",
                "assess",
                "--report",
                str(example),
                "--ledger",
                str(ledger),
                "--policy",
                str(policy),
                "--format",
                "json",
            ]
        )
        == 1
    )
    assert main(["readiness", "assess"]) == 4


# --- Review issue 3: all-skipped tests satisfied require_tests ------------------------

TESTS_ONLY = {"name": "t", "rules": {"require_tests": True}}


def _tests(
    totals: dict[str, int | None], status: str = "completed", outcome: str = "clean"
) -> dict[str, Any]:
    return report(
        executions=[
            {
                "id": "e",
                "check_id": "pytest",
                "status": status,
                "outcome": outcome,
                "outcome_detail": "",
                "test_totals": totals,
            }
        ]
    )


@pytest.mark.parametrize(
    "totals, status, outcome, expected, why",
    [
        (
            {"total": 3, "passed": 0, "failed": 0, "skipped": 3, "errored": 0},
            "completed",
            "clean",
            "unknown",
            "no test actually executed",
        ),
        (
            {"total": 3, "passed": 1, "failed": 0, "skipped": 1, "errored": 0},
            "completed",
            "clean",
            "unknown",
            "inconsistent",
        ),
        (
            {"total": 3, "passed": None, "failed": 0, "skipped": 0, "errored": 0},
            "completed",
            "clean",
            "unknown",
            "counts unknown",
        ),
        (
            {"total": 2, "passed": 2, "failed": 0, "skipped": 0, "errored": 0},
            "timeout",
            "tool-error",
            "unknown",
            "did not complete",
        ),
        (
            {"total": 2, "passed": 2, "failed": 0, "skipped": 0, "errored": 0},
            "completed",
            "parse-error",
            "unknown",
            "did not complete",
        ),
        (
            {"total": 4, "passed": 1, "failed": 0, "skipped": 2, "errored": 1},
            "completed",
            "tests-failed",
            "fail",
            "failing or erroring",
        ),
        (
            {"total": 4, "passed": 2, "failed": 0, "skipped": 2, "errored": 0},
            "completed",
            "clean",
            "pass",
            "2 executed",
        ),
    ],
)
def test_tests_rule_requires_executed_completed_consistent_runs(
    totals: dict, status: str, outcome: str, expected: str, why: str
) -> None:
    rule = verdict(_tests(totals, status, outcome), TESTS_ONLY)["rules"][0]
    assert (rule["result"], why in rule["detail"]) == (expected, True), rule


def test_reported_all_skipped_case_is_no_longer_ready() -> None:
    policy = {"name": "t", "rules": {"required_checks": ["pytest"], "require_tests": True}}
    all_skipped = _tests({"total": 3, "passed": 0, "failed": 0, "skipped": 3, "errored": 0})
    assert verdict(all_skipped, policy)["verdict"] == "incomplete"
