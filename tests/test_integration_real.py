"""Integration tests that run real tools. Each is skipped when its tool is not installed.

Run only these with: pytest -m integration
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from conftest import REPO_ROOT

from archonix.cli import main
from archonix.perf import k6_script

pytestmark = pytest.mark.integration


def needs(*tools: str) -> pytest.MarkDecorator:
    missing = [t for t in tools if shutil.which(t) is None]
    return pytest.mark.skipif(bool(missing), reason=f"not installed: {', '.join(missing)}")


@pytest.fixture
def service(tmp_path: Path) -> Path:
    dest = tmp_path / "python-service"
    shutil.copytree(REPO_ROOT / "examples" / "python-service", dest)
    return dest


def run_report(root: Path, out: Path, checks: str, *extra: str) -> dict:
    code = main(
        [
            "check",
            "run",
            str(root),
            "--mode",
            "audit",
            "--checks",
            checks,
            "--out-dir",
            str(out),
            *extra,
        ]
    )
    assert code == 0
    return json.loads((out / "report.json").read_text())


@needs("ruff", "bandit", "vulture")
def test_real_static_tools_on_example(service: Path, tmp_path: Path) -> None:
    report = run_report(service, tmp_path / "out", "ruff,bandit,vulture")
    ex = {e["check_id"]: e for e in report["executions"]}
    assert all(e["status"] == "completed" for e in ex.values())
    assert {e["outcome"] for e in ex.values()} == {"findings"}
    assert all(e["tool_version"] for e in ex.values())
    rules = {(f["source"]["tool"], f["source"]["rule_id"]) for f in report["findings"]}
    assert ("bandit", "B602") in rules and ("ruff", "S602") in rules
    assert ("vulture", "unused function") in rules
    secret = "example-not-a-real-password"
    assert secret not in (tmp_path / "out" / "report.json").read_text()
    assert secret not in "".join(
        p.read_text() for p in (tmp_path / "out" / "artifacts").rglob("*") if p.is_file()
    )


@needs("pytest")
def test_real_pytest_on_example(service: Path, tmp_path: Path) -> None:
    report = run_report(service, tmp_path / "out", "pytest", "--allow-repo-code")
    ex = report["executions"][0]
    assert ex["outcome"] == "clean"
    assert ex["test_totals"] == {"total": 3, "passed": 3, "failed": 0, "skipped": 0, "errored": 0}
    (service / "tests" / "test_broken.py").write_text("def test_broken():\n    assert 1 == 2\n")
    report = run_report(service, tmp_path / "out2", "pytest", "--allow-repo-code")
    assert report["executions"][0]["outcome"] == "tests-failed"
    assert report["executions"][0]["test_totals"]["failed"] == 1


@needs("git")
def test_real_git_revision_and_dirty_state(
    service: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git = ["git", "-c", "user.name=Archonix Test", "-c", "user.email=test@example.invalid"]
    subprocess.run([*git, "init", "-q", "-b", "main"], cwd=service, check=True)
    subprocess.run([*git, "add", "."], cwd=service, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "init"], cwd=service, check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=service, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert main(["inventory", str(service), "--format", "json", "--allow-tools"]) == 0
    repo = json.loads(capsys.readouterr().out)["repository"]
    assert repo["revision"] == sha and repo["dirty"] is False
    (service / "new.txt").write_text("x")
    assert main(["inventory", str(service), "--format", "json", "--allow-tools"]) == 0
    assert json.loads(capsys.readouterr().out)["repository"]["dirty"] is True


@needs("k6")
def test_generated_k6_script_runs(tmp_path: Path) -> None:
    (tmp_path / "health").write_text("ok")

    class Quiet(SimpleHTTPRequestHandler):
        def __init__(self, *a: object, **kw: object) -> None:
            super().__init__(*a, directory=str(tmp_path), **kw)  # type: ignore[arg-type]

        def log_message(self, *args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        script = tmp_path / "load.js"
        script.write_text(
            k6_script(
                f"http://127.0.0.1:{httpd.server_address[1]}",
                ["/health"],
                vus=1,
                duration="2s",
                p95_ms=1000,
                max_error_rate=0.01,
            )
        )
        result = subprocess.run(
            ["k6", "run", "--quiet", "--no-usage-report", str(script)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr[-2000:]
    finally:
        httpd.shutdown()


@needs("gitleaks")
def test_real_gitleaks_finds_synthetic_token_without_copying_it(tmp_path: Path) -> None:
    import random
    import string

    rng = random.Random(7)  # synthetic, deterministic, never a real credential
    token = "ghp_" + "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(36))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "settings.py").write_text(f'GITHUB_TOKEN = "{token}"\n')
    report = run_report(repo, tmp_path / "out", "gitleaks")
    ex = report["executions"][0]
    assert (ex["status"], ex["outcome"], ex["exit_code"]) == ("completed", "findings", 1)
    assert report["findings"][0]["location"]["path"] == "settings.py"
    assert all(token not in p.read_text() for p in (tmp_path / "out").rglob("*") if p.is_file())
    (repo / "settings.py").write_text("GITHUB_TOKEN = None\n")
    clean = run_report(repo, tmp_path / "out2", "gitleaks")
    assert clean["executions"][0]["outcome"] == "clean"


@needs("osv-scanner")
@pytest.mark.skipif(
    not __import__("os").environ.get("ARCHONIX_NETWORK_TESTS"),
    reason="queries osv.dev; set ARCHONIX_NETWORK_TESTS=1 to run",
)
def test_real_osv_scanner_on_vulnerable_lockfile(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "web").mkdir(parents=True)
    lock = {
        "name": "web",
        "version": "1.0.0",
        "lockfileVersion": 3,
        "requires": True,
        "packages": {
            "": {"name": "web", "version": "1.0.0", "dependencies": {"lodash": "4.17.15"}},
            # osv-scanner 2.7 skips entries without a registry "resolved" URL.
            "node_modules/lodash": {
                "version": "4.17.15",
                "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.15.tgz",
            },
        },
    }
    (repo / "web" / "package-lock.json").write_text(json.dumps(lock))
    report = run_report(repo, tmp_path / "out", "osv-scanner", "--allow-network")
    ex = report["executions"][0]
    assert (ex["status"], ex["outcome"], ex["exit_code"]) == ("completed", "findings", 1)
    assert any(f["source"]["rule_id"] == "GHSA-29mw-wpgm-hmr9" for f in report["findings"])
    assert "--no-call-analysis=all" in ex["argv"]


SEMGREP_RULES = """\
rules:
  - id: subprocess-shell-true
    languages: [python]
    severity: ERROR
    message: subprocess call with shell=True
    metadata:
      confidence: HIGH
      cwe: ["CWE-78: OS Command Injection"]
    pattern: subprocess.$F(..., shell=True, ...)
  - id: legacy-rounding
    languages: [python]
    severity: INFO
    message: legacy rounding helper
    pattern: round($X, 2)
"""


@needs("semgrep")
def test_real_semgrep_local_rules(service: Path, tmp_path: Path) -> None:
    """Offline: rules are committed in the repository, so semgrep needs no network."""
    (service / ".semgrep.yml").write_text(SEMGREP_RULES)
    report = run_report(service, tmp_path / "out", "semgrep-local")
    ex = report["executions"][0]
    assert (ex["status"], ex["outcome"], ex["exit_code"]) == ("completed", "findings", 0)
    assert ex["tool_version"]
    by_rule = {f["source"]["rule_id"]: f for f in report["findings"]}
    shell = by_rule["subprocess-shell-true"]
    assert (shell["severity"], shell["confidence"]) == ("high", "high")
    assert shell["location"] == {
        "path": "app/ops.py",
        "start_line": 11,
        "end_line": 11,
        "start_column": shell["location"]["start_column"],
        "symbol": None,
    }
    assert "CWE-78: OS Command Injection" in shell["references"]
    assert (by_rule["legacy-rounding"]["severity"], by_rule["legacy-rounding"]["confidence"]) == (
        "low",
        "unknown",
    )


@needs("semgrep")
def test_real_semgrep_clean_and_invalid_rules(service: Path, tmp_path: Path) -> None:
    (service / ".semgrep.yml").write_text(
        "rules:\n  - id: never\n    languages: [python]\n    severity: INFO\n"
        "    message: x\n    pattern: this_function_does_not_exist_anywhere()\n"
    )
    clean = run_report(service, tmp_path / "clean", "semgrep-local")
    assert clean["executions"][0]["outcome"] == "clean" and clean["findings"] == []
    (service / ".semgrep.yml").write_text(
        "rules:\n  - id: bad\n    languages: [python]\n    severity: INFO\n"
        "    message: x\n    pattern: (((\n"
    )
    broken = run_report(service, tmp_path / "broken", "semgrep-local")
    ex = broken["executions"][0]
    assert ex["status"] == "completed" and ex["outcome"] == "tool-error"
    assert ex["exit_code"] not in (0, 1)
    assert broken["summary"]["failed"] == 1
