from __future__ import annotations

import json
import os
import stat
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def isolate_user_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never read the developer's real ~/.config/archonix during tests."""
    monkeypatch.setenv("ARCHONIX_USER_CONFIG", "none")
    monkeypatch.delenv("ARCHONIX_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("ARCHONIX_MAX_OUTPUT_BYTES", raising=False)


def write_tree(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content), encoding="utf-8")
    return root


@pytest.fixture
def make_repo(tmp_path: Path) -> Callable[..., Path]:
    def _make(files: dict[str, str], name: str = "repo") -> Path:
        return write_tree(tmp_path / name, files)

    return _make


@pytest.fixture
def fake_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Path]:
    """Create fake tool executables (Python scripts) on PATH.

    Each fake prints a fixture to stdout, optionally writes a report file given by a flag,
    optionally sleeps, and exits with the configured code. ``--version`` prints a version.
    """
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    def _make(
        name: str,
        *,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
        sleep: float = 0.0,
        report_flag: str | None = None,
        report: str | None = None,
        version: str = "9.9.9",
    ) -> Path:
        spec = {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "sleep": sleep,
            "report_flag": report_flag,
            "report": report,
            "version": version,
        }
        script = bin_dir / name
        script.write_text(
            f"#!{sys.executable}\n"
            "import json, sys, time\n"
            f"spec = json.loads({json.dumps(json.dumps(spec))})\n"
            "args = sys.argv[1:]\n"
            "if args[:1] in (['--version'], ['version']):\n"
            "    print(spec['version']); sys.exit(0)\n"
            "if spec['report_flag']:\n"
            "    for i, a in enumerate(args):\n"
            "        if a == spec['report_flag']:\n"
            "            open(args[i + 1], 'w').write(spec['report'] or '')\n"
            "        elif a.startswith(spec['report_flag'] + '='):\n"
            "            open(a.split('=', 1)[1], 'w').write(spec['report'] or '')\n"
            "time.sleep(spec['sleep'])\n"
            "sys.stdout.write(spec['stdout']); sys.stderr.write(spec['stderr'])\n"
            "sys.exit(spec['exit_code'])\n",
            encoding="utf-8",
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return script

    return _make


def fixture_text(*parts: str) -> str:
    return FIXTURES.joinpath(*parts).read_text(encoding="utf-8")


PY_REPO = {
    "pyproject.toml": """
        [project]
        name = "demo"
        dependencies = ["fastapi>=0.1", "psycopg[binary]"]
        [tool.pytest.ini_options]
        testpaths = ["tests"]
    """,
    "demo/__init__.py": "",
    "demo/app.py": "def handler():\n    return 1\n",
    "tests/test_app.py": "def test_ok():\n    assert True\n",
}
