"""Claude Code acceptance run for the Archonix skill (opt-in; uses your Claude account).

Builds a disposable git project from ``examples/python-service`` with a seeded rounding
bug, installs the skill with ``archonix install --scope project``, and runs four fixed
tasks through ``claude -p`` with a restricted tool allowlist. Each task starts from a
clean checkout. Results are derived from the stream-json transcript, git state and an
independent CLI re-check, never from the assistant's own claims alone.

    python acceptance/claude_code.py --archonix "$(command -v archonix)" \\
        --yes-send-fixtures-to-anthropic --out acceptance-results/

The fixture is synthetic and already public in this repository; it is sent to Anthropic
as part of the run. Do not point this script at private code.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IDENT = ["-c", "user.name=Acceptance", "-c", "user.email=acceptance@example.invalid"]
READ_ONLY = [
    "Read",
    "Glob",
    "Grep",
    "Skill",
    "Bash(archonix:*)",
    "Bash(git status:*)",
    "Bash(git log:*)",
    "Bash(git diff:*)",
    "Bash(ls:*)",
]
NO_WRITE = ["Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch", "Agent"]

TASKS: dict[str, dict] = {
    "T1-understand": {
        "prompt": "Use Archonix to help me understand this repository: its purpose, stack, "
        "structure, how to test it, and main risks. Do not modify any files.",
        "allowed": READ_ONLY,
        "disallowed": NO_WRITE,
        "expect": {"references": ["repository-understanding.md"], "changes": "none"},
    },
    "T2-discover": {
        "prompt": "I want to add a maximum discount cap for VIP customers. Use Archonix to "
        "discover the requirements before any implementation. Do not write code or "
        "modify files; present the requirements and open questions in your reply.",
        "allowed": READ_ONLY,
        "disallowed": NO_WRITE,
        "expect": {"references": ["discovery.md"], "changes": "none"},
    },
    "T3-bugfix": {
        "prompt": "Bug report: apply_discount(Decimal('10.005'), 0) returns 10.00 but it should "
        "round half-up to 10.01. Fix it using Archonix's bug-investigation workflow. "
        "This project is trusted: you may run its tests.",
        # Generic `python3 -m pytest` is deliberately not allowed: the skill must lead the
        # assistant to the permitted, evidence-producing CLI path.
        "allowed": [*READ_ONLY, "Edit", "Write"],
        "disallowed": ["WebFetch", "WebSearch", "Agent"],
        "expect": {
            "references": ["bug-investigation.md"],
            "changes": "app/ and tests/ only",
            "verified_with_cli": True,
        },
    },
    "T4-release": {
        "prompt": "Use Archonix to assess whether this repository is ready to release. This "
        "project is trusted: you may run its tests. Do not modify any files.",
        "allowed": READ_ONLY,
        "disallowed": NO_WRITE,
        "expect": {
            "references": ["release-readiness.md"],
            "changes": "none",
            "verdict": "not-ready",
        },
    },
}


def sh(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False, env=env).stdout


def build_project(work: Path, archonix: str) -> Path:
    project = work / "project"
    shutil.copytree(REPO / "examples" / "python-service", project)
    pricing = project / "app" / "pricing.py"
    pricing.write_text(pricing.read_text().replace("ROUND_HALF_UP", "ROUND_DOWN"))
    sh(["git", *IDENT, "init", "-q", "-b", "main"], project)
    sh(["git", *IDENT, "add", "-A"], project)
    sh(["git", *IDENT, "commit", "-q", "-m", "fixture with seeded rounding bug"], project)
    env = {**os.environ, "HOME": str(work / "home")}
    subprocess.run(
        [
            archonix,
            "install",
            "--assistant",
            "claude",
            "--scope",
            "project",
            "--project-dir",
            str(project),
            "--apply",
        ],
        check=True,
        env=env,
        capture_output=True,
    )
    sh(["git", *IDENT, "add", "-A"], project)
    sh(["git", *IDENT, "commit", "-q", "-m", "install archonix skill"], project)
    return project


def classify_out_dir(path: str, project: Path) -> str:
    p = Path(path)
    resolved = (p if p.is_absolute() else project / p).resolve()
    if resolved.is_relative_to(project.resolve() / ".archonix"):
        return "inside .archonix/"
    if resolved.is_relative_to(project.resolve()):
        return "inside repository (not .archonix/)"
    temp_roots = {Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve()}  # noqa: S108
    if any(resolved.is_relative_to(t) for t in temp_roots) and not resolved.is_relative_to(
        project.resolve().parent.parent
    ):
        return "temporary directory"
    return "other location"


def analyse(events: list[dict], project: Path) -> dict:
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    denied = {d.get("tool_use_id") for d in result.get("permission_denials", [])}
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
    uses = [
        b
        for e in events
        if e.get("type") == "assistant"
        for b in e["message"].get("content", [])
        if b.get("type") == "tool_use"
    ]
    executed = [u for u in uses if u.get("id") not in denied]
    text_of = [json.dumps(u.get("input", {})) for u in executed]
    references = sorted({m for t in text_of for m in re.findall(r"references/([a-z-]+\.md)", t)})
    commands = [u["input"].get("command", "") for u in executed if u["name"] == "Bash"]
    archonix_cmds = [c for c in commands if re.search(r"(^|[;&|]\s*)archonix ", c)]
    out_dirs = [m for c in archonix_cmds for m in re.findall(r"--out-dir[ =](\S+)", c)]
    return {
        "model": init.get("model"),
        "skill_listed": "archonix" in json.dumps(init.get("skills") or init.get("slash_commands")),
        "skill_invoked": any(
            u["name"] == "Skill" and "archonix" in json.dumps(u["input"]) for u in executed
        ),
        "references_loaded": references,
        "archonix_commands": archonix_cmds,
        "out_dirs": [{"path": d, "kind": classify_out_dir(d, project)} for d in out_dirs],
        "tested_with_cli": any(
            "--checks" in c and "pytest" in c and "--allow-repo-code" in c for c in archonix_cmds
        ),
        "denied_count": len(denied),
        "turns": result.get("num_turns"),
        "final_text": result.get("result", ""),
    }


def score(
    name: str, task: dict, a: dict, changed: list[str], recheck: dict | None
) -> tuple[str, list[str]]:
    exp, problems = task["expect"], []
    if not a["skill_invoked"]:
        problems.append("skill not invoked")
    missing = [r for r in exp["references"] if r not in a["references_loaded"]]
    if missing:
        problems.append(f"expected reference not loaded: {missing}")
    if exp["changes"] == "none" and changed:
        problems.append(f"files changed: {changed}")
    if exp["changes"].startswith("app/") and any(
        not (c.split()[-1].startswith(("app/", "tests/"))) for c in changed
    ):
        problems.append(f"unexpected files changed: {changed}")
    if any(d["kind"] == "other location" for d in a["out_dirs"]):
        problems.append(f"report written to an invented location: {a['out_dirs']}")
    if exp.get("verified_with_cli") and not a["tested_with_cli"]:
        problems.append("fix not verified through the CLI")
    if recheck is not None and recheck.get("outcome") != "clean":
        problems.append(f"independent re-check failed: {recheck}")
    if exp.get("verdict") and not re.search(r"not[ -]ready", a["final_text"], re.IGNORECASE):
        problems.append("final answer does not report the not-ready verdict")
    if not problems:
        return "PASS", []
    fatal = {"skill not invoked"}
    return ("FAIL" if fatal & set(problems) else "PARTIAL"), problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archonix", required=True)
    parser.add_argument("--tools-path", default="", help="extra PATH entries (e.g. a venv bin)")
    parser.add_argument("--tasks", default=",".join(TASKS))
    parser.add_argument("--out", required=True, help="directory for sanitized summaries")
    parser.add_argument(
        "--yes-send-fixtures-to-anthropic",
        action="store_true",
        required=True,
        help="confirm that the synthetic fixture may be sent to Anthropic",
    )
    args = parser.parse_args()
    if shutil.which("claude") is None:
        print("claude (Claude Code CLI) is not installed; nothing was tested")
        return 2
    version = sh(["claude", "--version"], Path.cwd()).strip()
    work = Path(tempfile.mkdtemp(prefix="archonix-claude-")).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    project = build_project(work, args.archonix)
    path = os.pathsep.join(
        p for p in (str(Path(args.archonix).parent), args.tools_path, os.environ["PATH"]) if p
    )
    rows = []
    for name in args.tasks.split(","):
        task = TASKS[name]
        sh(["git", "reset", "-q", "--hard"], project)
        sh(["git", "clean", "-qfdx", "-e", ".claude"], project)
        cmd = [
            "claude",
            "-p",
            task["prompt"],
            "--output-format",
            "stream-json",
            "--verbose",
            "--setting-sources",
            "project",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--max-turns",
            "40",
            "--allowedTools",
            *task["allowed"],
            "--disallowedTools",
            *task["disallowed"],
        ]
        proc = subprocess.run(
            cmd,
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
            timeout=1800,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "PATH": path},
        )
        events = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        a = analyse(events, project)
        changed = [
            line
            for line in sh(["git", "status", "--porcelain"], project).splitlines()
            if ".archonix/" not in line
        ]
        recheck = None
        if task["expect"].get("verified_with_cli"):
            r = subprocess.run(
                [
                    args.archonix,
                    "check",
                    "run",
                    ".",
                    "--mode",
                    "audit",
                    "--allow-repo-code",
                    "--checks",
                    "pytest",
                    "--format",
                    "json",
                ],
                cwd=project,
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": path},
            )
            ex = json.loads(r.stdout)["executions"][0] if r.stdout else {}
            recheck = {"outcome": ex.get("outcome"), "test_totals": ex.get("test_totals")}
        verdict, problems = score(name, task, a, changed, recheck)
        summary = {
            "task": name,
            "claude_code_version": version,
            "verdict": verdict,
            "problems": problems,
            "files_changed": changed,
            "independent_recheck": recheck,
            "diff": sh(["git", "diff"], project)[:4000],
            **a,
        }
        text = json.dumps(summary, indent=1)
        for secret_path in (str(work), str(Path.home()), str(REPO)):
            text = text.replace(secret_path, "<redacted-path>")
        (out / f"{name}.json").write_text(text + "\n")
        rows.append((name, verdict, problems))
        print(f"{name}: {verdict} {problems or ''}")
    shutil.rmtree(work, ignore_errors=True)
    passed = sum(v == "PASS" for _, v, _ in rows)
    print(f"\n{passed} of {len(rows)} tasks passed ({version})")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
