"""Copy project document templates for the selected workflow into a user project.

Only the documents belonging to the requested set are generated, existing files are
never overwritten, and writing into the repository requires source-write permission.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .errors import ArchonixError, PolicyError
from .policy import WriteGuard
from .resources import templates_dir

# set name -> list of (template file, destination relative to project root)
TEMPLATE_SETS: dict[str, list[tuple[str, str]]] = {
    "discovery": [
        ("product-spec.md", "docs/product-spec.md"),
        ("user-journeys.md", "docs/user-journeys.md"),
        ("business-rules.md", "docs/business-rules.md"),
        ("acceptance-criteria.md", "docs/acceptance-criteria.md"),
        ("open-questions.md", "docs/open-questions.md"),
        ("requirements.json", "docs/requirements.json"),
    ],
    "change-note": [("change-note.md", "docs/changes/change-note.md")],
    "architecture": [
        ("technology-stack.md", "docs/technology-stack.md"),
        ("architecture.md", "docs/architecture.md"),
        ("data-flows.md", "docs/data-flows.md"),
        ("adr.md", "docs/architecture-decisions/0001-record-architecture-decisions.md"),
    ],
    "testing": [("testing-strategy.md", "docs/testing-strategy.md")],
    "security": [("security-findings.md", "docs/security-findings.md")],
    "dead-code": [("dead-code-analysis.md", "docs/dead-code-analysis.md")],
    "performance": [("performance-assessment.md", "docs/performance-assessment.md")],
    "technical-debt": [("technical-debt.md", "docs/technical-debt.md")],
    "release": [("release-readiness.md", "docs/release-readiness.md")],
}


@dataclass
class DocsPlan:
    create: list[str] = field(default_factory=list)
    exists: list[str] = field(default_factory=list)
    written: bool = False


def init_docs(
    root: Path, template_set: str, *, project: str, allow_source_writes: bool, apply: bool
) -> DocsPlan:
    if template_set not in TEMPLATE_SETS:
        raise ArchonixError(
            f"unknown template set {template_set!r}; choose from {', '.join(TEMPLATE_SETS)}"
        )
    root = root.resolve()
    plan = DocsPlan()
    for _, dest in TEMPLATE_SETS[template_set]:
        (plan.exists if (root / dest).exists() else plan.create).append(dest)
    if not apply:
        return plan
    if not allow_source_writes:
        raise PolicyError(
            "writing documents into the repository is a source modification; "
            "re-run with --allow-source-writes"
        )
    guard = WriteGuard([root / "docs"])
    today = datetime.now(UTC).date().isoformat()
    for template, dest in TEMPLATE_SETS[template_set]:
        if dest not in plan.create:
            continue
        text = (templates_dir() / template).read_text(encoding="utf-8")
        text = text.replace("{{project}}", project).replace("{{date}}", today)
        guard.write_text(root / dest, text)
    plan.written = True
    return plan
