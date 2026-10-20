from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import PY_REPO, REPO_ROOT

from archonix.config import load_settings
from archonix.inventory import build_inventory
from archonix.schemas import validate


def inv(root: Path, **kw: Any) -> dict[str, Any]:
    settings = load_settings(root)
    for k, v in kw.items():
        setattr(settings, k, v)
    result = build_inventory(root, settings)
    validate(result, "inventory")
    return result


def names(result: dict[str, Any], category: str) -> set[str]:
    return {d["name"] for d in result["detections"] if d["category"] == category}


def test_python_detection_with_evidence(make_repo: Callable[..., Path]) -> None:
    result = inv(make_repo({**PY_REPO, "requirements-dev.txt": "ruff==0.6  # lint\n-r base.txt\n"}))
    assert names(result, "framework") == {"FastAPI"}
    assert "PostgreSQL client" in names(result, "database")
    assert {"pytest"} <= names(result, "test")
    assert "Ruff" in names(result, "lint")
    fastapi = next(d for d in result["detections"] if d["name"] == "FastAPI")
    assert fastapi["basis"] == "declared-dependency"
    assert fastapi["evidence"] == ["pyproject.toml: dependency 'fastapi'"]
    assert result["projects"][0]["ecosystems"] == ["python"]


def test_javascript_typescript_detection(make_repo: Callable[..., Path]) -> None:
    root = make_repo(
        {
            "package.json": '{"name": "web", "dependencies": {"next": "1", "react": "1"},'
            ' "devDependencies": {"vitest": "1", "typescript": "5"}}',
            "pnpm-lock.yaml": "lockfileVersion: 9\n",
            "tsconfig.json": "{}",
            "src/a.ts": "export const a = 1;\n",
            "src/b.tsx": "export const B = () => null;\n",
        }
    )
    result = inv(root)
    assert names(result, "framework") == {"Next.js", "React"}
    assert "pnpm" in names(result, "package-manager")
    assert "Vitest" in names(result, "test")
    assert {lang["name"] for lang in result["languages"]} == {"TypeScript"}


def test_mixed_monorepo_example() -> None:
    result = inv(REPO_ROOT / "examples" / "mixed-monorepo")
    paths = {p["path"]: p["ecosystems"] for p in result["projects"]}
    assert paths == {".": ["javascript"], "apps/web": ["javascript"], "services/api": ["python"]}
    assert {"npm/yarn workspaces", "multiple projects"} <= names(result, "monorepo")
    assert {"FastAPI", "React"} <= names(result, "framework")


def test_ambiguous_repo_lists_both_ecosystems(make_repo: Callable[..., Path]) -> None:
    root = make_repo(
        {
            "setup.py": "raise SystemExit('must never run')\n",
            "package.json": '{"name": "tools"}',
            "README.md": "# ?\n",
        }
    )
    result = inv(root)
    assert result["projects"][0]["ecosystems"] == ["javascript", "python"]
    assert names(result, "framework") == set()


def test_inventory_never_executes_repository_code(
    make_repo: Callable[..., Path], tmp_path: Path
) -> None:
    marker = tmp_path / "executed"
    root = make_repo(
        {
            "setup.py": f"open({str(marker)!r}, 'w')\n",
            "conftest.py": f"open({str(marker)!r}, 'w')\n",
            "pyproject.toml": "[project]\nname='x'\n",
        }
    )
    inv(root)
    assert not marker.exists()


def test_non_git_directory_has_no_revision(make_repo: Callable[..., Path]) -> None:
    repo = inv(make_repo(PY_REPO))["repository"]
    assert repo == {
        "vcs": "none",
        "revision": None,
        "branch": None,
        "dirty": None,
        "notes": ["not a Git repository; no revision recorded"],
    }


def test_git_revision_read_without_running_git(make_repo: Callable[..., Path]) -> None:
    sha = "a" * 40
    root = make_repo(
        {**PY_REPO, ".git/HEAD": "ref: refs/heads/main\n", ".git/refs/heads/main": sha + "\n"}
    )
    repo = inv(root)["repository"]
    assert repo["vcs"] == "git" and repo["revision"] == sha and repo["branch"] == "main"
    assert repo["dirty"] is None  # discovery mode does not run git status


def test_packed_refs(make_repo: Callable[..., Path]) -> None:
    sha = "b" * 40
    root = make_repo(
        {
            ".git/HEAD": "ref: refs/heads/dev\n",
            ".git/packed-refs": f"# pack-refs\n{sha} refs/heads/dev\n",
        }
    )
    assert inv(root)["repository"]["revision"] == sha


def test_default_and_custom_exclusions(make_repo: Callable[..., Path]) -> None:
    root = make_repo(
        {
            **PY_REPO,
            "node_modules/pkg/package.json": '{"dependencies": {"express": "1"}}',
            ".venv/lib/x.py": "",
            "generated/big.py": "",
        }
    )
    result = inv(root, exclude=[*load_settings(root).exclude, "generated"])
    assert "node_modules/" in result["scan"]["excluded_dirs"]
    assert "generated/" in result["scan"]["excluded_dirs"]
    assert "Express" not in names(result, "framework")
    assert not any(m["path"].startswith("node_modules") for m in result["manifests"])


@pytest.mark.skipif(os.name != "posix", reason="symlinks")
def test_symlinks_are_not_followed(make_repo: Callable[..., Path], tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "package.json").write_text('{"dependencies": {"express": "1"}}')
    root = make_repo(PY_REPO)
    (root / "linked").symlink_to(outside, target_is_directory=True)
    (root / "linked-file.json").symlink_to(outside / "package.json")
    result = inv(root)
    assert set(result["scan"]["symlinks_skipped"]) == {"linked", "linked-file.json"}
    assert "Express" not in names(result, "framework")


def test_max_files_truncates_and_says_so(make_repo: Callable[..., Path]) -> None:
    root = make_repo({f"m/f{i}.py": "" for i in range(30)})
    result = inv(root, max_files=10)
    assert result["scan"]["truncated"] and result["scan"]["files_scanned"] == 10
    assert any("partial" in x for x in result["limitations"])


def test_large_and_malformed_manifests(make_repo: Callable[..., Path]) -> None:
    root = make_repo({"package.json": "{broken", "sub/pyproject.toml": "x" * 5000})
    result = inv(root, max_file_bytes=1000)
    errors = {m["path"]: m["parse_error"] for m in result["manifests"]}
    assert errors["package.json"].startswith("invalid JSON")
    assert "not parsed" in errors["sub/pyproject.toml"]
    assert result["scan"]["large_files"] == ["sub/pyproject.toml"]


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="permissions")
def test_unreadable_directory_is_recorded(make_repo: Callable[..., Path]) -> None:
    root = make_repo({**PY_REPO, "locked/a.py": ""})
    (root / "locked").chmod(0)
    try:
        result = inv(root)
    finally:
        (root / "locked").chmod(0o755)
    assert "locked" in result["scan"]["unreadable"]
