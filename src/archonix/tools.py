"""Detect which supported external tools are installed, optionally with versions.

``which`` lookups are passive. Version detection launches each tool with its version
flag, which is external tool execution and is only done when requested.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runner import build_env, run

_VERSION = re.compile(r"(\d+\.\d+(?:\.\d+)?(?:[-+.][0-9A-Za-z.]+)?)")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    executable: str
    version_args: tuple[str, ...]
    purpose: str


KNOWN_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec("git", "git", ("--version",), "repository metadata"),
    ToolSpec("python", "python3", ("--version",), "Python runtime"),
    ToolSpec("node", "node", ("--version",), "JavaScript runtime"),
    ToolSpec("npm", "npm", ("--version",), "JavaScript package manager / npm audit"),
    ToolSpec("ruff", "ruff", ("--version",), "Python lint"),
    ToolSpec("mypy", "mypy", ("--version",), "Python type checking"),
    ToolSpec("pytest", "pytest", ("--version",), "Python tests"),
    ToolSpec("bandit", "bandit", ("--version",), "Python security lint"),
    ToolSpec("vulture", "vulture", ("--version",), "Python dead-code candidates"),
    ToolSpec("deptry", "deptry", ("--version",), "Python dependency hygiene"),
    ToolSpec("pip-audit", "pip-audit", ("--version",), "Python dependency vulnerabilities"),
    ToolSpec("semgrep", "semgrep", ("--version",), "multi-language static analysis"),
    ToolSpec("gitleaks", "gitleaks", ("version",), "secret scanning"),
    ToolSpec("trivy", "trivy", ("--version",), "vulnerability and misconfiguration scanning"),
    ToolSpec("osv-scanner", "osv-scanner", ("--version",), "dependency vulnerabilities"),
    ToolSpec("eslint", "eslint", ("--version",), "JavaScript/TypeScript lint"),
    ToolSpec("tsc", "tsc", ("--version",), "TypeScript type checking"),
    ToolSpec("knip", "knip", ("--version",), "JavaScript/TypeScript unused code"),
    ToolSpec("k6", "k6", ("version",), "load testing"),
    ToolSpec("locust", "locust", ("--version",), "load testing"),
    ToolSpec("zap", "zap.sh", ("-version",), "dynamic application scanning (authorized targets)"),
)


def parse_version(text: str) -> str | None:
    m = _VERSION.search(text)
    return m.group(1) if m else None


def tool_version(executable: str, args: tuple[str, ...], timeout: float = 15.0) -> str | None:
    # Run from a neutral directory so repository-local config is not picked up.
    result = run(
        [executable, *args],
        cwd=Path(tempfile.gettempdir()),
        env=build_env(),
        timeout=timeout,
        max_output_bytes=16384,
    )
    if result.status != "completed":
        return None
    return parse_version(result.stdout.text() + "\n" + result.stderr.text())


def detect_tools(*, versions: bool) -> list[dict[str, Any]]:
    out = []
    for spec in KNOWN_TOOLS:
        path = shutil.which(spec.executable)
        entry: dict[str, Any] = {
            "name": spec.name,
            "executable": spec.executable,
            "available": path is not None,
            "path": path,
            "version": None,
            "purpose": spec.purpose,
        }
        if path and versions:
            entry["version"] = tool_version(spec.executable, spec.version_args)
        out.append(entry)
    return out
