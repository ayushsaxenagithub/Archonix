"""Documentation must match the CLI, and shipped schemas/examples must validate."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import tomllib
from pathlib import Path

import pytest
from conftest import REPO_ROOT
from jsonschema import Draft202012Validator

import archonix
from archonix.cli import build_parser, main
from archonix.schemas import schema_names, validate

DOC_FILES = sorted(
    [
        REPO_ROOT / "README.md",
        REPO_ROOT / "CONTRIBUTING.md",
        REPO_ROOT / "AGENTS.md",
        *(REPO_ROOT / "docs").rglob("*.md"),
        *(REPO_ROOT / "skills").rglob("*.md"),
        *(REPO_ROOT / "adapters").rglob("*.md"),
        REPO_ROOT / "examples" / "README.md",
    ]
)


def documented_commands() -> list[tuple[str, str]]:
    found = []
    for path in DOC_FILES:
        text = path.read_text(encoding="utf-8").replace("\\\n", " ")
        candidates = re.findall(r"^\s*(archonix [^\n#|]+)", text, flags=re.MULTILINE)
        candidates += re.findall(r"`(archonix [^`]+)`", text)
        for cmd in candidates:
            cmd = cmd.strip().rstrip("`")
            if "…" in cmd or "..." in cmd or "<" in cmd or "[" in cmd:
                continue  # synopsis lines with placeholders are checked separately
            found.append((str(path.relative_to(REPO_ROOT)), cmd))
    return found


COMMANDS = documented_commands()


def test_docs_contain_commands() -> None:
    assert len(COMMANDS) > 40


@pytest.mark.parametrize("where, command", COMMANDS, ids=[f"{w}:{c[:50]}" for w, c in COMMANDS])
def test_documented_command_parses(where: str, command: str) -> None:
    argv = shlex.split(command)[1:]
    parser = build_parser()
    names = _subcommands(parser)
    if " ".join(argv) in {n for full in names for n in _prefixes(full)}:
        return  # a bare command name mentioned in prose
    try:
        parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code not in (0, None):  # --help / --version exit 0
            pytest.fail(f"{where}: `{command}` does not parse")


def _subcommands(parser: argparse.ArgumentParser, prefix: str = "") -> list[str]:
    out = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                full = f"{prefix} {name}".strip()
                nested = _subcommands(sub, full)
                out += nested or [full]
    return out


def _prefixes(full: str) -> list[str]:
    parts = full.split()
    return [" ".join(parts[: i + 1]) for i in range(len(parts))]


def test_every_command_is_documented_in_cli_reference() -> None:
    cli_md = (REPO_ROOT / "docs" / "cli.md").read_text()
    missing = [c for c in _subcommands(build_parser()) if f"archonix {c}" not in cli_md]
    assert not missing, f"undocumented commands: {missing}"


def test_schemas_are_valid_draft_2020_12() -> None:
    from archonix.resources import schemas_dir

    for name in schema_names():
        schema = json.loads((schemas_dir() / f"{name}.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        assert schema["$id"] == f"urn:archonix:schema:{name}:{archonix.SCHEMA_VERSION}"


@pytest.mark.parametrize(
    "path",
    sorted((REPO_ROOT / "examples").rglob("*.json")),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_example_json_documents_validate_and_are_labelled(path: Path) -> None:
    doc = json.loads(path.read_text())
    if not isinstance(doc, dict) or "kind" not in doc:
        pytest.skip("not an Archonix document (example project file)")
    validate(doc)
    assert doc.get("example") is True, "example documents must be labelled as examples"


def test_example_markdown_reports_are_labelled() -> None:
    for name in ("report.md", "readiness.md", "perf.md"):
        assert "EXAMPLE" in (REPO_ROOT / "examples" / "reports" / name).read_text().splitlines()[0]


def test_example_reports_contain_no_local_paths() -> None:
    for path in (REPO_ROOT / "examples" / "reports").iterdir():
        text = path.read_text()
        assert "/Users/" not in text and "/home/" not in text and "/private/" not in text, path


def test_version_is_consistent() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]
    assert project["version"] == archonix.__version__


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--version"])
    assert capsys.readouterr().out.strip() == f"archonix {archonix.__version__}"
