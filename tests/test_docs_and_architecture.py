from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import REPO_ROOT

from archonix.architecture import inventory_diagram, python_import_graph
from archonix.cli import main
from archonix.config import load_settings
from archonix.docsinit import TEMPLATE_SETS, init_docs
from archonix.errors import PolicyError
from archonix.inventory import build_inventory
from archonix.resources import templates_dir


def test_every_template_exists() -> None:
    for items in TEMPLATE_SETS.values():
        for template, _ in items:
            assert (templates_dir() / template).is_file(), template


def test_docs_init_gates_and_scope(make_repo: Callable[..., Path]) -> None:
    root = make_repo({"docs/product-spec.md": "existing, keep me"})
    plan = init_docs(root, "discovery", project="demo", allow_source_writes=False, apply=False)
    assert "docs/product-spec.md" in plan.exists and "docs/user-journeys.md" in plan.create
    assert not (root / "docs/user-journeys.md").exists()
    with pytest.raises(PolicyError):
        init_docs(root, "discovery", project="demo", allow_source_writes=False, apply=True)
    init_docs(root, "discovery", project="demo", allow_source_writes=True, apply=True)
    assert (root / "docs/product-spec.md").read_text() == "existing, keep me"
    assert "# demo — User journeys" in (root / "docs/user-journeys.md").read_text()
    assert not (root / "docs/security-findings.md").exists()  # other sets untouched
    assert main(["requirements", "validate", str(root / "docs/requirements.json")]) == 0


def test_inventory_diagram_labels_inferred_edges() -> None:
    root = REPO_ROOT / "examples" / "mixed-monorepo"
    mermaid, evidence = inventory_diagram(build_inventory(root, load_settings(root)))
    assert mermaid.startswith("flowchart LR")
    assert '-. "sqlalchemy (inferred)" .->' in mermaid
    statuses = {e["status"] for e in evidence}
    assert "inferred" in statuses and "verified" in statuses


def test_python_import_graph_verified_and_unknown(make_repo: Callable[..., Path]) -> None:
    root = make_repo(
        {
            "pkg/__init__.py": "",
            "pkg/api/__init__.py": "from ..core import models\n",
            "pkg/core/__init__.py": "",
            "pkg/core/models.py": (
                "import importlib\nplugin = importlib.import_module('pkg.plugins')\n"
            ),
            "pkg/broken.py": "def (:\n",
        }
    )
    mermaid, evidence, limitations = python_import_graph(root / "pkg")
    assert "m_pkg_api --> m_pkg_core" in mermaid
    statuses = {e["status"] for e in evidence}
    assert statuses == {"verified (static import)", "unknown"}
    assert any("not parsed" in x for x in limitations)


def test_cli_architecture_refuses_outside_package(make_repo: Callable[..., Path]) -> None:
    root = make_repo({"a.py": ""})
    assert main(["architecture", "diagram", str(root), "--python-package", "../.."]) == 3
