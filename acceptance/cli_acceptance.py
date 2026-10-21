"""Archonix CLI acceptance suite.

Drives an *installed* ``archonix`` (not the source tree) against synthetic scenario
repositories built from ``examples/`` and checks the acceptance criteria in
``acceptance/README.md``. Real tools (ruff, bandit, vulture, pytest, gitleaks) are used
when they are on PATH; checks that need a missing tool are recorded as SKIP, never PASS.

    python acceptance/cli_acceptance.py --archonix "$(command -v archonix)"

Exit status: 0 when nothing failed (skips allowed), 1 when any check failed.
Standard library only; never contacts the network; runs repository code only for the
pytest scenarios, which use synthetic fixtures.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# Synthetic values, assembled at runtime so no credential-shaped literal is committed.
FAKE_SECRET = "tok-" + "acceptance-" + "123456"
EXAMPLE_PASSWORD = "example-not-a-real-password"  # synthetic, lives in examples/


class Suite:
    def __init__(self, archonix: str, work: Path, examples: Path) -> None:
        self.archonix, self.work, self.examples = archonix, work, examples
        self.results: list[dict[str, str]] = []

    # ------------------------------------------------------------------ helpers
    def record(self, ac: str, scenario: str, name: str, status: str, evidence: str) -> None:
        evidence = evidence.replace(str(self.work), "<work>")
        self.results.append(
            {"ac": ac, "scenario": scenario, "check": name, "status": status, "evidence": evidence}
        )
        print(f"[{status:4}] {ac:5} {scenario:3} {name}: {evidence}")

    def check(self, ac: str, scenario: str, name: str, ok: bool, evidence: str) -> None:
        self.record(ac, scenario, name, "PASS" if ok else "FAIL", evidence)

    def skip(self, ac: str, scenario: str, name: str, reason: str) -> None:
        self.record(ac, scenario, name, "SKIP", reason)

    def arx(
        self, *args: str, cwd: Path | None = None, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.archonix, *args],
            cwd=cwd or self.work,
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
            timeout=600,
            check=False,
        )

    def repo(
        self, name: str, example: str | None, files: dict[str, str] | None = None, git: bool = False
    ) -> Path:
        dest = self.work / "repos" / name
        shutil.rmtree(dest, ignore_errors=True)
        if example:
            shutil.copytree(self.examples / example, dest)
        else:
            dest.mkdir(parents=True)
        for rel, text in (files or {}).items():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (dest / rel).write_text(text)
        if git:
            ident = ["-c", "user.name=Acceptance", "-c", "user.email=acceptance@example.invalid"]
            for cmd in (
                ["init", "-q", "-b", "main"],
                ["add", "-A"],
                ["commit", "-q", "-m", "fixture"],
            ):
                subprocess.run(["git", *ident, *cmd], cwd=dest, check=True)
        return dest

    def run(
        self,
        scenario: str,
        repo: Path,
        checks: str,
        label: str,
        *flags: str,
        env: dict[str, str] | None = None,
    ) -> dict | None:
        out = self.work / "out" / label
        shutil.rmtree(out, ignore_errors=True)
        r = self.arx(
            "check",
            "run",
            str(repo),
            "--mode",
            "audit",
            "--checks",
            checks,
            "--out-dir",
            str(out),
            *flags,
            env=env,
        )
        if r.returncode != 0 or not (out / "report.json").is_file():
            self.check(
                "AC-4",
                scenario,
                f"run {checks}",
                False,
                f"exit {r.returncode}: {r.stderr.strip()[-200:]}",
            )
            return None
        v = self.arx("validate", str(out / "report.json"))
        self.check(
            "AC-4",
            scenario,
            f"report {label} validates",
            v.returncode == 0,
            "valid" if v.returncode == 0 else v.stderr.strip()[-200:],
        )
        report: dict = json.loads((out / "report.json").read_text())
        return report

    def plan(self, repo: Path, *flags: str) -> dict[str, dict]:
        r = self.arx("check", "plan", str(repo), "--format", "json", *flags)
        return {c["check_id"]: c for c in json.loads(r.stdout)["checks"]}

    def inventory(self, scenario: str, repo: Path, expected: set[str], forbidden: set[str]) -> dict:
        marker = self.work / f"executed-{scenario}"
        out = self.work / f"inventory-{scenario}.json"
        r = self.arx("inventory", str(repo), "--format", "json", "--out", str(out), "--overwrite")
        inv: dict = json.loads(out.read_text()) if r.returncode == 0 else {}
        got = {f"{d['category']}:{d['name']}" for d in inv.get("detections", [])}
        self.check(
            "AC-3",
            scenario,
            "expected detections",
            expected <= got,
            f"missing={sorted(expected - got)}",
        )
        self.check(
            "AC-3",
            scenario,
            "no false detections",
            not forbidden & got,
            f"unexpected={sorted(forbidden & got)}",
        )
        self.check(
            "AC-3",
            scenario,
            "repository code not executed",
            not marker.exists(),
            "marker absent" if not marker.exists() else "marker created",
        )
        v = self.arx("validate", str(out))
        self.check(
            "AC-4",
            scenario,
            "inventory validates",
            v.returncode == 0,
            "valid" if v.returncode == 0 else v.stderr.strip()[-200:],
        )
        return inv

    @staticmethod
    def execution(report: dict, check_id: str) -> dict:
        return next(e for e in report["executions"] if e["check_id"] == check_id)

    # ------------------------------------------------------------------ scenarios
    def install_and_resources(self) -> None:
        r = self.arx("--version")
        self.check("AC-1", "-", "installed CLI runs", r.returncode == 0, r.stdout.strip())
        outside = self.work / "outside"
        outside.mkdir(exist_ok=True)
        r = self.arx("skill", "validate", cwd=outside)
        self.check(
            "AC-2",
            "-",
            "bundled skill validates outside a checkout",
            r.returncode == 0 and str(REPO) not in r.stdout,
            "valid skill" if r.returncode == 0 else r.stderr.strip(),
        )
        r = self.arx("schema", "list", cwd=outside)
        self.check(
            "AC-2",
            "-",
            "bundled schemas available",
            len(r.stdout.split()) == 8,
            f"{len(r.stdout.split())} schemas",
        )
        target = self.repo("docs-target", None, {"README.md": "# demo\n"})
        r = self.arx(
            "docs",
            "init",
            str(target),
            "--set",
            "discovery",
            "--apply",
            "--allow-source-writes",
            cwd=outside,
        )
        made = sorted(p.name for p in (target / "docs").glob("*"))
        self.check(
            "AC-2",
            "-",
            "templates usable outside a checkout",
            r.returncode == 0 and len(made) == 6,
            f"created {len(made)} files",
        )
        r = self.arx("requirements", "validate", str(target / "docs" / "requirements.json"))
        self.check(
            "AC-11",
            "-",
            "template ledger validates",
            r.returncode == 0,
            "valid" if r.returncode == 0 else r.stderr.strip(),
        )

    def requirements(self) -> None:
        ledger = REPO / "examples" / "requirements" / "ledger.json"
        r = self.arx("requirements", "validate", str(ledger))
        self.check("AC-11", "-", "example ledger validates", r.returncode == 0, "valid")
        bad = json.loads(ledger.read_text())
        bad["requirements"][0]["dependencies"] = ["REQ-999"]
        bad["requirements"][1]["status"] = "approved"
        bad["requirements"][1]["open_questions"][0]["accepted_as_assumption"] = False
        path = self.work / "bad-ledger.json"
        path.write_text(json.dumps(bad))
        r = self.arx("requirements", "validate", str(path))
        self.check(
            "AC-11",
            "-",
            "broken ledger rejected with reasons",
            r.returncode == 1 and "REQ-999" in r.stderr and "critical question" in r.stderr,
            f"exit {r.returncode}",
        )

    def python_service(self) -> None:
        marker = self.work / "executed-S1"
        s1 = self.repo(
            "s1-python",
            "python-service",
            {
                "conftest.py": f"open({str(marker)!r}, 'w').close()\n",
                "setup.py": f"open({str(marker)!r}, 'w').close()\n",
            },
        )
        self.inventory(
            "S1",
            s1,
            {
                "framework:Flask",
                "test:pytest",
                "lint:Ruff",
                "database:PostgreSQL client",
                "cache:Redis client",
                "queue:Celery",
                "container:Docker",
                "api-spec:OpenAPI",
            },
            {"framework:React", "framework:Next.js"},
        )
        audit = self.plan(s1, "--mode", "audit")
        self.check(
            "AC-7",
            "S1",
            "pytest blocked without --allow-repo-code",
            audit["pytest"]["action"] == "block",
            audit["pytest"]["reason"],
        )
        self.check(
            "AC-7",
            "S1",
            "network checks not run without --allow-network",
            audit["semgrep-registry"]["action"] == "block"
            and audit["osv-scanner"]["action"] in {"block", "skip"},
            f"semgrep-registry={audit['semgrep-registry']['action']}, "
            f"osv-scanner={audit['osv-scanner']['action']}",
        )
        discovery = self.plan(s1)
        self.check(
            "AC-7",
            "S1",
            "discovery mode launches no tool",
            all(c["action"] in {"block", "skip"} for c in discovery.values()),
            ", ".join(f"{k}={v['action']}" for k, v in discovery.items()),
        )
        (s1 / "archonix.toml").write_text("[permissions]\nrepo_code = true\nnetwork = true\n")
        r = self.arx("check", "plan", str(s1), "--mode", "audit", "--format", "json")
        planned = json.loads(r.stdout)
        pytest_plan = next(c for c in planned["checks"] if c["check_id"] == "pytest")
        self.check(
            "AC-7",
            "S1",
            "repository config cannot grant permissions",
            pytest_plan["action"] == "block" and len(planned["ignored_settings"]) == 2,
            f"ignored {len(planned['ignored_settings'])} settings",
        )
        (s1 / "archonix.toml").unlink()

        static = [t for t in ("ruff", "bandit", "vulture") if shutil.which(t)]
        if static:
            report = self.run("S1", s1, ",".join(static), "s1-static")
            if report:
                outcomes = {e["check_id"]: e["outcome"] for e in report["executions"]}
                self.check(
                    "AC-6",
                    "S1",
                    "real static tools report findings",
                    set(outcomes.values()) == {"findings"},
                    str(outcomes),
                )
                rules = {(f["source"]["tool"], f["source"]["rule_id"]) for f in report["findings"]}
                expect = {("bandit", "B602")} if "bandit" in static else set()
                self.check(
                    "AC-4",
                    "S1",
                    "known-bad code is found",
                    expect <= rules,
                    f"{len(report['findings'])} findings",
                )
                artifacts = self.work / "out" / "s1-static" / "artifacts"
                leaked = EXAMPLE_PASSWORD in json.dumps(report) or any(
                    EXAMPLE_PASSWORD in p.read_text(errors="ignore")
                    for p in artifacts.rglob("*")
                    if p.is_file()
                )
                self.check(
                    "AC-8",
                    "S1",
                    "fake password redacted in report and artifacts",
                    not leaked,
                    "absent" if not leaked else "present",
                )
            self.check(
                "AC-3",
                "S1",
                "static audit did not run repository code",
                not marker.exists(),
                "marker absent",
            )
        else:
            self.skip("AC-6", "S1", "real static tools", "ruff/bandit/vulture not on PATH")

        if shutil.which("pytest"):
            report = self.run("S1", s1, "pytest", "s1-pytest", "--allow-repo-code")
            if report:
                e = self.execution(report, "pytest")
                self.check(
                    "AC-5",
                    "S1",
                    "passing tests are counted",
                    e["outcome"] == "clean" and e["test_totals"]["total"] == 3,
                    json.dumps(e["test_totals"]),
                )
                left = [p.name for p in s1.rglob("*") if p.name in {"__pycache__", ".pytest_cache"}]
                self.check(
                    "AC-7",
                    "S1",
                    "test run leaves no caches in the repository",
                    not left,
                    f"leftovers={left}",
                )
            marker.unlink(missing_ok=True)
        else:
            self.skip("AC-5", "S1", "passing tests are counted", "pytest not on PATH")

        if shutil.which("ruff"):
            broken = self.repo(
                "s1-broken-ruff", "python-service", {"ruff.toml": "this is = = not toml\n"}
            )
            report = self.run("S1", broken, "ruff", "s1-ruff-broken")
            if report:
                e = self.execution(report, "ruff")
                self.check(
                    "AC-6",
                    "S1",
                    "broken tool config is a tool error, not a finding",
                    e["outcome"] == "tool-error" and report["findings"] == [],
                    f"{e['outcome']}, exit {e['exit_code']}",
                )
        else:
            self.skip("AC-6", "S1", "broken tool config", "ruff not on PATH")

        fake = self.work / "fakebin"
        fake.mkdir(exist_ok=True)
        (fake / "ruff").write_text(
            '#!/bin/sh\n[ "$1" = "--version" ] && echo \'ruff 0.0.0\' && exit 0\n'
            "echo \"connecting with $ACCEPT_API_TOKEN\" >&2\necho '[]'\n"
        )
        (fake / "ruff").chmod(0o755)
        env = {"PATH": f"{fake}{os.pathsep}{os.environ['PATH']}", "ACCEPT_API_TOKEN": FAKE_SECRET}
        report = self.run("S1", s1, "ruff", "s1-env", env=env)
        if report:
            e = self.execution(report, "ruff")
            self.check(
                "AC-8",
                "S1",
                "caller's secret env vars are not passed to tools",
                e["stderr"]["excerpt"] == "connecting with \n"
                and FAKE_SECRET not in json.dumps(report),
                repr(e["stderr"]["excerpt"]),
            )
        trusted = self.work / "trusted.toml"
        trusted.write_text('[execution]\nenv_passthrough = ["ACCEPT_API_TOKEN"]\n')
        report = self.run("S1", s1, "ruff", "s1-env-pass", "--config", str(trusted), env=env)
        if report:
            e = self.execution(report, "ruff")
            self.check(
                "AC-8",
                "S1",
                "deliberately passed secret is masked in the report",
                FAKE_SECRET not in json.dumps(report) and e["redaction"]["replacements"] >= 1,
                f"{e['stderr']['excerpt'].strip()!r}",
            )

    def readiness(self) -> None:
        policy = REPO / "examples" / "readiness-policy.toml"
        r = self.arx("readiness", "assess", "--policy", str(policy), "--format", "json")
        self.check(
            "AC-5",
            "-",
            "no evidence is incomplete (exit 4)",
            r.returncode == 4 and json.loads(r.stdout)["verdict"] == "incomplete",
            f"exit {r.returncode}",
        )
        s1 = self.work / "repos" / "s1-python"
        report = self.run("S1", s1, "ruff,bandit,pytest", "s1-blocked")
        if report:
            r = self.arx(
                "readiness",
                "assess",
                "--policy",
                str(policy),
                "--report",
                str(self.work / "out" / "s1-blocked" / "report.json"),
                "--format",
                "json",
            )
            verdict = json.loads(r.stdout)["verdict"]
            self.check(
                "AC-5",
                "S1",
                "blocked required check is never ready",
                verdict != "ready",
                f"verdict={verdict}",
            )
        if not (shutil.which("pytest") and shutil.which("ruff")):
            self.skip("AC-5", "S1", "failing / complete evidence", "needs pytest and ruff")
            return
        failing = self.repo(
            "s1-failing",
            "python-service",
            {"tests/test_broken.py": "def test_broken():\n    assert 1 == 2\n"},
            git=True,
        )
        if self.run("S1", failing, "pytest", "s1-failing", "--allow-repo-code", "--allow-tools"):
            r = self.arx(
                "readiness",
                "assess",
                "--report",
                str(self.work / "out" / "s1-failing" / "report.json"),
                "--format",
                "json",
            )
            verdict = json.loads(r.stdout)["verdict"]
            self.check(
                "AC-5",
                "S1",
                "failing tests are not-ready (exit 1)",
                verdict == "not-ready" and r.returncode == 1,
                f"verdict={verdict}",
            )
        ready = self.repo(
            "s1-ready",
            None,
            {
                "pyproject.toml": "[project]\nname = 'ok'\nversion = '0'\n"
                "[tool.pytest.ini_options]\ntestpaths = ['tests']\n"
                "[tool.ruff]\nline-length = 100\n",
                "ok/__init__.py": "",
                "ok/core.py": "def add(a: int, b: int) -> int:\n    return a + b\n",
                "tests/conftest.py": "import pathlib\nimport sys\n\n"
                "sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))\n",
                "tests/test_core.py": "from ok.core import add\n\n\ndef test_add():\n"
                "    assert add(1, 2) == 3\n",
            },
            git=True,
        )
        if self.run("S1", ready, "ruff,pytest", "s1-ready", "--allow-repo-code", "--allow-tools"):
            pol = self.work / "ready-policy.toml"
            pol.write_text(
                'name = "acceptance"\n[rules]\nrequired_checks = ["ruff", "pytest"]\n'
                'max_severity = "medium"\nrequire_tests = true\n'
                "require_revision = true\nrequire_clean_worktree = true\n"
            )
            r = self.arx(
                "readiness",
                "assess",
                "--policy",
                str(pol),
                "--report",
                str(self.work / "out" / "s1-ready" / "report.json"),
                "--format",
                "json",
            )
            v = json.loads(r.stdout)
            self.check(
                "AC-5",
                "S1",
                "complete evidence is ready (exit 0)",
                v["verdict"] == "ready" and r.returncode == 0,
                ", ".join(f"{x['id']}={x['result']}" for x in v["rules"]),
            )

    def typescript_app(self) -> None:
        s2 = self.repo("s2-ts", "ts-web")
        self.inventory(
            "S2",
            s2,
            {
                "framework:Next.js",
                "framework:React",
                "language:TypeScript",
                "test:Jest",
                "lint:ESLint",
                "package-manager:npm",
                "database:Prisma ORM",
            },
            {"framework:Flask", "test:pytest"},
        )
        plan = self.plan(s2, "--mode", "audit")
        not_applicable = [
            k
            for k in ("ruff", "bandit", "vulture", "pytest")
            if plan[k]["action"] == "skip" and plan[k]["reason"].startswith("not applicable")
        ]
        self.check(
            "AC-10",
            "S2",
            "Python checks reported not applicable",
            len(not_applicable) == 4,
            str(not_applicable),
        )
        self.check(
            "AC-10",
            "S2",
            "no JS lint/type/test adapter is claimed",
            not {"eslint", "tsc", "jest", "vitest"} & set(plan),
            f"checks={sorted(plan)}",
        )
        r = self.arx("architecture", "diagram", str(s2), "--format", "mermaid")
        self.check(
            "AC-3",
            "S2",
            "declared-dependency edges labelled inferred",
            "(inferred)" in r.stdout,
            f"{r.stdout.count('(inferred)')} inferred edges",
        )

    def mixed_monorepo(self) -> None:
        s3 = self.repo("s3-mixed", "mixed-monorepo")
        inv = self.inventory(
            "S3",
            s3,
            {
                "framework:FastAPI",
                "framework:React",
                "monorepo:npm/yarn workspaces",
                "test:Vitest",
                "test:pytest",
                "container:Docker Compose",
            },
            {"framework:Flask"},
        )
        projects = {p["path"]: p["ecosystems"] for p in inv.get("projects", [])}
        self.check(
            "AC-3",
            "S3",
            "three projects with correct ecosystems",
            projects
            == {".": ["javascript"], "apps/web": ["javascript"], "services/api": ["python"]},
            str(projects),
        )
        r = self.arx("architecture", "diagram", str(s3), "--python-package", "services/api/api")
        self.check(
            "AC-3",
            "S3",
            "Python import graph has a verified edge",
            "verified (static import)" in r.stdout,
            "api.main -> api.models",
        )
        if shutil.which("gitleaks"):
            report = self.run("S3", s3, "gitleaks", "s3-gitleaks")
            if report:
                e = self.execution(report, "gitleaks")
                self.check(
                    "AC-6",
                    "S3",
                    "real gitleaks clean on the fixture",
                    e["outcome"] == "clean",
                    e["outcome_detail"],
                )
        else:
            self.skip("AC-6", "S3", "real gitleaks clean on the fixture", "gitleaks not on PATH")

    def unsupported_stack(self) -> None:
        s4 = self.repo(
            "s4-go",
            None,
            {
                "go.mod": "module example.com/svc\n\ngo 1.22\n\n"
                "require github.com/gin-gonic/gin v1.9.0\n",
                "main.go": "package main\n\nfunc main() {}\n",
            },
        )
        inv = self.inventory("S4", s4, set(), {"framework:Gin"})
        languages = [lang["name"] for lang in inv.get("languages", [])]
        frameworks = [d["name"] for d in inv.get("detections", []) if d["category"] == "framework"]
        self.check(
            "AC-10",
            "S4",
            "Go counted as a language, no framework claimed",
            languages == ["Go"] and not frameworks,
            f"languages={languages}",
        )
        self.check(
            "AC-10",
            "S4",
            "limitations state the static-only scope",
            any("Static inspection" in x for x in inv.get("limitations", [])),
            "present",
        )

    def agent_context(self) -> None:
        proj = self.repo("s5-agents", "python-service")
        (proj / "docs").mkdir(exist_ok=True)
        shutil.copy(
            REPO / "examples" / "requirements" / "ledger.json", proj / "docs" / "requirements.json"
        )
        dry = self.arx("agents", "init", str(proj))
        self.check(
            "AC-12",
            "S1",
            "agents init is a dry run by default",
            dry.returncode == 0 and not (proj / ".ai").exists(),
            f"exit {dry.returncode}",
        )
        denied = self.arx("agents", "init", str(proj), "--apply")
        self.check(
            "AC-12",
            "S1",
            "writing needs --allow-source-writes",
            denied.returncode == 3,
            f"exit {denied.returncode}",
        )
        write = ["--apply", "--allow-source-writes"]
        r = self.arx("agents", "init", str(proj), *write)
        skill = "example-python-service-requirements"
        self.check(
            "AC-12",
            "S1",
            "init drafts instructions and a requirements skill",
            r.returncode == 0
            and (proj / ".ai" / "instructions.md").is_file()
            and (proj / ".ai" / "skills" / skill / "SKILL.md").is_file(),
            f"exit {r.returncode}",
        )
        r = self.arx("agents", "sync", str(proj), *write)
        agents_md = proj / "AGENTS.md"
        valid = all(
            self.arx("skill", "validate", str(proj / base / skill)).returncode == 0
            for base in (".claude/skills", ".agents/skills")
        )
        self.check(
            "AC-12",
            "S1",
            "sync writes AGENTS.md, CLAUDE.md import and valid skills",
            r.returncode == 0
            and agents_md.is_file()
            and "@AGENTS.md" in (proj / "CLAUDE.md").read_text()
            and valid,
            f"exit {r.returncode}, skills valid={valid}",
        )
        r = self.arx("agents", "sync", str(proj), "--check")
        self.check(
            "AC-12",
            "S1",
            "--check reports up to date after sync",
            r.returncode == 0,
            f"exit {r.returncode}",
        )
        agents_md.write_text(agents_md.read_text() + "hand edit\n")
        r = self.arx("agents", "sync", str(proj), *write)
        self.check(
            "AC-12",
            "S1",
            "hand-edited output is protected",
            r.returncode == 3 and agents_md.read_text().endswith("hand edit\n"),
            f"exit {r.returncode}",
        )

    def installer(self) -> None:
        home, proj = self.work / "home", self.work / "proj"
        proj.mkdir(exist_ok=True)
        args = ["--assistant", "claude", "--scope", "project", "--apply"]
        r = self.arx("install", *args, "--project-dir", str(proj), env={"HOME": str(home)})
        target = proj / ".claude" / "skills" / "archonix"
        self.check(
            "AC-9",
            "-",
            "project install writes a valid skill",
            r.returncode == 0 and self.arx("skill", "validate", str(target)).returncode == 0,
            f"exit {r.returncode}",
        )
        r = self.arx("uninstall", *args, "--project-dir", str(proj), env={"HOME": str(home)})
        self.check(
            "AC-9",
            "-",
            "uninstall removes managed files",
            r.returncode == 0 and not target.exists(),
            f"exit {r.returncode}",
        )
        evil, elsewhere = self.work / "evil", self.work / "elsewhere"
        (evil / ".claude").mkdir(parents=True, exist_ok=True)
        elsewhere.mkdir(exist_ok=True)
        if not (evil / ".claude" / "skills").exists():
            (evil / ".claude" / "skills").symlink_to(elsewhere, target_is_directory=True)
        r = self.arx("install", *args, "--project-dir", str(evil), env={"HOME": str(home)})
        self.check(
            "AC-9",
            "-",
            "symlinked project skills directory refused",
            r.returncode == 3 and not any(elsewhere.iterdir()),
            f"exit {r.returncode}",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archonix", required=True, help="path to the installed archonix CLI")
    parser.add_argument("--work", help="working directory (default: a new temporary directory)")
    parser.add_argument("--json-out", help="write results as JSON to this file")
    args = parser.parse_args()
    if os.name != "posix":
        print("acceptance suite requires a POSIX system (symlinks, shell fake tools)")
        return 2
    work = Path(args.work or tempfile.mkdtemp(prefix="archonix-acceptance-")).resolve()
    work.mkdir(parents=True, exist_ok=True)
    suite = Suite(args.archonix, work, REPO / "examples")
    for step in (
        suite.install_and_resources,
        suite.requirements,
        suite.python_service,
        suite.readiness,
        suite.typescript_app,
        suite.mixed_monorepo,
        suite.unsupported_stack,
        suite.agent_context,
        suite.installer,
    ):
        step()
    counts = {s: sum(r["status"] == s for r in suite.results) for s in ("PASS", "FAIL", "SKIP")}
    print(
        f"\n{counts['PASS']} passed, {counts['FAIL']} failed, {counts['SKIP']} skipped "
        f"of {len(suite.results)} checks"
    )
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"counts": counts, "results": suite.results}, indent=1) + "\n"
        )
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
