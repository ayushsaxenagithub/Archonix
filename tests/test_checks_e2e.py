"""Inventory -> plan -> execute -> parse -> validate -> report, using fake tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import PY_REPO, fixture_text

from archonix.checks import execute_plan, plan_checks
from archonix.cli import main
from archonix.config import load_settings
from archonix.inventory import build_inventory
from archonix.redact import Redactor
from archonix.report import build_workflow_report, render_workflow_report
from archonix.schemas import validate


def run_checks(root: Path, checks: list[str], mode: str = "audit", **perms: bool) -> dict:
    settings = load_settings(root, mode=mode, cli_permissions=perms)
    inv = build_inventory(root, settings)
    plans = plan_checks(root, inv, settings, checks)
    executions, findings, skipped = execute_plan(
        root, plans, settings, artifact_dir=None, redactor=Redactor.from_environment()
    )
    report = build_workflow_report(
        workflow="audit",
        root=str(root),
        settings=settings,
        inventory=inv,
        repository=inv["repository"],
        executions=executions,
        findings=findings,
        skipped=skipped,
        requested_checks=checks,
    )
    validate(report, "workflow-report")
    return report


def by_check(report: dict) -> dict[str, dict]:
    return {e["check_id"]: e for e in report["executions"]}


def test_complete_flow_with_findings(
    make_repo: Callable[..., Path], fake_bin: Callable[..., Path]
) -> None:
    fake_bin("bandit", stdout=fixture_text("tool-output", "bandit-findings.json"), exit_code=1)
    fake_bin("ruff", stdout="[]", exit_code=0)
    report = run_checks(make_repo(PY_REPO), ["ruff", "bandit"])
    ex = by_check(report)
    assert ex["ruff"]["outcome"] == "clean" and ex["ruff"]["tool_version"] == "9.9.9"
    assert ex["bandit"]["outcome"] == "findings" and ex["bandit"]["findings_count"] == 3
    assert report["summary"]["clean"] == 1 and report["summary"]["with_findings"] == 1
    md = render_workflow_report(report)
    assert "B602" in md and "## Limitations" in md and "not proof" in md


def test_missing_tool_and_policy_blocks(
    make_repo: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))  # deterministic: no tools installed
    report = run_checks(make_repo(PY_REPO), ["gitleaks", "pytest", "semgrep-registry"])
    ex = by_check(report)
    assert (
        ex["pytest"]["status"] == "blocked" and "repository code" in ex["pytest"]["outcome_detail"]
    )
    assert ex["semgrep-registry"]["status"] == "blocked"
    assert report["summary"]["checks_run"] == 0
    assert all(e["outcome"] == "not-run" and e["findings_count"] is None for e in ex.values())


def test_discovery_mode_blocks_all_tools(
    make_repo: Callable[..., Path], fake_bin: Callable[..., Path]
) -> None:
    marker = make_repo(PY_REPO)
    fake_bin("ruff", stdout="[]")
    report = run_checks(marker, ["ruff"], mode="discovery")
    assert by_check(report)["ruff"]["status"] == "blocked"


def test_not_applicable_checks_are_skipped(
    make_repo: Callable[..., Path], fake_bin: Callable[..., Path]
) -> None:
    fake_bin("npm")
    report = run_checks(make_repo({"README.md": "x"}), ["npm-audit", "bandit"])
    reasons = {s["check_id"]: s["reason"] for s in report["skipped"]}
    assert reasons["npm-audit"].startswith("not applicable")
    assert reasons["bandit"].startswith("not applicable")


def test_tool_error_is_not_reported_as_clean(
    make_repo: Callable[..., Path], fake_bin: Callable[..., Path]
) -> None:
    fake_bin("ruff", stdout="", stderr="config error", exit_code=2)
    fake_bin("bandit", stdout="garbage", exit_code=1)
    report = run_checks(make_repo(PY_REPO), ["ruff", "bandit"])
    ex = by_check(report)
    assert ex["ruff"]["outcome"] == "tool-error" and ex["ruff"]["findings_count"] == 0
    assert ex["bandit"]["outcome"] == "parse-error" and ex["bandit"]["findings_count"] is None
    assert report["summary"]["failed"] == 2 and report["summary"]["clean"] == 0
    assert any("bandit: output could not be parsed" in x for x in report["limitations"])


def test_timeout_is_recorded(
    make_repo: Callable[..., Path], fake_bin: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_bin("ruff", stdout="[]", sleep=5)
    monkeypatch.setenv("ARCHONIX_TIMEOUT_SECONDS", "0.5")
    report = run_checks(make_repo(PY_REPO), ["ruff"])
    ex = by_check(report)["ruff"]
    assert ex["status"] == "timeout" and ex["exit_code"] is None and ex["outcome"] == "tool-error"


def test_secrets_in_output_are_redacted(
    make_repo: Callable[..., Path], fake_bin: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEPLOY_TOKEN", "super-secret-deploy-value")
    fake_bin("ruff", stdout="[]", stderr="using token super-secret-deploy-value\n")
    report = run_checks(make_repo(PY_REPO), ["ruff"])
    ex = by_check(report)["ruff"]
    assert "super-secret-deploy-value" not in json.dumps(report)
    assert ex["redaction"]["replacements"] >= 1


def test_pytest_runs_only_with_repo_code_permission(
    make_repo: Callable[..., Path], fake_bin: Callable[..., Path]
) -> None:
    fake_bin(
        "pytest",
        report_flag="--junitxml",
        report=fixture_text("tool-output", "pytest-junit-pass.xml"),
    )
    root = make_repo(PY_REPO)
    assert by_check(run_checks(root, ["pytest"]))["pytest"]["status"] == "blocked"
    ex = by_check(run_checks(root, ["pytest"], repo_code=True))["pytest"]
    assert ex["outcome"] == "clean" and ex["test_totals"]["total"] == 2


def test_cli_check_run_writes_only_to_out_dir(
    make_repo: Callable[..., Path], fake_bin: Callable[..., Path], tmp_path: Path
) -> None:
    fake_bin("bandit", stdout=fixture_text("tool-output", "bandit-findings.json"), exit_code=1)
    root = make_repo(PY_REPO)
    before = sorted(p.relative_to(root) for p in root.rglob("*"))
    out = tmp_path / "reports"
    code = main(
        [
            "check",
            "run",
            str(root),
            "--mode",
            "audit",
            "--checks",
            "bandit",
            "--out-dir",
            str(out),
            "--fail-on",
            "high",
        ]
    )
    assert code == 1  # a high-severity finding exists
    assert sorted(p.relative_to(root) for p in root.rglob("*")) == before
    assert {"report.json", "report.md", "artifacts"} <= {p.name for p in out.iterdir()}
    assert main(["validate", str(out / "report.json")]) == 0
    assert (
        main(
            [
                "check",
                "run",
                str(root),
                "--mode",
                "audit",
                "--checks",
                "bandit",
                "--out-dir",
                str(out),
            ]
        )
        == 3
    )  # non-empty out dir refused


def test_cli_fail_on_error(
    make_repo: Callable[..., Path],
    fake_bin: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_bin("ruff", exit_code=2)
    root = make_repo(PY_REPO)
    assert main(["check", "run", str(root), "--mode", "audit", "--checks", "ruff"]) == 0
    assert (
        main(["check", "run", str(root), "--mode", "audit", "--checks", "ruff", "--fail-on-error"])
        == 4
    )
    assert main(["check", "run", str(root), "--checks", "nope"]) == 2
    capsys.readouterr()


def test_cli_plan_executes_nothing(
    make_repo: Callable[..., Path],
    fake_bin: Callable[..., Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    marker = tmp_path / "ran"
    script = fake_bin("ruff")
    script.write_text(f"#!/bin/sh\ntouch {marker}\n")
    assert (
        main(["check", "plan", str(make_repo(PY_REPO)), "--mode", "audit", "--format", "json"]) == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert next(c for c in plan["checks"] if c["check_id"] == "ruff")["action"] == "run"
    assert not marker.exists()


def test_pytest_child_gets_no_bytecode_env_only(
    make_repo: Callable[..., Path], fake_bin: Callable[..., Path], tmp_path: Path
) -> None:
    """Acceptance finding F3: test runs must not leave __pycache__ in the repository."""
    import os

    seen = tmp_path / "env-seen.txt"
    script = fake_bin(
        "pytest",
        report_flag="--junitxml",
        report=fixture_text("tool-output", "pytest-junit-pass.xml"),
    )
    original = script.read_text()
    script.write_text(
        original.replace(
            "time.sleep(spec['sleep'])",
            f"import os; open({str(seen)!r}, 'w')"
            ".write(os.environ.get('PYTHONDONTWRITEBYTECODE', ''))"
            "\ntime.sleep(spec['sleep'])",
        )
    )
    fake_bin("ruff", stdout="[]")
    root = make_repo(PY_REPO)
    report = run_checks(root, ["pytest"], repo_code=True)
    assert by_check(report)["pytest"]["outcome"] == "clean"
    assert seen.read_text() == "1"
    assert "PYTHONDONTWRITEBYTECODE" not in os.environ  # caller's environment untouched
    seen.unlink()
    run_checks(root, ["ruff"])  # other tools do not get the variable
    assert not seen.exists()
