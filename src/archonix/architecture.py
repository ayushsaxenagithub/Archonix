"""Evidence-labelled architecture diagrams (Mermaid).

Two generators are provided:

* ``inventory_diagram`` — system context from the inventory. Project-to-service edges
  come from declared dependencies and are labelled *inferred*.
* ``python_import_graph`` — module dependencies from parsing Python files with ``ast``
  (no import or execution). Static imports are *verified* edges; dynamic imports are
  listed as *unknown*.

Neither reconstructs full runtime architecture; agent-assisted diagram templates in the
skill cover the rest.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from .inventory import JS_DEPENDENCIES, PY_DEPENDENCIES

# Mermaid node shape delimiters per service category.
SERVICE_SHAPES = {
    "database": ("[(", ")]"),
    "cache": ("[(", ")]"),
    "queue": ("[/", "/]"),
    "integration": ("{{", "}}"),
    "auth": ("([", "])"),
}
CONTEXT_CATEGORIES = {"ci", "container", "infrastructure", "deployment"}


def _node_id(prefix: str, text: str) -> str:
    return prefix + "_" + re.sub(r"[^A-Za-z0-9]", "_", text).strip("_")[:40]


def _label(text: str) -> str:
    return text.replace('"', "'")


def inventory_diagram(inv: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    """Return (mermaid_source, evidence_rows)."""
    lines = ["flowchart LR"]
    evidence: list[dict[str, str]] = []
    services: dict[str, str] = {}
    lines.append('  subgraph repo["Repository"]')
    for proj in inv["projects"]:
        pid = _node_id("proj", proj["path"] or "root")
        table = JS_DEPENDENCIES if "javascript" in proj["ecosystems"] else PY_DEPENDENCIES
        frameworks = sorted(
            {
                table[d][1]
                for d in proj.get("dependencies", [])
                if d in table and table[d][0] == "framework"
            }
        )
        title = proj.get("name") or proj["path"]
        detail = ", ".join(proj["ecosystems"]) + (
            f" · {', '.join(frameworks)}" if frameworks else ""
        )
        lines.append(f'    {pid}["{_label(title)}<br/><small>{_label(detail)}</small>"]')
        evidence.append(
            {
                "element": title,
                "relationship": "project",
                "status": "verified",
                "evidence": ", ".join(proj["manifests"]),
            }
        )
    lines.append("  end")
    edges = []
    for proj in inv["projects"]:
        pid = _node_id("proj", proj["path"] or "root")
        table = JS_DEPENDENCIES if "javascript" in proj["ecosystems"] else PY_DEPENDENCIES
        for dep in proj.get("dependencies", []):
            hit = table.get(dep)
            if not hit or hit[0] not in SERVICE_SHAPES:
                continue
            category, name = hit
            sid = services.get(name)
            if sid is None:
                sid = services[name] = _node_id("svc", name)
                opening, closing = SERVICE_SHAPES[category]
                lines.append(f'  {sid}{opening}"{_label(name)}"{closing}')
            edges.append(f'  {pid} -. "{_label(dep)} (inferred)" .-> {sid}')
            evidence.append(
                {
                    "element": f"{proj['path']} -> {name}",
                    "relationship": "uses",
                    "status": "inferred",
                    "evidence": f"declared dependency {dep!r} in {', '.join(proj['manifests'])}",
                }
            )
    lines += edges
    for d in inv["detections"]:
        if d["category"] in CONTEXT_CATEGORIES:
            nid = _node_id("ctx", d["category"] + d["name"])
            lines.append(f'  {nid}["{_label(d["name"])}<br/><small>{d["category"]}</small>"]')
            lines.append(f"  {nid} --- repo")
            evidence.append(
                {
                    "element": d["name"],
                    "relationship": d["category"] + " configuration",
                    "status": "verified (file present)",
                    "evidence": "; ".join(d["evidence"][:3]),
                }
            )
    lines += ["  classDef inferred stroke-dasharray: 4 3;"]
    for sid in services.values():
        lines.append(f"  class {sid} inferred;")
    return "\n".join(lines) + "\n", evidence


def _module_name(pkg_root: Path, file: Path) -> str:
    rel = file.relative_to(pkg_root.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def python_import_graph(
    package_dir: Path, depth: int = 2
) -> tuple[str, list[dict[str, str]], list[str]]:
    """Return (mermaid_source, evidence_rows, limitations) for a Python package directory."""
    package_dir = package_dir.resolve()
    if not (package_dir / "__init__.py").is_file():
        raise ValueError(f"{package_dir} is not a Python package (no __init__.py)")
    top = package_dir.name
    modules: dict[str, Path] = {}
    for file in sorted(package_dir.rglob("*.py")):
        if any(part.startswith(".") or part == "__pycache__" for part in file.parts):
            continue
        if file.is_symlink():
            continue
        modules[_module_name(package_dir, file)] = file

    def collapse(name: str) -> str:
        return ".".join(name.split(".")[:depth])

    edges: dict[tuple[str, str], str] = {}
    unknown: list[dict[str, str]] = []
    limitations = []
    for mod, file in modules.items():
        try:
            tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"), filename=str(file))
        except SyntaxError as exc:
            limitations.append(f"{file.relative_to(package_dir.parent)}: not parsed ({exc.msg})")
            continue
        is_pkg = file.name == "__init__.py"
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = mod.split(".") if is_pkg else mod.split(".")[:-1]
                    base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                    prefix = ".".join(base)
                    targets = [f"{prefix}.{node.module}" if node.module else prefix]
                    if not node.module:
                        targets = [f"{prefix}.{a.name}" for a in node.names]
                elif node.module:
                    targets = [node.module]
            elif isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                if name in {"import_module", "__import__"}:
                    unknown.append(
                        {
                            "element": f"{mod} -> ?",
                            "relationship": "dynamic import",
                            "status": "unknown",
                            "evidence": f"{file.relative_to(package_dir.parent)}:{node.lineno}",
                        }
                    )
            for target in targets:
                if target == top or target.startswith(top + "."):
                    src, dst = collapse(mod), collapse(target)
                    if src != dst:
                        line = getattr(node, "lineno", 0)
                        edges.setdefault(
                            (src, dst), f"{file.relative_to(package_dir.parent)}:{line}"
                        )
    nodes = sorted({collapse(m) for m in modules})
    lines = ["flowchart TD"]
    for n in nodes:
        lines.append(f'  {_node_id("m", n)}["{n}"]')
    for (src, dst), _ in sorted(edges.items()):
        lines.append(f"  {_node_id('m', src)} --> {_node_id('m', dst)}")
    evidence = [
        {
            "element": f"{s} -> {d}",
            "relationship": "imports",
            "status": "verified (static import)",
            "evidence": ev,
        }
        for (s, d), ev in sorted(edges.items())
    ] + unknown
    limitations.append(
        "Static imports only; runtime registration, plugins, dependency injection "
        "and imports inside strings are not visible."
    )
    if unknown:
        limitations.append(
            f"{len(unknown)} dynamic import call(s) found; their targets are unknown."
        )
    return "\n".join(lines) + "\n", evidence, limitations


def render_diagram_markdown(
    title: str, mermaid: str, evidence: list[dict[str, str]], limitations: list[str]
) -> str:
    out = [
        f"# {title}",
        "",
        "```mermaid",
        mermaid.rstrip(),
        "```",
        "",
        "Legend: solid edges are verified from files; dashed edges are inferred from declared "
        "dependencies; items marked unknown could not be resolved statically.",
        "",
        "## Evidence",
        "",
        "| Element | Relationship | Status | Evidence |",
        "|---|---|---|---|",
    ]
    for row in evidence:
        out.append(
            f"| {row['element']} | {row['relationship']} | {row['status']} | {row['evidence']} |"
        )
    out += ["", "## Limitations", ""] + [f"- {x}" for x in limitations]
    return "\n".join(out) + "\n"
