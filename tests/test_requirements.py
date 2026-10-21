from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from conftest import REPO_ROOT

from archonix.cli import main
from archonix.requirements import traceability, validate_ledger

EXAMPLE = REPO_ROOT / "examples" / "requirements" / "ledger.json"


def ledger() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text())


def req(rid: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "id": rid,
        "title": "t",
        "description": "d",
        "source": {"type": "user-confirmed"},
        "priority": "must",
        "acceptance_criteria": [{"id": f"AC-{rid[4:]}-1", "description": "x"}],
        "dependencies": [],
        "status": "approved",
        "verification": {"method": "automated-test"},
    }
    base.update(overrides)
    return base


def doc(*reqs: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "requirements-ledger",
        "schema_version": "0.1",
        "project": "p",
        "requirements": list(reqs),
    }


def test_example_ledger_is_valid() -> None:
    result = validate_ledger(ledger())
    assert result.ok, result.errors


def test_template_ledger_is_valid_after_substitution() -> None:
    text = (REPO_ROOT / "skills/archonix/templates/requirements.json").read_text()
    result = validate_ledger(json.loads(text.replace("{{project}}", "demo")))
    assert result.ok, result.errors


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda d: d["requirements"][0].update(id="req-1"), "does not match"),
        (lambda d: d["requirements"][0].update(priority="urgent"), "is not one of"),
        (
            lambda d: d["requirements"][0].pop("verification"),
            "'verification' is a required property",
        ),
        (lambda d: d.update(schema_version="9"), "'0.1' was expected"),
    ],
)
def test_schema_errors_are_reported(mutate: Any, message: str) -> None:
    d = ledger()
    mutate(d)
    result = validate_ledger(d)
    assert not result.ok
    assert any(message in e for e in result.errors), result.errors


def test_duplicate_ids_and_unknown_dependency() -> None:
    result = validate_ledger(doc(req("REQ-1"), req("REQ-1", dependencies=["REQ-9"])))
    assert "duplicate requirement id REQ-1" in result.errors
    assert any("unknown dependency REQ-9" in e for e in result.errors)


def test_dependency_cycle_detected() -> None:
    a = req("REQ-1", dependencies=["REQ-2"])
    b = req(
        "REQ-2", dependencies=["REQ-1"], acceptance_criteria=[{"id": "AC-2-1", "description": "x"}]
    )
    result = validate_ledger(doc(a, b))
    assert any(e.startswith("dependency cycle: REQ-1 -> REQ-2 -> REQ-1") for e in result.errors)


def test_approved_requires_acceptance_criteria() -> None:
    result = validate_ledger(doc(req("REQ-1", acceptance_criteria=[])))
    assert any("requires at least one acceptance criterion" in e for e in result.errors)
    proposed = validate_ledger(doc(req("REQ-1", acceptance_criteria=[], status="proposed")))
    assert proposed.ok


def test_critical_question_gate() -> None:
    q = {"id": "Q-1", "question": "Who can see invoices?", "critical": True}
    blocked = validate_ledger(doc(req("REQ-1", open_questions=[q])))
    assert any("critical question Q-1 is unresolved" in e for e in blocked.errors)
    accepted = validate_ledger(
        doc(req("REQ-1", open_questions=[{**q, "accepted_as_assumption": True}]))
    )
    assert accepted.ok
    as_proposed = validate_ledger(doc(req("REQ-1", status="proposed", open_questions=[q])))
    assert as_proposed.ok and as_proposed.warnings


def test_verified_requires_passing_evidence_per_criterion() -> None:
    no_evidence = validate_ledger(doc(req("REQ-1", status="verified")))
    assert any("no verification evidence" in e for e in no_evidence.errors)
    failing = req(
        "REQ-1",
        status="verified",
        verification={
            "method": "automated-test",
            "evidence": [{"acceptance_criterion": "AC-1-1", "reference": "t", "result": "fail"}],
        },
    )
    assert any("not all evidence passed" in e for e in validate_ledger(doc(failing)).errors)
    two = req(
        "REQ-1",
        status="verified",
        acceptance_criteria=[
            {"id": "AC-1-1", "description": "a"},
            {"id": "AC-1-2", "description": "b"},
        ],
        verification={
            "method": "automated-test",
            "evidence": [{"acceptance_criterion": "AC-1-1", "reference": "t", "result": "pass"}],
        },
    )
    assert any("criteria lack evidence: AC-1-2" in e for e in validate_ledger(doc(two)).errors)


def test_traceability_marks_missing_and_resolves_checks() -> None:
    report = {"executions": [{"check_id": "pytest", "status": "completed", "outcome": "clean"}]}
    rows = traceability(ledger(), [report])
    by_ac = {r["criterion"]: r for r in rows}
    assert by_ac["AC-001-1"]["result"] == "pass"
    assert "check:pytest -> completed/clean" in by_ac["AC-001-1"]["evidence"][0]
    assert by_ac["AC-002-1"]["result"] == "missing"
    rows_without_report = traceability(ledger(), [])
    assert "not present in supplied reports" in rows_without_report[0]["evidence"][0]


def test_cli_validate_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["requirements", "validate", str(EXAMPLE)]) == 0
    bad = copy.deepcopy(ledger())
    bad["requirements"][1]["dependencies"] = ["REQ-404"]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    assert main(["requirements", "validate", str(path)]) == 1
    assert "unknown dependency REQ-404" in capsys.readouterr().err
    path.write_text("{not json")
    assert main(["requirements", "validate", str(path)]) == 1


# --- Review issue 2: traceability reported "pass" for missing or failed evidence ------


def _ledger(*evidence: dict[str, Any]) -> dict[str, Any]:
    return doc(
        req(
            "REQ-1",
            status="verified",
            verification={"method": "automated-test", "evidence": list(evidence)},
        )
    )


def _ex(outcome: str, status: str = "completed") -> dict[str, Any]:
    return {"executions": [{"check_id": "pytest", "status": status, "outcome": outcome}]}


CHECK_PASS = {"acceptance_criterion": "AC-1-1", "reference": "check:pytest", "result": "pass"}


@pytest.mark.parametrize(
    "reports, expected",
    [
        ([], "unknown"),  # evidence not supplied
        ([_ex("tests-failed")], "fail"),  # ledger says pass, execution failed
        ([_ex("clean")], "pass"),
        ([_ex("findings")], "unknown"),  # needs human judgement
        ([_ex("tool-error")], "unknown"),
        ([_ex("not-run", status="blocked")], "unknown"),
    ],
)
def test_check_evidence_is_resolved_before_assigning_result(reports: list, expected: str) -> None:
    row = traceability(_ledger(CHECK_PASS), reports)[0]
    assert row["result"] == expected and row["basis"] == "verified", row


def test_recorded_fail_is_never_overridden_by_a_clean_check() -> None:
    failing = {**CHECK_PASS, "result": "fail"}
    row = traceability(_ledger(failing), [_ex("clean")])[0]
    assert row["result"] == "fail" and "ledger recorded fail" not in row["evidence"][0]


def test_recorded_assertions_are_labelled_and_mixed_basis() -> None:
    manual = {"acceptance_criterion": "AC-1-1", "reference": "QA sign-off", "result": "pass"}
    assert traceability(_ledger(manual), [])[0]["basis"] == "recorded"
    row = traceability(_ledger(manual, CHECK_PASS), [_ex("clean")])[0]
    assert (row["result"], row["basis"]) == ("pass", "mixed")
    row = traceability(_ledger(manual, CHECK_PASS), [])[0]
    assert row["result"] == "unknown"  # a recorded pass cannot cover missing evidence
