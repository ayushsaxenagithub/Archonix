"""`archonix agents init` / `sync`: .ai/ as one source for every assistant's context."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import PY_REPO, REPO_ROOT

from archonix.agents import CLAUDE_MD, SYNC_MANIFEST, Plan, init, sync
from archonix.cli import main
from archonix.config import load_settings
from archonix.errors import ArchonixError, PolicyError
from archonix.install import parse_frontmatter, validate_skill

posix_only = pytest.mark.skipif(os.name != "posix", reason="symlinks")
LEDGER = (REPO_ROOT / "examples" / "requirements" / "ledger.json").read_text()


def _init(root: Path, apply: bool = True) -> Plan:
    return init(root, load_settings(root), allow_source_writes=True, apply=apply)


def _sync(root: Path, targets: tuple[str, ...] = ("claude", "agents")) -> Plan:
    return sync(root, targets=targets, allow_source_writes=True, apply=True)


@pytest.fixture
def project(make_repo: Callable[..., Path]) -> Path:
    return make_repo(
        {**PY_REPO, "docs/requirements.json": LEDGER, "docs/business-rules.md": "# rules\n"}
    )


# ------------------------------------------------------------------------- init


def test_init_is_a_dry_run_and_needs_permission(project: Path) -> None:
    plan = init(project, load_settings(project), allow_source_writes=False, apply=False)
    assert ("create", ".ai/instructions.md") in plan.actions
    assert not (project / ".ai").exists()
    with pytest.raises(PolicyError, match="allow-source-writes"):
        init(project, load_settings(project), allow_source_writes=False, apply=True)


def test_init_drafts_evidence_based_instructions_and_requirements_skill(project: Path) -> None:
    _init(project)
    text = (project / ".ai" / "instructions.md").read_text()
    assert "framework: FastAPI (declared dependency" in text
    assert "--checks pytest" in text and "REQ-001 (verified): Percentage discounts" in text
    # Found when Claude Code read the generated file: the list must say it is must-haves.
    assert "Must-have requirements (priority `must`" in text
    assert "REQ-003" not in text  # a `could` requirement is not listed as must-have
    assert "`docs/business-rules.md`" in text
    assert "TODO: naming, error handling" in text  # unknowns are marked, not invented
    skill = project / ".ai" / "skills" / "example-python-service-requirements"
    assert validate_skill(skill) == []
    body = (skill / "SKILL.md").read_text()
    assert "AC-001-1: A 25% discount on 200.00 yields 150.00." in body
    assert "Business rules are documented" in body


def test_init_never_overwrites(project: Path) -> None:
    (project / ".ai").mkdir()
    (project / ".ai" / "instructions.md").write_text("mine")
    plan = _init(project)
    assert ("exists", ".ai/instructions.md") in plan.actions
    assert (project / ".ai" / "instructions.md").read_text() == "mine"


def test_init_without_ledger_reports_skipped_skill(make_repo: Callable[..., Path]) -> None:
    root = make_repo(
        {"package.json": '{"name": "web", "scripts": {"test": "vitest run", "lint": "eslint ."}}'}
    )
    plan = _init(root)
    assert any("requirements skill was not generated" in n for n in plan.notes)
    text = (root / ".ai" / "instructions.md").read_text()
    assert "`npm run test` (package.json: `vitest run`)" in text
    assert "`npm run lint`" in text and "run the Archonix discovery" in text
    assert not (root / ".ai" / "skills").exists()


def test_project_name_cannot_break_skill_frontmatter(make_repo: Callable[..., Path]) -> None:
    ledger = json.loads(LEDGER)
    ledger["project"] = 'Acme: "Billing" \\ Portal'
    root = make_repo({"docs/requirements.json": json.dumps(ledger)})
    _init(root)
    skill = root / ".ai" / "skills" / "acme-billing-portal-requirements"
    assert validate_skill(skill) == []
    meta = parse_frontmatter((skill / "SKILL.md").read_text())
    assert meta["name"] == "acme-billing-portal-requirements"
    assert meta["description"].startswith(
        'Requirements and acceptance criteria of Acme: \\"Billing'
    )


@posix_only
def test_init_refuses_symlinked_ai_dir(project: Path, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (project / ".ai").symlink_to(elsewhere, target_is_directory=True)
    plan = _init(project)
    assert plan.conflicts and list(elsewhere.iterdir()) == []


# ------------------------------------------------------------------------- sync


def test_sync_requires_instructions(project: Path) -> None:
    plan = _sync(project)
    assert plan.conflicts and "not found" in plan.conflicts[0]
    assert not (project / "AGENTS.md").exists()


def test_sync_renders_every_target_and_is_idempotent(project: Path) -> None:
    _init(project)
    plan = sync(project, allow_source_writes=False, apply=False)
    assert {a for a, _ in plan.actions} == {"create"} and not (project / "AGENTS.md").exists()
    with pytest.raises(PolicyError):
        sync(project, allow_source_writes=False, apply=True)
    assert _sync(project).applied
    agents_md = (project / "AGENTS.md").read_text()
    assert agents_md.startswith("<!-- Generated by `archonix agents sync`")
    assert (project / ".ai" / "instructions.md").read_text().strip() in agents_md
    assert (project / "CLAUDE.md").read_text() == CLAUDE_MD
    for base in (".claude/skills", ".agents/skills"):
        assert validate_skill(project / base / "example-python-service-requirements") == []
    manifest = json.loads((project / ".ai" / SYNC_MANIFEST).read_text())
    assert set(manifest["files"]) == {
        "AGENTS.md",
        "CLAUDE.md",
        ".claude/skills/example-python-service-requirements/SKILL.md",
        ".agents/skills/example-python-service-requirements/SKILL.md",
    }
    again = _sync(project)
    assert {a for a, _ in again.actions} == {"unchanged"}


def test_source_edit_updates_and_hand_edit_is_protected(project: Path) -> None:
    _init(project)
    _sync(project)
    with (project / ".ai" / "instructions.md").open("a") as fh:
        fh.write("- Use Decimal for money.\n")
    plan = _sync(project)
    assert ("update", "AGENTS.md") in plan.actions
    assert "Use Decimal for money." in (project / "AGENTS.md").read_text()
    with (project / "AGENTS.md").open("a") as fh:
        fh.write("hand edit\n")
    with (project / ".ai" / "instructions.md").open("a") as fh:
        fh.write("- another rule\n")
    plan = _sync(project)
    assert not plan.applied and any("edited by hand" in c for c in plan.conflicts)
    assert (project / "AGENTS.md").read_text().endswith("hand edit\n")


def test_existing_unmanaged_files_are_not_overwritten(project: Path) -> None:
    _init(project)
    (project / "AGENTS.md").write_text("team's own instructions")
    plan = _sync(project)
    assert not plan.applied and any("not managed" in c for c in plan.conflicts)
    assert (project / "AGENTS.md").read_text() == "team's own instructions"


def test_existing_claude_md_is_left_alone_with_advice(project: Path) -> None:
    _init(project)
    (project / "CLAUDE.md").write_text("# our Claude notes\n")
    plan = _sync(project)
    assert plan.applied
    assert (project / "CLAUDE.md").read_text() == "# our Claude notes\n"
    assert any("@AGENTS.md" in n for n in plan.notes)


def test_removed_skill_is_cleaned_up_only_if_unchanged(project: Path) -> None:
    _init(project)
    _sync(project)
    name = "example-python-service-requirements"
    (project / ".agents" / "skills" / name / "SKILL.md").write_text("edited copy")
    for f in (project / ".ai" / "skills" / name).iterdir():
        f.unlink()
    (project / ".ai" / "skills" / name).rmdir()
    plan = _sync(project)
    assert any("no longer generated but edited by hand" in c for c in plan.conflicts)
    (project / ".agents" / "skills" / name / "SKILL.md").unlink()
    plan = _sync(project)
    assert ("remove-stale", f".claude/skills/{name}/SKILL.md") in plan.actions
    assert not (project / ".claude" / "skills" / name / "SKILL.md").exists()


def test_invalid_skill_is_skipped_with_a_note(project: Path) -> None:
    _init(project)
    bad = project / ".ai" / "skills" / "Bad_Skill"
    bad.mkdir(parents=True)
    (bad / "SKILL.md").write_text("no frontmatter")
    plan = _sync(project)
    assert any("Bad_Skill" in n for n in plan.notes)
    assert not (project / ".claude" / "skills" / "Bad_Skill").exists()


def test_target_selection(project: Path) -> None:
    _init(project)
    _sync(project, targets=("agents",))
    assert (project / "AGENTS.md").exists() and (project / ".agents" / "skills").exists()
    assert not (project / "CLAUDE.md").exists() and not (project / ".claude").exists()
    with pytest.raises(ArchonixError, match="unknown target"):
        sync(project, targets=("vscode",))


@posix_only
def test_sync_refuses_symlinked_outputs_and_tampered_manifest(
    project: Path, tmp_path: Path
) -> None:
    _init(project)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (project / ".claude").mkdir()
    (project / ".claude" / "skills").symlink_to(elsewhere, target_is_directory=True)
    plan = _sync(project)
    assert not plan.applied and list(elsewhere.iterdir()) == []
    (project / ".claude" / "skills").unlink()
    victim = tmp_path / "victim.txt"
    victim.write_text("important")
    (project / ".ai" / SYNC_MANIFEST).write_text(json.dumps({"files": {"../victim.txt": "0" * 64}}))
    plan = _sync(project)
    assert any("unsafe" in c for c in plan.conflicts)
    assert victim.read_text() == "important"


def test_cli_exit_codes(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = str(project)
    assert main(["agents", "init", root]) == 0 and not (project / ".ai").exists()
    assert main(["agents", "init", root, "--apply"]) == 3
    assert main(["agents", "init", root, "--apply", "--allow-source-writes"]) == 0
    assert main(["agents", "sync", root, "--check"]) == 1  # outputs missing
    assert main(["agents", "sync", root, "--apply", "--allow-source-writes"]) == 0
    assert main(["agents", "sync", root, "--check"]) == 0
    (project / "AGENTS.md").write_text("hand edit")
    assert main(["agents", "sync", root, "--apply", "--allow-source-writes"]) == 3
    assert main(["agents", "sync", root, "--check"]) == 1
    capsys.readouterr()
