"""Release and supply-chain guards: what PyPI shows and how CI is allowed to run."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from conftest import REPO_ROOT

import archonix

REPO_URL = "https://github.com/ayushsaxenagithub/Archonix"
WORKFLOWS = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
PROJECT = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]


def test_readme_links_work_on_pypi() -> None:
    """README is the PyPI long description; relative links would 404 there."""
    text = (REPO_ROOT / "README.md").read_text()
    links = re.findall(r"\]\(([^)\s]+)\)", text)
    relative = [
        x for x in links if not re.match(r"[a-z][a-z0-9+.-]*:", x) and not x.startswith("#")
    ]
    assert relative == [], relative
    missing = []
    for url in links:
        m = re.match(rf"{re.escape(REPO_URL)}/(?:blob|tree)/main/([^#]+)", url)
        if m and not (REPO_ROOT / m.group(1)).exists():
            missing.append(url)
    assert missing == [], missing


def test_changelog_has_entry_for_current_version() -> None:
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text()
    assert re.search(rf"^## \[{re.escape(archonix.__version__)}\]", changelog, re.MULTILINE)


def test_project_urls_and_metadata_for_pypi() -> None:
    urls = PROJECT["urls"]
    assert {"Homepage", "Repository", "Documentation", "Issues", "Changelog"} <= set(urls)
    assert all(u.startswith(REPO_URL) for u in urls.values())
    assert PROJECT["readme"] == "README.md" and PROJECT["license"] == "MIT"
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    for version in re.findall(r'"(3\.\d+)"', ci.split("matrix:", 1)[1].split("steps:", 1)[0]):
        assert f"Programming Language :: Python :: {version}" in PROJECT["classifiers"]


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_actions_are_pinned_to_commit_shas(workflow: Path) -> None:
    for line in workflow.read_text().splitlines():
        m = re.search(r"uses:\s*([^\s#]+)(.*)$", line)
        if not m or m.group(1).startswith("./"):
            continue
        ref = m.group(1).rsplit("@", 1)
        assert len(ref) == 2 and re.fullmatch(r"[0-9a-f]{40}", ref[1]), line.strip()
        assert re.search(r"#\s*v\d", m.group(2)), f"missing version comment: {line.strip()}"


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_permissions_are_minimal(workflow: Path) -> None:
    text = workflow.read_text()
    assert re.search(r"^permissions:\n  contents: read\n", text, re.MULTILINE)
    assert "pull_request_target" not in text
    assert "write-all" not in text
    jobs = re.split(r"^  (?=[a-z][\w-]*:\n)", text.split("\njobs:\n", 1)[1], flags=re.MULTILINE)
    for job in jobs:
        if "id-token: write" in job:
            # OIDC publishing only in jobs gated by a protected environment.
            assert workflow.name == "release.yml" and "environment:" in job, job[:80]
        assert "contents: write" not in job


def test_release_publishes_only_on_release_or_manual_testpypi() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text()
    triggers = text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    assert re.findall(r"^  ([a-z_]+):", triggers, re.MULTILINE) == ["release", "workflow_dispatch"]
    assert "types: [published]" in triggers
    assert "if: github.event_name == 'release'" in text
    assert "repository-url: https://test.pypi.org/legacy/" in text
