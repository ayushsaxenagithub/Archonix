"""Locate bundled skill content (SKILL.md, references, templates, schemas).

The skill directory is the single source of truth. In a wheel it is bundled at
``archonix/_bundled/skills/archonix``; in a source checkout it is ``skills/archonix``.
"""

from __future__ import annotations

from pathlib import Path

from .errors import ArchonixError

_PKG_DIR = Path(__file__).resolve().parent


def skill_root() -> Path:
    candidates = [
        _PKG_DIR / "_bundled" / "skills" / "archonix",
        _PKG_DIR.parent.parent / "skills" / "archonix",
    ]
    for candidate in candidates:
        if (candidate / "SKILL.md").is_file():
            return candidate
    raise ArchonixError("bundled Archonix skill content not found; the installation is incomplete")


def schemas_dir() -> Path:
    return skill_root() / "schemas"


def templates_dir() -> Path:
    return skill_root() / "templates"
