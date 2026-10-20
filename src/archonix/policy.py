"""Execution modes, independent permission controls, and write boundaries.

Modes are workflow *defaults*, not isolation. The CLI enforces these controls for the
operations it performs itself (which checks it launches, where it writes). It cannot
constrain what a launched tool does once running, and it cannot constrain the host
assistant.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .errors import PolicyError

MODES = ("discovery", "implementation", "audit")


@dataclass
class Permissions:
    source_writes: bool = False  # write files inside the repository outside the artifact dir
    artifact_writes: bool = False  # write reports into an explicitly selected location
    repo_code: bool = False  # run tests/builds/plugins that execute repository code
    external_tools: bool = False  # launch installed tools (scanners, linters, git)
    network: bool = False  # checks or measurements that use the network
    dependency_install: bool = False  # install packages (no built-in check does this)
    shared_environment: bool = False  # touch shared databases/services
    destructive: bool = False  # delete or overwrite files outside Archonix-managed state

    @classmethod
    def for_mode(cls, mode: str) -> Permissions:
        if mode == "discovery":
            return cls(artifact_writes=True)
        if mode == "audit":
            return cls(artifact_writes=True, external_tools=True)
        if mode == "implementation":
            return cls(
                source_writes=True, artifact_writes=True, external_tools=True, repo_code=True
            )
        raise ValueError(mode)

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)


PERMISSION_NAMES = tuple(f.name for f in fields(Permissions))


@dataclass(frozen=True)
class Requirements:
    external_tool: bool = True
    repo_code: bool = False
    network: bool = False
    writes_cache: bool = False

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)


def blocking_reasons(req: Requirements, perms: Permissions) -> list[str]:
    reasons = []
    if req.external_tool and not perms.external_tools:
        reasons.append(
            "requires external tool execution (enable with --allow-tools or --mode audit)"
        )
    if req.repo_code and not perms.repo_code:
        reasons.append(
            "executes repository code (enable with --allow-repo-code only for trusted repositories)"
        )
    if req.network and not perms.network:
        reasons.append("uses the network (enable with --allow-network)")
    return reasons


class WriteGuard:
    """Permit writes only beneath explicitly selected directories.

    Paths are resolved (following symlinks) before the containment check so a symlink
    inside the selected directory cannot redirect a write elsewhere.
    """

    def __init__(self, allowed_roots: list[Path], *, overwrite: bool = False) -> None:
        self.allowed_roots = [p.resolve() for p in allowed_roots]
        self.overwrite = overwrite

    def check(self, target: Path) -> Path:
        resolved = target.resolve()
        if not any(resolved.is_relative_to(root) for root in self.allowed_roots):
            allowed = ", ".join(str(r) for r in self.allowed_roots) or "<none>"
            raise PolicyError(
                f"refusing to write {target}: outside the allowed locations ({allowed})"
            )
        if resolved.exists() and not self.overwrite:
            raise PolicyError(f"refusing to overwrite existing file {target}")
        return resolved

    def write_text(self, target: Path, content: str) -> Path:
        resolved = self.check(target)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        # Re-check after mkdir in case a parent was a symlink created concurrently.
        self.check(target)
        resolved.write_text(content, encoding="utf-8")
        return resolved
