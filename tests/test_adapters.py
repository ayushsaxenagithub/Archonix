"""Adapter parsing and exit-code interpretation against recorded/fixture output.

These are fixture tests: they do not run the real tools. Real-tool runs are in
test_integration_real.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import fixture_text

from archonix.adapters import ADAPTERS, Context
from archonix.runner import CapturedStream, RunResult
from archonix.schemas import errors_for


def result(stdout: str = "", exit_code: int | None = 0, truncated: bool = False) -> RunResult:
    data = stdout.encode()
    return RunResult(
        argv=["x"],
        cwd="/repo",
        started_at="2026-01-01T00:00:00Z",
        duration_seconds=0.1,
        exit_code=exit_code,
        status="completed",
        stdout=CapturedStream(data, len(data), truncated),
    )


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    return Context(
        root=Path("/repo"), artifact_dir=tmp_path, excludes=[".venv"], tool_version="1.0"
    )


def assert_valid_findings(findings: list[dict]) -> None:
    for f in findings:
        assert errors_for(f, "finding") == []


def test_ruff_findings_from_real_output(ctx: Context) -> None:
    out = ADAPTERS["ruff"].interpret(
        result(fixture_text("tool-output", "ruff-findings.json"), 1), ctx
    )
    assert out.outcome == "findings"
    rules = {f["source"]["rule_id"]: f for f in out.findings}
    assert rules["S602"]["category"] == "security" and rules["S602"]["severity"] == "medium"
    assert rules["S602"]["location"]["path"] == "app/ops.py"
    assert_valid_findings(out.findings)


def test_ruff_non_security_s_prefixed_rules_are_lint(ctx: Context) -> None:
    stdout = (
        '[{"code": "SIM105", "message": "m", "filename": "/repo/a.py",'
        ' "location": {"row": 1, "column": 1}}]'
    )
    out = ADAPTERS["ruff"].interpret(result(stdout, 1), ctx)
    assert out.findings[0]["category"] == "lint"


@pytest.mark.parametrize(
    "check, stdout, code, outcome",
    [
        ("ruff", "[]", 0, "clean"),
        ("ruff", "", 2, "tool-error"),
        ("ruff", "not json", 1, "parse-error"),
        ("ruff", "{}", 1, "parse-error"),
        ("ruff", "[]", 1, "parse-error"),  # tool says findings, none parsed
        ("bandit", '{"results": []}', 0, "clean"),
        ("bandit", "[]", 1, "parse-error"),
        ("bandit", "", 2, "tool-error"),
        ("vulture", "", 0, "clean"),
        ("vulture", "", 3, "parse-error"),
        ("vulture", "", 1, "tool-error"),
        ("semgrep-local", '{"results": [], "errors": []}', 0, "clean"),
        ("semgrep-local", "", 7, "tool-error"),
        ("npm-audit", fixture_text("tool-output", "npm-audit-error.json"), 1, "tool-error"),
        ("npm-audit", '{"auditReportVersion": 2, "vulnerabilities": {}}', 0, "clean"),
        ("npm-audit", '{"advisories": {}}', 1, "parse-error"),
    ],
)
def test_exit_codes_and_malformed_output(
    ctx: Context, check: str, stdout: str, code: int, outcome: str
) -> None:
    assert ADAPTERS[check].interpret(result(stdout, code), ctx).outcome == outcome


def test_truncated_output_is_not_parsed(ctx: Context) -> None:
    out = ADAPTERS["bandit"].interpret(
        result(fixture_text("tool-output", "truncated.json"), 1, True), ctx
    )
    assert out.outcome == "parse-error" and "max_output_bytes" in out.detail


def test_bandit_severity_and_confidence_are_separate(ctx: Context) -> None:
    out = ADAPTERS["bandit"].interpret(
        result(fixture_text("tool-output", "bandit-findings.json"), 1), ctx
    )
    b602 = next(f for f in out.findings if f["source"]["rule_id"] == "B602")
    assert (b602["severity"], b602["confidence"]) == ("high", "high")
    b105 = next(f for f in out.findings if f["source"]["rule_id"] == "B105")
    assert (b105["severity"], b105["confidence"]) == ("low", "medium")
    assert b602["source"]["original_severity"] == "HIGH"
    assert any("cwe.mitre.org" in r for r in b602["references"])
    assert_valid_findings(out.findings)


def test_vulture_confidence_never_high(ctx: Context) -> None:
    text = (
        fixture_text("tool-output", "vulture-findings.txt")
        + "app/x.py:1: unused import 'os' (100% confidence)\nsome unexpected line\n"
    )
    out = ADAPTERS["vulture"].interpret(result(text, 3), ctx)
    assert len(out.findings) == 4
    assert {f["confidence"] for f in out.findings} == {"low", "medium"}
    assert out.limitations == ["1 unrecognised output entries were ignored"]


def test_semgrep_parsing(ctx: Context) -> None:
    out = ADAPTERS["semgrep-local"].interpret(
        result(fixture_text("tool-output", "semgrep-findings.json")), ctx
    )
    assert out.outcome == "findings"
    sev = {f["source"]["rule_id"].split(".")[-1]: f["severity"] for f in out.findings}
    assert sev == {"subprocess-shell-true": "high", "no-print": "low"}
    assert out.limitations == ["semgrep reported 1 error(s) (partial scan)"]
    assert_valid_findings(out.findings)


def test_gitleaks_report_file(ctx: Context) -> None:
    (ctx.artifact_dir / "gitleaks.json").write_text(
        fixture_text("tool-output", "gitleaks-findings.json")
    )
    out = ADAPTERS["gitleaks"].interpret(result("", 1), ctx)
    assert out.outcome == "findings"
    f = out.findings[0]
    assert f["category"] == "secrets" and f["location"]["start_line"] == 4
    assert "REDACTED" not in (f["evidence"] or "")  # matched text is never copied
    (ctx.artifact_dir / "gitleaks.json").write_text("[]")
    assert ADAPTERS["gitleaks"].interpret(result("", 0), ctx).outcome == "clean"
    (ctx.artifact_dir / "gitleaks.json").unlink()
    assert ADAPTERS["gitleaks"].interpret(result("", 0), ctx).outcome == "parse-error"


def test_npm_audit_findings(ctx: Context) -> None:
    out = ADAPTERS["npm-audit"].interpret(
        result(fixture_text("tool-output", "npm-audit-findings.json"), 1), ctx
    )
    by = {f["source"]["rule_id"]: f for f in out.findings}
    assert by["npm:lodash"]["severity"] == "high"
    assert by["npm:minimist-wrapper"]["severity"] == "medium"
    assert by["npm:lodash"]["references"] == ["https://github.com/advisories/GHSA-p6mc-m468-83gw"]
    assert_valid_findings(out.findings)


def test_pytest_junit_counts_and_failures(ctx: Context) -> None:
    (ctx.artifact_dir / "pytest-junit.xml").write_text(
        fixture_text("tool-output", "pytest-junit-failures.xml")
    )
    out = ADAPTERS["pytest"].interpret(result("", 1), ctx)
    assert out.outcome == "tests-failed"
    assert out.test_totals == {"total": 5, "passed": 2, "failed": 1, "skipped": 1, "errored": 1}
    assert {f["source"]["rule_id"] for f in out.findings} == {"failure", "error"}


def test_pytest_exit_codes(ctx: Context) -> None:
    (ctx.artifact_dir / "pytest-junit.xml").write_text(
        fixture_text("tool-output", "pytest-junit-pass.xml")
    )
    assert ADAPTERS["pytest"].interpret(result("", 0), ctx).outcome == "clean"
    no_tests = ADAPTERS["pytest"].interpret(result("", 5), ctx)
    assert no_tests.outcome == "tool-error" and "no tests collected" in no_tests.detail
    (ctx.artifact_dir / "pytest-junit.xml").write_text(
        fixture_text("tool-output", "pytest-junit-malformed.xml")
    )
    bad = ADAPTERS["pytest"].interpret(result("", 0), ctx)
    assert bad.outcome == "parse-error"
    assert bad.test_totals == {
        "total": None,
        "passed": None,
        "failed": None,
        "skipped": None,
        "errored": None,
    }


def test_every_adapter_documents_itself() -> None:
    for adapter in ADAPTERS.values():
        d = adapter.describe()
        assert d["exit_codes"] and d["description"] and d["notes"] and d["status"]


# --- Review issue 4: incomplete scans must be structured, not just a limitation -------


def test_bandit_analysis_errors_mark_scan_incomplete(ctx: Context) -> None:
    doc = {"results": [], "errors": [{"filename": "/repo/broken.py", "reason": "syntax error"}]}
    out = ADAPTERS["bandit"].interpret(result(json.dumps(doc), 0), ctx)
    assert out.outcome == "clean" and out.complete is False
    assert out.coverage_detail == "bandit could not analyse 1 file(s): broken.py"
    clean = ADAPTERS["bandit"].interpret(result('{"results": [], "errors": []}', 0), ctx)
    assert clean.complete is True


def test_semgrep_errors_mark_scan_incomplete(ctx: Context) -> None:
    out = ADAPTERS["semgrep-local"].interpret(
        result(fixture_text("tool-output", "semgrep-findings.json")), ctx
    )
    assert out.outcome == "findings" and out.complete is False
    full = ADAPTERS["semgrep-local"].interpret(result('{"results": [], "errors": []}'), ctx)
    assert full.complete is True
