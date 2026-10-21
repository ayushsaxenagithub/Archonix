"""Acceptance scripts and their documentation must not drift apart."""

from __future__ import annotations

import ast
import re
import subprocess
import sys

from conftest import REPO_ROOT

ACCEPTANCE = REPO_ROOT / "acceptance"
README = (ACCEPTANCE / "README.md").read_text()


def test_every_criterion_used_by_the_cli_suite_is_documented() -> None:
    used = set(re.findall(r'"(AC-\d+)"', (ACCEPTANCE / "cli_acceptance.py").read_text()))
    documented = set(re.findall(r"^\| (AC-\d+) \|", README, re.MULTILINE))
    assert used and used <= documented, sorted(used - documented)
    assert documented <= used, f"documented but never checked: {sorted(documented - used)}"


def test_every_claude_code_task_is_documented() -> None:
    tree = ast.parse((ACCEPTANCE / "claude_code.py").read_text())
    tasks = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "TASKS"
    )
    names = [k.value for k in tasks.value.keys]  # type: ignore[union-attr]
    documented = set(re.findall(r"^\| (T\d) ", README, re.MULTILINE))
    assert {name.split("-", 1)[0] for name in names} == documented, (names, documented)


def test_claude_code_run_requires_explicit_consent() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ACCEPTANCE / "claude_code.py"),
            "--archonix",
            "archonix",
            "--out",
            "unused",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2 and "--yes-send-fixtures-to-anthropic" in result.stderr


def test_untested_assistants_are_not_claimed() -> None:
    assistants = (REPO_ROOT / "docs" / "assistants.md").read_text()
    for row in ("OpenAI Codex", "Cursor"):
        line = next(x for x in assistants.splitlines() if x.startswith(f"| {row}"))
        assert "not tested in the assistant" in line, line
