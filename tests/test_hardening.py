"""Regression tests for defects found in the community-readiness audit.

Each test reproduces a confirmed defect (D1-D7 in docs/audits/2026-10-community-readiness.md)
and asserts the fixed behaviour. All data is synthetic.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import PY_REPO, REPO_ROOT

from archonix.checks import _redact_artifacts, execute_plan, plan_checks
from archonix.cli import main
from archonix.config import load_settings
from archonix.install import MANIFEST, install, uninstall
from archonix.inventory import build_inventory
from archonix.redact import Redactor
from archonix.report import build_workflow_report
from archonix.runner import build_env, run, safe_path
from archonix.schemas import validate

posix_only = pytest.mark.skipif(os.name != "posix", reason="symlinks / shebang scripts")


def _manifest(target: Path, files: dict[str, str]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / MANIFEST).write_text(json.dumps({"tool": "archonix", "files": files}))


# --- D1: uninstall trusted manifest paths --------------------------------------------


@pytest.mark.parametrize(
    "entry",
    [
        "../../../../victim.txt",
        "/tmp/archonix-victim-abs.txt",
        "references/../../../../../victim.txt",
        "",
        "a\\..\\b",
    ],
)
def test_manifest_traversal_is_refused(tmp_path: Path, entry: str) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("important")
    digest = hashlib.sha256(b"important").hexdigest()
    target = tmp_path / "proj" / ".claude" / "skills" / "archonix"
    _manifest(target, {entry: digest})

    plan = uninstall("claude", "project", home=tmp_path, project_dir=tmp_path / "proj", apply=True)
    assert not plan.applied
    assert any("unsafe path" in c for c in plan.conflicts)
    assert victim.read_text() == "important"
    assert (target / MANIFEST).exists()  # nothing was deleted, not even the manifest

    again = install("claude", "project", home=tmp_path, project_dir=tmp_path / "proj", apply=True)
    assert not again.applied and any("unsafe path" in c for c in again.conflicts)


def test_cli_uninstall_with_tampered_manifest_exits_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _manifest(tmp_path / "proj" / ".agents" / "skills" / "archonix", {"../../../x": "0" * 64})
    code = main(
        [
            "uninstall",
            "--assistant",
            "codex",
            "--scope",
            "project",
            "--project-dir",
            str(tmp_path / "proj"),
            "--apply",
        ]
    )
    assert code == 3


# --- D2: symlinks inside or above the target -----------------------------------------


@posix_only
def test_install_refuses_symlinked_subdirectory(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    target = install("claude", "project", home=tmp_path, project_dir=proj, apply=True).target
    outside = tmp_path / "outside"
    outside.mkdir()
    for f in (target / "references").iterdir():
        f.unlink()
    (target / "references").rmdir()
    (target / "references").symlink_to(outside, target_is_directory=True)

    plan = install("claude", "project", home=tmp_path, project_dir=proj, apply=True)
    assert not plan.applied and any("symlink" in c for c in plan.conflicts)
    assert list(outside.iterdir()) == []

    (outside / "security.md").write_text(
        (REPO_ROOT / "skills/archonix/references/security.md").read_text()
    )
    removed = uninstall("claude", "project", home=tmp_path, project_dir=proj, apply=True)
    assert not removed.applied
    assert (outside / "security.md").exists()


@posix_only
def test_install_refuses_symlinked_target_and_project_skills_dir(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "skills").symlink_to(elsewhere, target_is_directory=True)
    plan = install("claude", "project", home=tmp_path, project_dir=proj, apply=True)
    assert not plan.applied and "symlink" in plan.conflicts[0]
    assert list(elsewhere.iterdir()) == []

    home = tmp_path / "home"
    (home / ".cursor" / "skills").mkdir(parents=True)
    (home / ".cursor" / "skills" / "archonix").symlink_to(elsewhere, target_is_directory=True)
    plan = install("cursor", "user", home=home, apply=True)
    assert not plan.applied and "symlink" in plan.conflicts[0]


@posix_only
def test_user_scope_allows_symlinked_dotfiles_directory(tmp_path: Path) -> None:
    """Users commonly symlink ~/.claude from a dotfiles repo; that stays supported."""
    real = tmp_path / "dotfiles" / "claude"
    real.mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").symlink_to(real, target_is_directory=True)
    plan = install("claude", "user", home=home, apply=True)
    assert plan.applied and (real / "skills" / "archonix" / "SKILL.md").is_file()


@posix_only
def test_installed_file_replaced_by_symlink_is_not_followed(tmp_path: Path) -> None:
    target = install("codex", "user", home=tmp_path, apply=True).target
    outside = tmp_path / "secret.txt"
    outside.write_text("do not touch")
    (target / "SKILL.md").unlink()
    (target / "SKILL.md").symlink_to(outside)
    assert not install("codex", "user", home=tmp_path, apply=True).applied
    uninstall("codex", "user", home=tmp_path, apply=True)
    assert outside.read_text() == "do not touch"


# --- D3: repository config could supply regexes; repo exclusions were invisible ------


def test_repo_config_cannot_supply_redaction_regex(make_repo: Callable[..., Path]) -> None:
    root = make_repo(
        {
            "archonix.toml": '[redaction]\nextra_patterns = ["(a+)+$"]\n'
            'sensitive_env_names = ["MY_KEY"]\n'
        }
    )
    s = load_settings(root)
    assert s.extra_redaction_patterns == []
    assert s.sensitive_env_names == ["MY_KEY"]  # names are harmless and still honoured
    assert any("redaction.extra_patterns" in x for x in s.ignored)


def test_trusted_config_may_still_supply_regex(tmp_path: Path) -> None:
    cfg = tmp_path / "trusted.toml"
    cfg.write_text('[redaction]\nextra_patterns = ["ACME-[0-9]{6}"]\n')
    assert load_settings(None, explicit_config=cfg).extra_redaction_patterns == ["ACME-[0-9]{6}"]


def test_repo_exclusions_are_reported(make_repo: Callable[..., Path]) -> None:
    root = make_repo({**PY_REPO, "archonix.toml": '[inventory]\nexclude = ["demo", "*"]\n'})
    settings = load_settings(root, mode="audit")
    inv = build_inventory(root, settings)
    report = build_workflow_report(
        workflow="audit",
        root=str(root),
        settings=settings,
        inventory=inv,
        repository=inv["repository"],
        executions=[],
        findings=[],
        skipped=[],
        requested_checks=None,
    )
    validate(report, "workflow-report")
    assert any(
        "repository config excluded paths" in x and "demo, *" in x for x in report["limitations"]
    )


# --- D4: relative PATH entries resolved to repository files --------------------------


def test_safe_path_drops_relative_entries() -> None:
    sep = os.pathsep
    assert safe_path(sep.join([".", "", "bin", "/usr/bin", "node_modules/.bin"])) == "/usr/bin"
    assert "." not in build_env(source={"PATH": f".{sep}/usr/bin"})["PATH"].split(sep)


@posix_only
def test_repo_local_executable_is_not_run_via_dot_in_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    marker = tmp_path / "pwned"
    tool = repo / "archonix-fake-tool"
    tool.write_text(f"#!/bin/sh\ntouch {marker}\n")
    tool.chmod(0o755)
    monkeypatch.chdir(repo)
    env = {"PATH": f".{os.pathsep}{os.environ['PATH']}"}
    result = run(["archonix-fake-tool"], repo, env=env, timeout=5, max_output_bytes=1024)
    assert result.status == "missing-tool"
    assert not marker.exists()


# --- D5: details, limitations and nested artifacts bypassed redaction -----------------


@posix_only
def test_tool_error_detail_is_redacted(
    make_repo: Callable[..., Path], fake_bin: Callable[..., Path]
) -> None:
    cred = "https://ci-user:synthetic-pass-123@registry.example.invalid/"
    fake_bin(
        "npm", stdout=json.dumps({"error": {"summary": f"request to {cred} failed"}}), exit_code=1
    )
    root = make_repo({"package.json": '{"name": "x"}', "package-lock.json": "{}"})
    settings = load_settings(root, mode="audit", cli_permissions={"network": True})
    plans = plan_checks(root, build_inventory(root, settings), settings, ["npm-audit"])
    executions, _, _ = execute_plan(
        root, plans, settings, artifact_dir=None, redactor=Redactor.from_environment(env={})
    )
    ex = executions[0]
    assert ex["outcome"] == "tool-error"
    assert "synthetic-pass-123" not in json.dumps(ex)
    assert "[REDACTED]" in ex["outcome_detail"]


def test_nested_artifacts_are_redacted_and_gaps_reported(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    value = "synthetic-" + "key-12345"  # assembled at runtime; never a literal credential
    (tmp_path / "nested" / "out.json").write_text(json.dumps({"api_key": value}))
    (tmp_path / "blob.bin").write_bytes(b"\xff\xfe\x00binary")
    n, notes = _redact_artifacts(tmp_path, Redactor.from_environment(env={}))
    assert n == 1
    assert value not in (tmp_path / "nested" / "out.json").read_text()
    assert notes == [
        "retained artifact blob.bin is not UTF-8 text, could not be redacted, and was removed"
    ]
    assert not (tmp_path / "blob.bin").exists()


def test_oversized_artifact_is_reported_not_silently_kept(tmp_path: Path) -> None:
    (tmp_path / "big.txt").write_text("token=synthetic-value-999 " * 10)
    _, notes = _redact_artifacts(tmp_path, Redactor.from_environment(env={}), limit=10)
    assert notes and "exceeds 10 bytes" in notes[0] and "removed" in notes[0]
    assert not (tmp_path / "big.txt").exists()


# --- D6: unreadable inputs produced tracebacks ---------------------------------------


def test_cli_reports_unreadable_inputs_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["validate", str(tmp_path)]) == 1
    assert "is a directory" in capsys.readouterr().err
    (tmp_path / "bin.json").write_bytes(b"\xff\xfe")
    assert main(["validate", str(tmp_path / "bin.json")]) == 1
    assert main(["perf", "endpoints", str(tmp_path / "missing.json")]) == 2
    err = capsys.readouterr().err
    assert "cannot read" in err and "Traceback" not in err


# --- D7: third-party imports must be declared runtime dependencies --------------------


def test_every_third_party_import_is_declared() -> None:
    declared = {
        dep.split(">")[0].split("=")[0].split("[")[0].strip().lower().replace("-", "_")
        for dep in tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"][
            "dependencies"
        ]
    }
    optional = {"yaml"}  # imported lazily with a clear error message when missing
    imported: set[str] = set()
    for path in (REPO_ROOT / "src" / "archonix").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
    third_party = {m for m in imported if m not in sys.stdlib_module_names and m != "archonix"}
    assert third_party - optional <= declared, third_party - optional - declared


# --- Review issue 1: artifacts were not finalized when a check timed out --------------


@posix_only
def test_timed_out_check_artifacts_are_redacted_and_listed(
    make_repo: Callable[..., Path],
    fake_bin: Callable[..., Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "synthetic-" + "token-" + "9f8e7d6c5b4a"  # assembled at runtime
    fake_bin(
        "pytest", report_flag="--junitxml", report=f'<testsuites api_key="{secret}"/>', sleep=30
    )
    monkeypatch.setenv("ARCHONIX_TIMEOUT_SECONDS", "1")
    root = make_repo(PY_REPO)
    settings = load_settings(root, mode="audit", cli_permissions={"repo_code": True})
    plans = plan_checks(root, build_inventory(root, settings), settings, ["pytest"])
    out = tmp_path / "out"
    executions, _, _ = execute_plan(
        root, plans, settings, artifact_dir=out, redactor=Redactor.from_environment(env={})
    )
    ex = executions[0]
    assert ex["status"] == "timeout"
    assert [Path(a["path"]).name for a in ex["artifacts"]] == ["pytest-junit.xml"]
    assert secret not in (out / "artifacts" / "pytest" / "pytest-junit.xml").read_text()
    assert ex["redaction"]["replacements"] >= 1


def test_adapter_exception_still_finalizes_artifacts(
    make_repo: Callable[..., Path],
    fake_bin: Callable[..., Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from archonix.adapters import ADAPTERS

    secret = "synthetic-" + "token-" + "1a2b3c4d5e6f"
    fake_bin("pytest", report_flag="--junitxml", report=f'<x api_key="{secret}"/>')

    def boom(*_: object) -> None:
        raise RuntimeError("parser crashed")

    monkeypatch.setattr(ADAPTERS["pytest"], "interpret", boom)
    root = make_repo(PY_REPO)
    settings = load_settings(root, mode="audit", cli_permissions={"repo_code": True})
    plans = plan_checks(root, build_inventory(root, settings), settings, ["pytest"])
    out = tmp_path / "out"
    executions, findings, _ = execute_plan(
        root, plans, settings, artifact_dir=out, redactor=Redactor.from_environment(env={})
    )
    ex = executions[0]
    assert ex["outcome"] == "parse-error" and "parser crashed" in ex["outcome_detail"]
    assert findings == [] and ex["artifacts"]
    assert secret not in (out / "artifacts" / "pytest" / "pytest-junit.xml").read_text()


# --- Feedback review: a committed .archonix symlink redirected reports outside the repo -


@posix_only
@pytest.mark.parametrize(
    "command",
    [
        [
            "check",
            "run",
            "{repo}",
            "--mode",
            "audit",
            "--checks",
            "gitleaks",
            "--out-dir",
            "{repo}/.archonix/run-1",
        ],
        ["inventory", "{repo}", "--out", "{repo}/.archonix/inventory.md"],
        ["architecture", "diagram", "{repo}", "--out", "{repo}/.archonix/arch.md"],
    ],
)
def test_output_through_repo_symlink_is_refused(
    make_repo: Callable[..., Path],
    tmp_path: Path,
    command: list[str],
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    repo = make_repo(PY_REPO)
    (repo / ".archonix").symlink_to(outside, target_is_directory=True)
    argv = [part.replace("{repo}", str(repo)) for part in command]
    assert main(argv) == 3
    assert list(outside.rglob("*")) == []


@posix_only
def test_symlinks_outside_the_repo_and_real_dirs_are_allowed(
    make_repo: Callable[..., Path],
    tmp_path: Path,
    fake_bin: Callable[..., Path],
) -> None:
    fake_bin("ruff", stdout="[]")
    repo = make_repo(PY_REPO)
    real = tmp_path / "reports-real"
    real.mkdir()
    (tmp_path / "reports-link").symlink_to(real, target_is_directory=True)
    args = ["check", "run", str(repo), "--mode", "audit", "--checks", "ruff"]
    assert main([*args, "--out-dir", str(tmp_path / "reports-link" / "run")]) == 0
    assert (real / "run" / "report.json").is_file()
    assert main([*args, "--out-dir", str(repo / ".archonix" / "run")]) == 0  # real directory
    assert (repo / ".archonix" / "run" / "report.json").is_file()


# --- Feedback review: gitleaks ignored Archonix exclusions -----------------------------


def _gitleaks_ctx(root: Path, artifacts: Path) -> object:
    from archonix.adapters import Context

    return Context(root=root, artifact_dir=artifacts, excludes=["__pycache__", "*.egg-info"])


def test_gitleaks_config_applies_exclusions_and_defaults(tmp_path: Path) -> None:
    from archonix.adapters import ADAPTERS

    gl = ADAPTERS["gitleaks"]
    ctx = _gitleaks_ctx(tmp_path, tmp_path / "art")
    gl.prepare(ctx)  # type: ignore[arg-type]
    config = (tmp_path / "art" / "gitleaks-archonix.toml").read_text()
    data = tomllib.loads(config)
    assert data["extend"] == {"useDefault": True}
    assert data["allowlist"]["paths"] == [
        r"(^|/)(?s:__pycache__)(/|$)",
        r"(^|/)(?s:.*\.egg\-info)(/|$)",
    ]
    argv = gl.argv(ctx)  # type: ignore[arg-type]
    assert argv[argv.index("--config") + 1] == str(tmp_path / "art" / "gitleaks-archonix.toml")


def test_gitleaks_config_extends_repo_config_but_not_through_symlink(tmp_path: Path) -> None:
    from archonix.adapters import ADAPTERS

    gl = ADAPTERS["gitleaks"]
    (tmp_path / ".gitleaks.toml").write_text("[extend]\nuseDefault = true\n")
    gl.prepare(_gitleaks_ctx(tmp_path, tmp_path / "a"))  # type: ignore[arg-type]
    data = tomllib.loads((tmp_path / "a" / "gitleaks-archonix.toml").read_text())
    assert data["extend"] == {"path": str(tmp_path / ".gitleaks.toml")}
    if os.name == "posix":
        (tmp_path / ".gitleaks.toml").unlink()
        (tmp_path / ".gitleaks.toml").symlink_to(tmp_path / "elsewhere.toml")
        gl.prepare(_gitleaks_ctx(tmp_path, tmp_path / "b"))  # type: ignore[arg-type]
        data = tomllib.loads((tmp_path / "b" / "gitleaks-archonix.toml").read_text())
        assert data["extend"] == {"useDefault": True}


def test_planning_gitleaks_writes_nothing(
    make_repo: Callable[..., Path], fake_bin: Callable[..., Path]
) -> None:
    fake_bin("gitleaks")
    root = make_repo(PY_REPO)
    before = sorted(root.rglob("*"))
    settings = load_settings(root, mode="audit")
    plan_checks(root, build_inventory(root, settings), settings, ["gitleaks"])
    assert sorted(root.rglob("*")) == before
    assert not Path("<artifact-dir>").exists()
