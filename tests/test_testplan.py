"""`archonix tests scaffold` and traceability from individual test results."""

from __future__ import annotations

import ast
import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES, PY_REPO, REPO_ROOT

from archonix.cli import main
from archonix.errors import ArchonixError, PolicyError
from archonix.requirements import orphan_tests, traceability
from archonix.testcases import ac_ids, decode_ac, encode_ac, matches_reference, parse_junit_cases
from archonix.testplan import scaffold

LEDGER = json.loads((REPO_ROOT / "examples" / "requirements" / "ledger.json").read_text())
OUT = FIXTURES / "tool-output"
posix_only = pytest.mark.skipif(os.name != "posix", reason="symlinks")


@pytest.fixture
def project(make_repo: Callable[..., Path]) -> Path:
    return make_repo({**PY_REPO, "docs/requirements.json": json.dumps(LEDGER)})


# ------------------------------------------------------------- naming convention


@pytest.mark.parametrize("ac", ["AC-001-1", "AC-LOGIN-2", "AC-7", "AC-A1-B2-C3"])
def test_encoding_round_trips(ac: str) -> None:
    assert decode_ac(encode_ac(ac)) == ac
    assert ac_ids(f"test_{encode_ac(ac)}__anything[param-1]") == [ac]


def test_ids_found_in_names_and_ignored_otherwise() -> None:
    assert ac_ids("REQ-1 > AC-001-1: does it") == ["AC-001-1"]
    assert ac_ids("test_plain_case", "tests.test_module") == []
    assert ac_ids("test_ac_001_1__x", "AC-002-1 suite") == ["AC-001-1", "AC-002-1"]


def test_explicit_references_match_pytest_node_ids() -> None:
    case = {"name": "test_rejects", "classname": "tests.test_pricing", "file": None}
    assert matches_reference("tests/test_pricing.py::test_rejects", case)
    assert matches_reference("tests.test_pricing::test_rejects", case)
    assert matches_reference("test_rejects", case)
    assert not matches_reference("tests/other.py::test_rejects", case)


# ------------------------------------------------------------- real JUnit formats


def test_vitest_and_jest_junit_results() -> None:
    """Recorded from vitest 5.0.5 and jest 30.5.2 + jest-junit 17.0.0."""
    for name in ("vitest-junit.xml", "jest-junit.xml"):
        cases, truncated = parse_junit_cases(OUT / name)
        assert not truncated
        assert [(c.ac_ids[0], c.result) for c in cases] == [
            ("AC-001-1", "passed"),
            ("AC-001-2", "failed"),
            ("AC-002-1", "skipped"),
            ("AC-LOGIN-1", "skipped"),
        ], name


def test_jest_todo_is_not_read_as_passed() -> None:
    """jest-junit lists test.todo with no marker but leaves it out of the suite count."""
    cases, _ = parse_junit_cases(OUT / "jest-junit.xml")
    todo = next(c for c in cases if "AC-002-1" in c.ac_ids)
    assert todo.result == "skipped"


@pytest.mark.parametrize("content", ["<html/>", "not xml", ""])
def test_non_junit_input_is_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "x.xml"
    path.write_text(content)
    with pytest.raises(ValueError):
        parse_junit_cases(path)


# ------------------------------------------------------------- scaffold


def test_scaffold_is_a_dry_run_and_needs_permission(project: Path) -> None:
    plan = scaffold(project, framework="pytest")
    assert [(a, p, n) for a, p, n in plan.files] == [
        ("create", "tests/acceptance/test_req_001.py", 2),
        ("create", "tests/acceptance/test_req_002.py", 1),
    ]
    assert any("REQ-003: no acceptance criteria" in n for n in plan.notes)
    assert not (project / "tests" / "acceptance").exists()
    with pytest.raises(PolicyError):
        scaffold(project, framework="pytest", apply=True)


def test_pytest_stubs_are_valid_named_and_pending(project: Path) -> None:
    scaffold(project, framework="pytest", apply=True, allow_source_writes=True)
    text = (project / "tests" / "acceptance" / "test_req_001.py").read_text()
    tree = ast.parse(text)  # valid Python
    names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert [ac_ids(n) for n in names] == [["AC-001-1"], ["AC-001-2"]]
    assert text.count('pytest.skip("not implemented: AC-') == 2


def test_failing_and_js_stubs(project: Path) -> None:
    scaffold(
        project,
        framework="pytest",
        out_dir="tests/tdd",
        failing=True,
        apply=True,
        allow_source_writes=True,
    )
    assert "pytest.fail(" in (project / "tests" / "tdd" / "test_req_001.py").read_text()
    scaffold(project, framework="vitest", typescript=True, apply=True, allow_source_writes=True)
    vt = (project / "tests" / "acceptance" / "req-001.test.ts").read_text()
    assert 'import { describe, test } from "vitest";' in vt
    assert 'test.skip("AC-001-1: ' in vt and "test.todo" not in vt.split("\n", 6)[-1]
    shutil.rmtree(project / "tests" / "acceptance")
    scaffold(project, framework="jest", failing=True, apply=True, allow_source_writes=True)
    jest = (project / "tests" / "acceptance" / "req-001.test.js").read_text()
    assert 'throw new Error("not implemented: AC-001-1");' in jest and "vitest" not in jest


def test_scaffold_never_overwrites(project: Path) -> None:
    target = project / "tests" / "acceptance" / "test_req_001.py"
    target.parent.mkdir(parents=True)
    target.write_text("# my real tests\n")
    plan = scaffold(project, framework="pytest", apply=True, allow_source_writes=True)
    assert ("exists", "tests/acceptance/test_req_001.py", 2) in plan.files
    assert target.read_text() == "# my real tests\n"
    assert (project / "tests" / "acceptance" / "test_req_002.py").exists()


def test_scaffold_skips_rejected_and_deferred(make_repo: Callable[..., Path]) -> None:
    ledger = json.loads(json.dumps(LEDGER))
    ledger["requirements"][1]["status"] = "deferred"
    root = make_repo({"docs/requirements.json": json.dumps(ledger)})
    plan = scaffold(root, framework="pytest")
    assert [p for _, p, _ in plan.files] == ["tests/acceptance/test_req_001.py"]
    assert any("REQ-002: status deferred" in n for n in plan.notes)


def test_scaffold_rejects_bad_inputs(project: Path, make_repo: Callable[..., Path]) -> None:
    with pytest.raises(ArchonixError, match="unknown framework"):
        scaffold(project, framework="mocha")
    with pytest.raises(ArchonixError, match="not found"):
        scaffold(make_repo({"README.md": "x"}, "empty"), framework="pytest")
    broken = make_repo({"docs/requirements.json": '{"kind": "requirements-ledger"}'}, "broken")
    with pytest.raises(ArchonixError, match="invalid"):
        scaffold(broken, framework="pytest")
    with pytest.raises(PolicyError, match="unsafe"):
        scaffold(project, framework="pytest", out_dir="../outside")


@posix_only
def test_scaffold_refuses_symlinked_output_dir(project: Path, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (project / "tests").mkdir(exist_ok=True)
    (project / "tests" / "acceptance").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(PolicyError):
        scaffold(project, framework="pytest", apply=True, allow_source_writes=True)
    assert list(elsewhere.iterdir()) == []


# ------------------------------------------------------------- traceability (milestone 3)


def _ledger_without_evidence() -> dict[str, Any]:
    ledger: dict[str, Any] = json.loads(json.dumps(LEDGER))
    for r in ledger["requirements"]:
        r["verification"] = {"method": "automated-test", "evidence": []}
        r["status"] = "approved" if r["acceptance_criteria"] else "proposed"
    return ledger


def _junit(name: str) -> list[tuple[str, list[dict[str, Any]]]]:
    cases, _ = parse_junit_cases(OUT / name)
    return [(name, [c.as_dict() for c in cases])]


def test_matrix_links_tests_by_id_without_ledger_evidence() -> None:
    rows = {
        r["criterion"]: r
        for r in traceability(_ledger_without_evidence(), [], _junit("vitest-junit.xml"))
    }
    assert (rows["AC-001-1"]["result"], rows["AC-001-1"]["basis"]) == ("pass", "verified")
    assert rows["AC-001-2"]["result"] == "fail"
    assert rows["AC-002-1"]["result"] == "unknown"  # skipped / pending
    assert rows["—"]["result"] == "missing"


def test_all_linked_tests_must_pass() -> None:
    passed = {
        "name": "test_ac_001_1__a",
        "classname": "t",
        "file": None,
        "result": "passed",
        "ac_ids": ["AC-001-1"],
    }
    skipped = {**passed, "name": "test_ac_001_1__b", "result": "skipped"}
    failed = {**passed, "name": "test_ac_001_1__c", "result": "failed"}
    ledger = _ledger_without_evidence()

    def row(cases: list[dict[str, Any]]) -> dict[str, Any]:
        rows = traceability(ledger, [], [("j", cases)])
        return next(r for r in rows if r["criterion"] == "AC-001-1")

    assert row([passed])["result"] == "pass"
    assert row([passed, skipped])["result"] == "unknown"
    assert row([passed, failed])["result"] == "fail"


def test_cases_recorded_in_reports_are_used() -> None:
    report = {
        "executions": [
            {
                "check_id": "pytest",
                "status": "completed",
                "outcome": "clean",
                "test_cases": [
                    {
                        "name": "test_ac_001_2__rejects",
                        "classname": "t",
                        "file": None,
                        "result": "passed",
                        "ac_ids": ["AC-001-2"],
                    }
                ],
            }
        ]
    }
    rows = {r["criterion"]: r for r in traceability(_ledger_without_evidence(), [report])}
    assert rows["AC-001-2"]["result"] == "pass"
    assert "(pytest) -> passed" in rows["AC-001-2"]["evidence"][0]


def test_explicit_test_reference_resolution() -> None:
    ledger = _ledger_without_evidence()
    ledger["requirements"][0]["verification"]["evidence"] = [
        {
            "acceptance_criterion": "AC-001-1",
            "reference": "test:tests/test_pricing.py::test_x",
            "result": "pass",
        }
    ]
    case: dict[str, Any] = {
        "name": "test_x",
        "classname": "tests.test_pricing",
        "file": None,
        "result": "failed",
        "ac_ids": [],
    }
    row = next(r for r in traceability(ledger, [], [("j", [case])]) if r["criterion"] == "AC-001-1")
    assert row["result"] == "fail"  # the real result overrides the recorded pass
    none = next(r for r in traceability(ledger, []) if r["criterion"] == "AC-001-1")
    assert none["result"] == "unknown" and "not found" in none["evidence"][0]


def test_orphan_tests_are_reported() -> None:
    cases = _junit("vitest-junit.xml")[0][1]
    assert orphan_tests(LEDGER, cases) == [
        "REQ-001: Percentage discounts > AC-LOGIN-1: skipped one -> AC-LOGIN-1"
    ]


def test_cli_matrix_with_junit(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger_path = project / "ledger.json"
    ledger_path.write_text(json.dumps(_ledger_without_evidence()))
    assert (
        main(
            [
                "requirements",
                "matrix",
                str(ledger_path),
                "--junit",
                str(OUT / "jest-junit.xml"),
                "--format",
                "json",
            ]
        )
        == 0
    )
    out = capsys.readouterr()
    rows = {r["criterion"]: r["result"] for r in json.loads(out.out)}
    assert rows["AC-001-1"] == "pass" and rows["AC-002-1"] == "unknown"
    assert "AC-LOGIN-1" in out.err  # orphan warning
    bad = project / "bad.xml"
    bad.write_text("<html/>")
    assert main(["requirements", "matrix", str(ledger_path), "--junit", str(bad)]) == 1


def test_cli_scaffold(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["tests", "scaffold", str(project), "--framework", "pytest"]) == 0
    assert not (project / "tests" / "acceptance").exists()
    assert main(["tests", "scaffold", str(project), "--framework", "pytest", "--apply"]) == 3
    assert (
        main(
            [
                "tests",
                "scaffold",
                str(project),
                "--framework",
                "pytest",
                "--apply",
                "--allow-source-writes",
            ]
        )
        == 0
    )
    assert (project / "tests" / "acceptance" / "test_req_001.py").exists()
    capsys.readouterr()
