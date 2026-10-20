from __future__ import annotations

from pathlib import Path

import pytest

from archonix.install import (
    MANIFEST,
    install,
    parse_frontmatter,
    target_dir,
    uninstall,
    validate_skill,
)
from archonix.resources import skill_root


def test_bundled_skill_is_valid() -> None:
    assert validate_skill(skill_root()) == []


@pytest.mark.parametrize(
    "assistant, scope, expected",
    [
        ("claude", "user", "home/.claude/skills/archonix"),
        ("codex", "user", "home/.agents/skills/archonix"),
        ("cursor", "user", "home/.cursor/skills/archonix"),
        ("claude", "project", "proj/.claude/skills/archonix"),
        ("codex", "project", "proj/.agents/skills/archonix"),
        ("cursor", "project", "proj/.cursor/skills/archonix"),
    ],
)
def test_target_locations(tmp_path: Path, assistant: str, scope: str, expected: str) -> None:
    got = target_dir(assistant, scope, home=tmp_path / "home", project_dir=tmp_path / "proj")
    assert got == (tmp_path / expected).resolve() or got == tmp_path / expected


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    plan = install("claude", "user", home=tmp_path)
    assert not plan.applied and not plan.conflicts
    assert ("create", "SKILL.md") in plan.actions
    assert not (tmp_path / ".claude").exists()


def test_install_reinstall_and_uninstall(tmp_path: Path) -> None:
    plan = install("codex", "user", home=tmp_path, apply=True)
    target = plan.target
    assert plan.applied and (target / "SKILL.md").is_file() and (target / MANIFEST).is_file()
    assert validate_skill(target) == []
    again = install("codex", "user", home=tmp_path, apply=True)
    assert {a for a, _ in again.actions} == {"unchanged"}
    removed = uninstall("codex", "user", home=tmp_path, apply=True)
    assert removed.applied and not target.exists()
    assert (tmp_path / ".agents" / "skills").is_dir()  # parent directories are left alone


def test_existing_unmanaged_directory_is_a_conflict(tmp_path: Path) -> None:
    target = tmp_path / ".claude" / "skills" / "archonix"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("user's own skill")
    plan = install("claude", "user", home=tmp_path, apply=True)
    assert plan.conflicts and not plan.applied
    assert (target / "SKILL.md").read_text() == "user's own skill"
    assert uninstall("claude", "user", home=tmp_path, apply=True).conflicts
    assert (target / "SKILL.md").exists()


def test_user_modified_files_are_never_overwritten_or_deleted(tmp_path: Path) -> None:
    target = install("cursor", "user", home=tmp_path, apply=True).target
    (target / "references" / "security.md").write_text("my notes")
    (target / "my-extra.md").write_text("mine")
    upgrade = install("cursor", "user", home=tmp_path, apply=True)
    assert any("modified since installation" in c for c in upgrade.conflicts)
    removed = uninstall("cursor", "user", home=tmp_path, apply=True)
    assert ("keep-modified", "references/security.md") in removed.actions
    assert (target / "references" / "security.md").read_text() == "my notes"
    assert (target / "my-extra.md").exists()
    assert not (target / "SKILL.md").exists()


def test_stale_files_are_removed_on_upgrade(tmp_path: Path) -> None:
    source = tmp_path / "src-skill"
    source.mkdir()
    (source / "SKILL.md").write_text(skill_root().joinpath("SKILL.md").read_text())
    (source / "old.md").write_text("old")
    home = tmp_path / "home"
    install("claude", "user", home=home, source=source, apply=True)
    (source / "old.md").unlink()
    plan = install("claude", "user", home=home, source=source, apply=True)
    assert ("remove-stale", "old.md") in plan.actions
    assert not (plan.target / "old.md").exists()


def test_project_scope_requires_project_dir(tmp_path: Path) -> None:
    from archonix.errors import ArchonixError

    with pytest.raises(ArchonixError):
        install("claude", "project", home=tmp_path)


def test_frontmatter_validation(tmp_path: Path) -> None:
    skill = tmp_path / "Bad_Name"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: Bad_Name\ndescription:\n---\n[x](references/missing.md)\n"
    )
    problems = validate_skill(skill)
    assert any("lowercase" in p for p in problems)
    assert any("description is required" in p for p in problems)
    assert any("missing file references/missing.md" in p for p in problems)
    with pytest.raises(Exception, match="line 1"):
        parse_frontmatter("# no frontmatter")
