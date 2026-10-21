"""Adapters for Ruff, Bandit, Vulture and pytest."""

from __future__ import annotations

import re

# The JUnit file is written by pytest, which only runs when repository code is already
# trusted (--allow-repo-code); CPython's bundled expat mitigates entity-expansion attacks.
import xml.etree.ElementTree as ET  # nosec B405
from pathlib import Path
from typing import Any

from ..findings import make_finding
from ..policy import Requirements
from ..runner import RunResult
from .base import (
    STATUS_TESTED_FIXTURES,
    STATUS_TESTED_REAL,
    Adapter,
    Context,
    ParseOutcome,
    has_python,
    load_json_output,
    relpath,
    unexpected_exit,
)

# flake8-bandit rules (S101, S603, ...) are security checks; SIM*, SLF* etc. are not.
_RUFF_SECURITY = re.compile(r"^S\d{3}$")


def _glob_excludes(excludes: list[str]) -> str:
    return ",".join(f"*/{e}/*" if not any(c in e for c in "*/") else e for e in excludes)


class RuffAdapter(Adapter):
    id = "ruff"
    tool = "ruff"
    executable = "ruff"
    category = "lint"
    description = "Ruff lint (read-only: --no-fix, --no-cache); S-rules are reported as security."
    requires = Requirements(external_tool=True)
    status = STATUS_TESTED_REAL
    exit_codes = {0: "no violations", 1: "violations found", 2: "configuration or internal error"}
    notes = "Uses the repository's Ruff configuration. Does not execute repository code."

    def applies(self, inventory: dict[str, Any], root: Path) -> tuple[bool, str]:
        return has_python(inventory)

    def argv(self, ctx: Context) -> list[str]:
        return [
            "ruff",
            "check",
            "--output-format",
            "json",
            "--no-cache",
            "--no-fix",
            "--extend-exclude",
            ",".join(ctx.excludes),
            *ctx.extra_args,
            ".",
        ]

    def interpret(self, result: RunResult, ctx: Context) -> ParseOutcome:
        if result.exit_code not in (0, 1):
            return unexpected_exit(result, self.exit_codes)
        data, err = load_json_output(result.stdout.text(), result.stdout.truncated)
        if err:
            return ParseOutcome("parse-error", err)
        if not isinstance(data, list):
            return ParseOutcome("parse-error", "expected a JSON array of diagnostics")
        findings, skipped = [], 0
        for item in data:
            if not isinstance(item, dict) or "filename" not in item:
                skipped += 1
                continue
            code = item.get("code") or "syntax-error"
            security = _RUFF_SECURITY.match(code) is not None
            loc = item.get("location") or {}
            end = item.get("end_location") or {}
            findings.append(
                make_finding(
                    tool="ruff",
                    check_id=self.id,
                    tool_version=ctx.tool_version,
                    category="security" if security else "lint",
                    title=f"{code}: {item.get('message', '')}".strip(),
                    message=item.get("message"),
                    rule_id=code,
                    severity="medium" if security else "low",
                    confidence="high",
                    path=relpath(item["filename"], ctx.root),
                    line=loc.get("row"),
                    end_line=end.get("row"),
                    column=loc.get("column"),
                    references=[item["url"]] if item.get("url") else [],
                )
            )
        return _finish(findings, skipped, result.exit_code == 1)


class BanditAdapter(Adapter):
    id = "bandit"
    tool = "bandit"
    executable = "bandit"
    category = "security"
    description = "Bandit Python security lint (AST-based; does not import code)."
    requires = Requirements(external_tool=True)
    status = STATUS_TESTED_REAL
    exit_codes = {0: "no issues", 1: "issues found", 2: "usage or configuration error"}
    notes = "Pattern-based; findings need review. A clean result is not proof of security."

    def applies(self, inventory: dict[str, Any], root: Path) -> tuple[bool, str]:
        return has_python(inventory)

    def argv(self, ctx: Context) -> list[str]:
        return [
            "bandit",
            "-r",
            ".",
            "-f",
            "json",
            "-q",
            "-x",
            _glob_excludes(ctx.excludes),
            *ctx.extra_args,
        ]

    def interpret(self, result: RunResult, ctx: Context) -> ParseOutcome:
        if result.exit_code not in (0, 1):
            return unexpected_exit(result, self.exit_codes)
        data, err = load_json_output(result.stdout.text(), result.stdout.truncated)
        if err:
            return ParseOutcome("parse-error", err)
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            return ParseOutcome("parse-error", "expected an object with a 'results' array")
        findings, skipped = [], 0
        for item in data["results"]:
            if not isinstance(item, dict) or "filename" not in item:
                skipped += 1
                continue
            cwe = item.get("issue_cwe") or {}
            refs = [r for r in (item.get("more_info"), cwe.get("link")) if r]
            sev = str(item.get("issue_severity", "")).lower()
            conf = str(item.get("issue_confidence", "")).lower()
            findings.append(
                make_finding(
                    tool="bandit",
                    check_id=self.id,
                    tool_version=ctx.tool_version,
                    category="security",
                    rule_id=item.get("test_id"),
                    title=(
                        f"{item.get('test_id')} {item.get('test_name')}: {item.get('issue_text')}"
                    ),
                    message=item.get("issue_text"),
                    severity=sev if sev in {"high", "medium", "low"} else "unknown",
                    confidence=conf if conf in {"high", "medium", "low"} else "unknown",
                    original_severity=item.get("issue_severity"),
                    original_confidence=item.get("issue_confidence"),
                    path=relpath(item["filename"], ctx.root),
                    line=item.get("line_number"),
                    column=item.get("col_offset"),
                    evidence=(item.get("code") or None),
                    references=refs,
                )
            )
        outcome = _finish(findings, skipped, result.exit_code == 1)
        errors = data.get("errors") or []
        if errors:
            outcome.limitations.append(f"bandit could not analyse {len(errors)} file(s)")
        return outcome


_VULTURE_LINE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+): (?P<msg>.+?) \((?P<conf>\d+)% confidence"
)


class VultureAdapter(Adapter):
    id = "vulture"
    tool = "vulture"
    executable = "vulture"
    category = "dead-code"
    description = "Vulture unused-code candidates (static; min confidence 60%)."
    requires = Requirements(external_tool=True)
    status = STATUS_TESTED_REAL
    exit_codes = {
        0: "no dead code found",
        1: "invalid input (missing file or syntax error)",
        2: "invalid arguments",
        3: "dead code found",
    }
    notes = (
        "Candidates only: dynamic imports, framework registration, reflection and external "
        "consumers are invisible to static analysis. Never delete automatically."
    )

    def applies(self, inventory: dict[str, Any], root: Path) -> tuple[bool, str]:
        return has_python(inventory)

    def argv(self, ctx: Context) -> list[str]:
        return [
            "vulture",
            ".",
            "--min-confidence",
            "60",
            "--exclude",
            _glob_excludes(ctx.excludes),
            *ctx.extra_args,
        ]

    def interpret(self, result: RunResult, ctx: Context) -> ParseOutcome:
        if result.exit_code not in (0, 3):
            return unexpected_exit(result, self.exit_codes)
        if result.stdout.truncated:
            return ParseOutcome("parse-error", "output exceeded max_output_bytes; not parsed")
        findings, skipped = [], 0
        for line in result.stdout.text().splitlines():
            if not line.strip():
                continue
            m = _VULTURE_LINE.match(line)
            if not m:
                skipped += 1
                continue
            conf = int(m.group("conf"))
            findings.append(
                make_finding(
                    tool="vulture",
                    check_id=self.id,
                    tool_version=ctx.tool_version,
                    category="dead-code",
                    rule_id=m.group("msg").split(" '")[0],
                    title=m.group("msg"),
                    message=f"{m.group('msg')} ({conf}% confidence)",
                    severity="info",
                    # Even 100% from vulture means "no static reference", not "unused".
                    confidence="medium" if conf >= 90 else "low",
                    original_confidence=f"{conf}%",
                    path=relpath(m.group("path"), ctx.root),
                    line=int(m.group("line")),
                    remediation="Confirm there are no dynamic, framework or external references "
                    "before removing.",
                )
            )
        if result.exit_code == 3 and not findings:
            return ParseOutcome("parse-error", "exit code 3 (dead code found) but no lines parsed")
        return _finish(findings, skipped, result.exit_code == 3)


class PytestAdapter(Adapter):
    id = "pytest"
    tool = "pytest"
    executable = "pytest"
    category = "tests"
    description = "pytest with JUnit XML results (executes repository code)."
    requires = Requirements(external_tool=True, repo_code=True, writes_cache=True)
    status = STATUS_TESTED_REAL
    exit_codes = {
        0: "all tests passed",
        1: "some tests failed",
        2: "interrupted",
        3: "internal error",
        4: "usage error",
        5: "no tests collected",
    }
    # Keep the run from leaving __pycache__ directories in the repository; together with
    # `-p no:cacheprovider` (no .pytest_cache). Applies to this child process only.
    env = {"PYTHONDONTWRITEBYTECODE": "1"}
    notes = (
        "Runs the repository's tests, conftest.py and plugins: only for trusted code. "
        "Bytecode and pytest caches are disabled for the run; tests may still write files "
        "or use the network on their own."
    )

    def applies(self, inventory: dict[str, Any], root: Path) -> tuple[bool, str]:
        if any(d["category"] == "test" and d["name"] == "pytest" for d in inventory["detections"]):
            return True, "pytest configuration or dependency detected"
        return False, "pytest not detected"

    def argv(self, ctx: Context) -> list[str]:
        return [
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            f"--junitxml={ctx.artifact_dir / 'pytest-junit.xml'}",
            *ctx.extra_args,
        ]

    def interpret(self, result: RunResult, ctx: Context) -> ParseOutcome:
        if result.exit_code not in (0, 1):
            return unexpected_exit(result, self.exit_codes)
        report = ctx.artifact_dir / "pytest-junit.xml"
        return parse_junit(report, self.id, ctx, failed=result.exit_code == 1)


def parse_junit(report: Path, check_id: str, ctx: Context, *, failed: bool) -> ParseOutcome:
    unknown: dict[str, int | None] = {
        "total": None,
        "passed": None,
        "failed": None,
        "skipped": None,
        "errored": None,
    }
    if not report.is_file():
        return ParseOutcome("parse-error", "JUnit report was not written", test_totals=unknown)
    try:
        root = ET.parse(report).getroot()  # noqa: S314  # nosec B314
    except ET.ParseError as exc:
        return ParseOutcome("parse-error", f"JUnit report is malformed: {exc}", test_totals=unknown)
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    if not suites:
        return ParseOutcome(
            "parse-error", "no <testsuite> elements in JUnit report", test_totals=unknown
        )
    totals = {"total": 0, "failed": 0, "skipped": 0, "errored": 0}
    findings = []
    for suite in suites:
        try:
            totals["total"] += int(suite.get("tests", 0))
            totals["failed"] += int(suite.get("failures", 0))
            totals["skipped"] += int(suite.get("skipped", 0))
            totals["errored"] += int(suite.get("errors", 0))
        except ValueError:
            return ParseOutcome(
                "parse-error", "non-numeric counts in JUnit report", test_totals=unknown
            )
        for case in suite.iter("testcase"):
            problem = case.find("failure")
            if problem is None:
                problem = case.find("error")
            if problem is None:
                continue
            name = f"{case.get('classname', '')}::{case.get('name', '')}".strip(":")
            path = case.get("file") or (case.get("classname", "").replace(".", "/") + ".py")
            findings.append(
                make_finding(
                    tool="pytest",
                    check_id=check_id,
                    tool_version=ctx.tool_version,
                    category="test-failure",
                    rule_id=problem.tag,
                    title=f"Test {problem.tag}: {name}",
                    message=(problem.get("message") or "")[:500] or None,
                    severity="medium",
                    confidence="high",
                    path=path,
                    line=int(line_attr)
                    if (line_attr := case.get("line") or "").isdigit()
                    else None,
                    symbol=name,
                    discriminator=name,
                )
            )
    test_totals: dict[str, int | None] = {
        **totals,
        "passed": totals["total"] - totals["failed"] - totals["skipped"] - totals["errored"],
    }
    if failed or totals["failed"] or totals["errored"]:
        return ParseOutcome(
            "tests-failed",
            f"{totals['failed']} failed, {totals['errored']} errored of {totals['total']}",
            findings,
            test_totals,
        )
    return ParseOutcome(
        "clean",
        f"{test_totals['passed']} passed, {totals['skipped']} skipped",
        findings,
        test_totals,
    )


def _finish(findings: list[dict[str, Any]], skipped: int, tool_says_findings: bool) -> ParseOutcome:
    limitations = [f"{skipped} unrecognised output entries were ignored"] if skipped else []
    if findings:
        return ParseOutcome(
            "findings", f"{len(findings)} finding(s)", findings, limitations=limitations
        )
    if tool_says_findings:
        return ParseOutcome(
            "parse-error",
            "tool reported findings but none could be parsed",
            limitations=limitations,
        )
    return ParseOutcome("clean", "no findings reported", limitations=limitations)


__all__ = [
    "STATUS_TESTED_FIXTURES",
    "BanditAdapter",
    "PytestAdapter",
    "RuffAdapter",
    "VultureAdapter",
    "parse_junit",
]
