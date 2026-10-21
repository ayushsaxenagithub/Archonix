"""Skill guidance contracts found necessary by acceptance testing with a real assistant.

In a recorded Claude Code run (bug-fix task), the assistant fixed the bug but left it
unverified: the generic test command was not permitted, and the bug workflow did not
point to the permitted `archonix check run ... --checks pytest` path. Workflows that
change code must name a verification command and an explicit "not run" fallback.
"""

from __future__ import annotations

import re

import pytest
from conftest import REPO_ROOT

SKILL = REPO_ROOT / "skills" / "archonix"
TEST_COMMAND = re.compile(r"archonix check run \. --mode audit --allow-repo-code --checks pytest")


@pytest.mark.parametrize("workflow", ["bug-investigation.md", "implementation.md"])
def test_code_changing_workflows_name_the_cli_test_command(workflow: str) -> None:
    text = (SKILL / "references" / workflow).read_text()
    assert TEST_COMMAND.search(text), f"{workflow} must show how to run tests through the CLI"


@pytest.mark.parametrize("workflow", ["bug-investigation.md", "implementation.md"])
def test_code_changing_workflows_require_honest_fallback(workflow: str) -> None:
    text = (SKILL / "references" / workflow).read_text().lower()
    assert "not run" in text or "unverified" in text
    assert "exact command" in text


def test_skill_entry_point_shows_test_verification() -> None:
    text = (SKILL / "SKILL.md").read_text()
    lines = [line for line in text.splitlines() if TEST_COMMAND.search(line)]
    assert lines, "SKILL.md must show how to run tests through the CLI"
    # Running repository code stays behind explicit authorization.
    assert all("authorized" in line for line in lines)
    assert "**not run**" in text


def test_report_location_rule_is_explicit() -> None:
    """Acceptance finding F2: told not to modify files, an assistant invented an output
    directory three levels above the repository. The skill must state the rule."""
    policy = (SKILL / "references" / "execution-policy.md").read_text()
    section = policy.split("## Where reports and artifacts go", 1)[1].split("\n## ", 1)[0]
    for required in (
        ".archonix/<run-name>/",
        "mktemp -d",
        "not to modify files",
        "Never invent",
        "--format md",
        "state the path",
    ):
        assert required in section, required
    for doc in ("SKILL.md", "references/release-readiness.md"):
        assert "Where reports and artifacts go" in (SKILL / doc).read_text(), doc
