"""OSV-Scanner adapter: fixture tests against output recorded from osv-scanner 2.7.0.

The recorded fixtures were produced by a real run (paths rewritten to /repo). The real-tool
test that needs the network is in test_integration_real.py.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import fixture_text

from archonix.adapters import ADAPTERS, Context
from archonix.adapters.dependency_tools import _cvss_severity, _exclude_args
from archonix.checks import plan_checks
from archonix.config import load_settings
from archonix.inventory import build_inventory
from archonix.runner import CapturedStream, RunResult
from archonix.schemas import errors_for

OSV = ADAPTERS["osv-scanner"]


def result(stdout: str, exit_code: int | None, truncated: bool = False) -> RunResult:
    data = stdout.encode()
    return RunResult(
        ["osv-scanner"],
        "/repo",
        "2026-01-01T00:00:00Z",
        0.1,
        exit_code,
        "completed",
        stdout=CapturedStream(data, len(data), truncated),
    )


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    return Context(
        root=Path("/repo"),
        artifact_dir=tmp_path,
        excludes=[".venv", "*.egg-info"],
        tool_version="2.7.0",
    )


def test_recorded_findings_are_normalised(ctx: Context) -> None:
    out = OSV.interpret(result(fixture_text("tool-output", "osv-scanner-findings.json"), 1), ctx)
    assert out.outcome == "findings"
    by_pkg: dict[str, list[dict]] = {}
    for f in out.findings:
        assert errors_for(f, "finding") == []
        by_pkg.setdefault(f["location"]["symbol"], []).append(f)
    # One finding per advisory group, not per alias: 11 urllib3 groups, 6 lodash groups.
    assert {k: len(v) for k, v in by_pkg.items()} == {
        "PyPI:urllib3@1.26.4": 11,
        "npm:lodash@4.17.15": 6,
    }
    assert {f["location"]["path"] for f in out.findings} == {
        "requirements.txt",
        "web/package-lock.json",
    }
    assert all(f["confidence"] == "high" for f in out.findings)  # pinned in lockfiles
    assert len({f["id"] for f in out.findings}) == len(out.findings)


def test_severity_aliases_and_fixed_versions(ctx: Context) -> None:
    out = OSV.interpret(result(fixture_text("tool-output", "osv-scanner-findings.json"), 1), ctx)
    redos = next(f for f in out.findings if f["source"]["rule_id"] == "GHSA-29mw-wpgm-hmr9")
    assert redos["severity"] == "medium" and redos["source"]["original_severity"] == "5.3"
    assert "CVE-2020-28500" in redos["title"] and "CVE-2020-28500" in redos["evidence"]
    assert redos["remediation"].startswith("upgrade lodash to a fixed version: 4.17.21")
    assert "https://osv.dev/vulnerability/GHSA-29mw-wpgm-hmr9" in redos["references"]
    for f in out.findings:  # fixed versions never come from GIT (commit SHA) ranges
        assert not any(len(part) == 40 for part in f["remediation"].replace(",", " ").split())


def test_clean_output(ctx: Context) -> None:
    out = OSV.interpret(result(fixture_text("tool-output", "osv-scanner-clean.json"), 0), ctx)
    assert (out.outcome, out.findings) == ("clean", [])


@pytest.mark.parametrize(
    "stdout, code, outcome",
    [
        ("", 128, "tool-error"),  # no package sources
        ("", 127, "tool-error"),  # general error
        ("", 2, "tool-error"),  # undocumented
        ("not json", 1, "parse-error"),
        ('{"results": {}}', 1, "parse-error"),
        ('{"results": []}', 1, "parse-error"),  # tool says vulnerable, nothing parsed
    ],
)
def test_exit_codes_and_malformed_output(
    ctx: Context, stdout: str, code: int, outcome: str
) -> None:
    assert OSV.interpret(result(stdout, code), ctx).outcome == outcome


def test_truncated_output_is_not_parsed(ctx: Context) -> None:
    text = fixture_text("tool-output", "osv-scanner-findings.json")
    out = OSV.interpret(result(text, 1, truncated=True), ctx)
    assert out.outcome == "parse-error" and "max_output_bytes" in out.detail


def test_resolved_transitive_versions_have_medium_confidence(ctx: Context) -> None:
    doc = {
        "results": [
            {
                "source": {"path": "/repo/requirements.txt", "type": "unknown"},
                "packages": [
                    {
                        "package": {"name": "certifi", "version": "1.0", "ecosystem": "PyPI"},
                        "vulnerabilities": [{"id": "GHSA-aaaa-bbbb-cccc"}],
                        "groups": [{"ids": ["GHSA-aaaa-bbbb-cccc"], "max_severity": ""}],
                    }
                ],
            }
        ]
    }
    f = OSV.interpret(result(json.dumps(doc), 1), ctx).findings[0]
    assert f["confidence"] == "medium" and f["severity"] == "unknown"
    assert "resolved by osv-scanner" in f["evidence"]


def test_repository_ignore_file_is_reported(tmp_path: Path) -> None:
    (tmp_path / "osv-scanner.toml").write_text("[[IgnoredVulns]]\nid = 'GHSA-x'\n")
    ctx = Context(root=tmp_path, artifact_dir=tmp_path, excludes=[])
    out = OSV.interpret(result(fixture_text("tool-output", "osv-scanner-clean.json"), 0), ctx)
    assert out.limitations == ["repository osv-scanner.toml may ignore vulnerabilities; review it"]


def test_cvss_mapping_and_exclusions() -> None:
    assert [_cvss_severity(s) for s in ("9.8", "7.0", "5.3", "0.1", "0", "", "n/a")] == [
        "critical",
        "high",
        "medium",
        "low",
        "info",
        None,
        None,
    ]
    assert _exclude_args(["node_modules", "*.egg-info"]) == [
        "--x-exclude",
        "node_modules",
        "--x-exclude",
        "g:**/*.egg-info",
    ]


def test_argv_disables_call_analysis(ctx: Context) -> None:
    """Call analysis can run Rust build scripts, i.e. execute repository code."""
    argv = OSV.argv(ctx)
    assert "--no-call-analysis=all" in argv and argv[:3] == ["osv-scanner", "scan", "source"]
    assert OSV.requires.network and not OSV.requires.repo_code


def test_planning_requires_network_and_a_lockfile(
    make_repo: Callable[..., Path], fake_bin: Callable[..., Path]
) -> None:
    fake_bin("osv-scanner")
    locked = make_repo({"web/package-lock.json": "{}", "requirements.txt": "x==1\n"}, "locked")
    settings = load_settings(locked, mode="audit")
    plan = plan_checks(locked, build_inventory(locked, settings), settings, ["osv-scanner"])[0]
    assert plan.action == "block" and "network" in plan.reason
    settings = load_settings(locked, mode="audit", cli_permissions={"network": True})
    plan = plan_checks(locked, build_inventory(locked, settings), settings, ["osv-scanner"])[0]
    assert plan.action == "run"
    bare = make_repo({"README.md": "x"}, "bare")
    settings = load_settings(bare, mode="audit", cli_permissions={"network": True})
    plan = plan_checks(bare, build_inventory(bare, settings), settings, ["osv-scanner"])[0]
    assert plan.action == "skip" and "no lockfiles" in plan.reason
