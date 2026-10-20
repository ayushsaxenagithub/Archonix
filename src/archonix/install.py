"""Install, verify and remove the Archonix skill for supported assistants.

Every install writes ``.archonix-manifest.json`` listing the files it created with
their SHA-256. Upgrades and removal touch only files whose content still matches the
manifest; anything the user edited, and any pre-existing directory without a manifest,
is reported as a conflict and left alone. All operations are dry runs unless
``apply=True``.

Discovery locations were checked against official documentation in October 2026
(see docs/assistants.md); assistants change, so re-verify when they update.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .errors import ArchonixError
from .resources import skill_root

SKILL_NAME = "archonix"
MANIFEST = ".archonix-manifest.json"
TARGETS: dict[str, dict[str, str]] = {
    "claude": {"user": "~/.claude/skills", "project": ".claude/skills"},
    "codex": {"user": "~/.agents/skills", "project": ".agents/skills"},
    "cursor": {"user": "~/.cursor/skills", "project": ".cursor/skills"},
}
IGNORED_NAMES = {"__pycache__", ".DS_Store", MANIFEST}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@dataclass
class InstallPlan:
    target: Path
    actions: list[tuple[str, str]] = field(default_factory=list)  # (action, relative path)
    conflicts: list[str] = field(default_factory=list)
    applied: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "target": str(self.target),
            "applied": self.applied,
            "actions": [{"action": a, "path": p} for a, p in self.actions],
            "conflicts": self.conflicts,
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def target_dir(assistant: str, scope: str, *, home: Path, project_dir: Path | None) -> Path:
    if assistant not in TARGETS:
        raise ArchonixError(f"unknown assistant {assistant!r}; supported: {', '.join(TARGETS)}")
    base = TARGETS[assistant][scope]
    if scope == "user":
        return home / base.removeprefix("~/") / SKILL_NAME
    if project_dir is None:
        raise ArchonixError("--project-dir is required for --scope project")
    return project_dir.resolve() / base / SKILL_NAME


def source_files(source: Path) -> dict[str, Path]:
    files = {}
    for path in sorted(source.rglob("*")):
        rel = path.relative_to(source)
        if any(part in IGNORED_NAMES for part in rel.parts) or not path.is_file():
            continue
        files[rel.as_posix()] = path
    return files


def _read_manifest(target: Path) -> dict[str, Any] | None:
    path = target / MANIFEST
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ArchonixError(f"{path} is corrupt; inspect it manually") from exc
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        raise ArchonixError(f"{path} is not an Archonix manifest")
    return data


def install(
    assistant: str,
    scope: str,
    *,
    home: Path,
    project_dir: Path | None = None,
    apply: bool = False,
    source: Path | None = None,
) -> InstallPlan:
    source = source or skill_root()
    target = target_dir(assistant, scope, home=home, project_dir=project_dir)
    plan = InstallPlan(target)
    new_files = source_files(source)
    manifest = _read_manifest(target) if target.exists() else None
    if target.exists() and manifest is None:
        plan.conflicts.append(
            f"{target} exists and was not installed by Archonix; refusing to "
            "modify it (move it aside or remove it yourself)"
        )
        return plan
    old: dict[str, str] = manifest["files"] if manifest else {}
    for rel, src in new_files.items():
        dest = target / rel
        if not dest.exists():
            plan.actions.append(("create", rel))
        elif rel not in old:
            plan.conflicts.append(f"{rel}: exists but is not managed by Archonix")
        elif _sha256(dest) != old[rel]:
            plan.conflicts.append(f"{rel}: modified since installation; not overwriting")
        elif _sha256(dest) == _sha256(src):
            plan.actions.append(("unchanged", rel))
        else:
            plan.actions.append(("update", rel))
    for rel, digest in old.items():
        if rel not in new_files:
            dest = target / rel
            if dest.is_file() and _sha256(dest) == digest:
                plan.actions.append(("remove-stale", rel))
            elif dest.exists():
                plan.conflicts.append(f"{rel}: no longer shipped but modified; leaving it")
    if plan.conflicts or not apply:
        return plan

    for action, rel in plan.actions:
        dest = target / rel
        if action in {"create", "update"}:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(new_files[rel], dest)
        elif action == "remove-stale":
            dest.unlink()
    _prune_empty(target)
    record = {
        "tool": "archonix",
        "version": __version__,
        "assistant": assistant,
        "scope": scope,
        "files": {rel: _sha256(target / rel) for rel in new_files},
    }
    (target / MANIFEST).write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    plan.applied = True
    return plan


def uninstall(
    assistant: str, scope: str, *, home: Path, project_dir: Path | None = None, apply: bool = False
) -> InstallPlan:
    target = target_dir(assistant, scope, home=home, project_dir=project_dir)
    plan = InstallPlan(target)
    if not target.exists():
        plan.conflicts.append(f"{target} does not exist; nothing to remove")
        return plan
    manifest = _read_manifest(target)
    if manifest is None:
        plan.conflicts.append(f"{target} has no Archonix manifest; refusing to delete anything")
        return plan
    for rel, digest in sorted(manifest["files"].items()):
        dest = target / rel
        if not dest.exists():
            continue
        if dest.is_file() and not dest.is_symlink() and _sha256(dest) == digest:
            plan.actions.append(("remove", rel))
        else:
            plan.actions.append(("keep-modified", rel))
    plan.actions.append(("remove", MANIFEST))
    if not apply:
        return plan
    for action, rel in plan.actions:
        if action == "remove":
            (target / rel).unlink(missing_ok=True)
    _prune_empty(target)
    if target.exists() and not any(target.iterdir()):
        target.rmdir()
    plan.applied = True
    return plan


def _prune_empty(root: Path) -> None:
    if not root.exists():
        return
    for directory in sorted(
        (p for p in root.rglob("*") if p.is_dir() and not p.is_symlink()),
        key=lambda p: len(p.parts),
        reverse=True,
    ):
        if not any(directory.iterdir()):
            directory.rmdir()


def parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ArchonixError("SKILL.md must start with '---' YAML frontmatter on line 1")
    data: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return data
        if not line.strip() or line.startswith((" ", "#")):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise ArchonixError(f"unparseable frontmatter line: {line!r}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        data[key.strip()] = value
    raise ArchonixError("SKILL.md frontmatter is not closed with '---'")


def validate_skill(skill_dir: Path) -> list[str]:
    """Return problems with a skill directory (empty list when valid)."""
    problems = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"{skill_md} not found"]
    text = skill_md.read_text(encoding="utf-8")
    try:
        meta = parse_frontmatter(text)
    except ArchonixError as exc:
        return [str(exc)]
    name = meta.get("name", "")
    desc = meta.get("description", "")
    if not NAME_RE.match(name) or len(name) > 64:
        problems.append(
            f"name {name!r} must be lowercase letters, digits and hyphens (<= 64 chars)"
        )
    if name != skill_dir.name:
        problems.append(f"name {name!r} must match the directory name {skill_dir.name!r}")
    if not desc:
        problems.append("description is required")
    elif len(desc) > 1024:
        problems.append(f"description is {len(desc)} characters; keep it within 1024")
    for link in re.findall(r"\]\(((?:references|templates|schemas)/[^)#\s]+)", text):
        if not (skill_dir / link).is_file():
            problems.append(f"SKILL.md links to missing file {link}")
    body_lines = len(text.splitlines())
    if body_lines > 500:
        problems.append(f"SKILL.md has {body_lines} lines; keep the entry point under 500")
    manifest = skill_dir / MANIFEST
    if manifest.is_file():
        data = _read_manifest(skill_dir) or {"files": {}}
        for rel, digest in data["files"].items():
            path = skill_dir / rel
            if not path.is_file():
                problems.append(f"installed file missing: {rel}")
            elif _sha256(path) != digest:
                problems.append(f"installed file modified: {rel} (informational)")
    return problems
