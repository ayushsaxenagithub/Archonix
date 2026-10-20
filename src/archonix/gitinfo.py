"""Repository revision metadata.

The revision and branch are read directly from ``.git`` files, so no git process (and
no repository-configured hook or fsmonitor) runs. Working-tree dirtiness can only be
determined by running ``git status``; that is done only when external tools are
permitted, with fsmonitor and untracked-cache features disabled. Otherwise it is
reported as unknown (null). A non-Git directory never gets a fabricated revision.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from .runner import build_env, run

_SHA = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")


def _git_dir(root: Path) -> Path | None:
    for candidate in (root, *root.parents):
        dot = candidate / ".git"
        if dot.is_dir():
            return dot
        if dot.is_file():  # worktree or submodule: "gitdir: <path>"
            text = dot.read_text(encoding="utf-8", errors="replace").strip()
            if text.startswith("gitdir:"):
                target = Path(text.split(":", 1)[1].strip())
                return target if target.is_absolute() else (candidate / target).resolve()
    return None


def _resolve_ref(git_dir: Path, ref: str) -> str | None:
    common = git_dir
    commondir = git_dir / "commondir"
    if commondir.is_file():
        common = (git_dir / commondir.read_text().strip()).resolve()
    for base in (git_dir, common):
        ref_file = base / ref
        if ref_file.is_file():
            value = ref_file.read_text(encoding="utf-8", errors="replace").strip()
            return value if _SHA.match(value) else None
    packed = common / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref and _SHA.match(parts[0]):
                return parts[0]
    return None


def repository_info(
    root: Path, *, allow_git_process: bool, timeout: float = 20.0
) -> dict[str, Any]:
    git_dir = _git_dir(root)
    if git_dir is None:
        return {
            "vcs": "none",
            "revision": None,
            "branch": None,
            "dirty": None,
            "notes": ["not a Git repository; no revision recorded"],
        }
    notes: list[str] = []
    revision = branch = None
    head_file = git_dir / "HEAD"
    head = (
        head_file.read_text(encoding="utf-8", errors="replace").strip()
        if head_file.is_file()
        else ""
    )
    if head.startswith("ref:"):
        ref = head.split(":", 1)[1].strip()
        branch = ref.removeprefix("refs/heads/")
        revision = _resolve_ref(git_dir, ref)
        if revision is None:
            notes.append(f"branch {branch!r} has no commits yet")
    elif _SHA.match(head):
        revision = head
        notes.append("detached HEAD")

    dirty: bool | None = None
    if not allow_git_process:
        notes.append("working-tree status unknown: running git requires external tool permission")
    elif shutil.which("git") is None:
        notes.append("working-tree status unknown: git is not installed")
    else:
        result = run(
            [
                "git",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.untrackedCache=false",
                "status",
                "--porcelain",
                "--ignore-submodules=dirty",
            ],
            root,
            env=build_env(extra={"GIT_OPTIONAL_LOCKS": "0"}),
            timeout=timeout,
            max_output_bytes=1_000_000,
        )
        if result.status == "completed" and result.exit_code == 0:
            dirty = bool(result.stdout.text().strip())
        else:
            notes.append(f"working-tree status unknown: git status failed ({result.status})")
    return {"vcs": "git", "revision": revision, "branch": branch, "dirty": dirty, "notes": notes}
