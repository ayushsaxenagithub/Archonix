"""Adapter interface: how a check is invoked, when it applies, and how output is read."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..policy import Requirements
from ..runner import RunResult

# Capability status labels used in documentation and `archonix check list`.
STATUS_TESTED_REAL = "implemented; tested with real tool and fixtures"
STATUS_TESTED_FIXTURES = "implemented; tested with fixtures only (real tool not verified here)"


@dataclass
class Context:
    root: Path
    artifact_dir: Path
    excludes: list[str]
    extra_args: list[str] = field(default_factory=list)
    tool_version: str | None = None


@dataclass
class ParseOutcome:
    outcome: str  # clean | findings | tests-failed | tool-error | parse-error
    detail: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    test_totals: dict[str, int | None] | None = None
    limitations: list[str] = field(default_factory=list)
    # Scan completeness: True = the tool reported analysing every target, False = it
    # reported targets it could not analyse, None = the tool does not say.
    complete: bool | None = None
    coverage_detail: str | None = None


class Adapter:
    id: str = ""
    tool: str = ""
    executable: str = ""
    version_args: tuple[str, ...] = ("--version",)
    category: str = ""
    description: str = ""
    requires: Requirements = Requirements()
    status: str = STATUS_TESTED_FIXTURES
    exit_codes: dict[int, str] = {}
    # Extra environment variables for this tool's process only (never the caller's).
    env: dict[str, str] = {}
    notes: str = ""

    def applies(self, inventory: dict[str, Any], root: Path) -> tuple[bool, str]:
        raise NotImplementedError

    def argv(self, ctx: Context) -> list[str]:
        raise NotImplementedError

    def interpret(self, result: RunResult, ctx: Context) -> ParseOutcome:
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "executable": self.executable,
            "category": self.category,
            "description": self.description,
            "requires": self.requires.as_dict(),
            "status": self.status,
            "exit_codes": {str(k): v for k, v in self.exit_codes.items()},
            "env": dict(self.env),
            "notes": self.notes,
        }


def relpath(path: str, root: Path) -> str:
    p = Path(path)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix().removeprefix("./")


def load_json_output(text: str, truncated: bool) -> tuple[Any, str | None]:
    """Parse tool JSON, reporting truncation and malformed output distinctly."""
    if truncated:
        return None, "output exceeded max_output_bytes and was truncated; not parsed"
    if not text.strip():
        return None, "tool produced no output"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"output is not valid JSON ({exc.msg} at line {exc.lineno})"


def unexpected_exit(result: RunResult, known: dict[int, str]) -> ParseOutcome:
    meaning = (
        known.get(result.exit_code, "undocumented exit code")
        if result.exit_code is not None
        else "no exit code"
    )
    return ParseOutcome("tool-error", f"exit code {result.exit_code}: {meaning}")


def has_python(inventory: dict[str, Any]) -> tuple[bool, str]:
    if any("python" in p["ecosystems"] for p in inventory["projects"]) or any(
        lang["name"] == "Python" for lang in inventory["languages"]
    ):
        return True, "Python sources or manifests detected"
    return False, "no Python sources or manifests detected"
