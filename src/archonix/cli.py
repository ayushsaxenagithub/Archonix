"""Command-line interface.

Exit codes: 0 success; 1 negative result (validation failed, not ready, --fail-on
threshold reached); 2 usage error; 3 refused by policy or conflict; 4 incomplete or
unknown result (readiness incomplete, or a check failed with --fail-on-error).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .adapters import ADAPTERS
from .config import Settings, load_settings
from .errors import ArchonixError, PolicyError, ValidationFailed
from .findings import SEVERITIES
from .policy import WriteGuard

EXIT_OK, EXIT_NEGATIVE, EXIT_USAGE, EXIT_POLICY, EXIT_INCOMPLETE = 0, 1, 2, 3, 4


# ---------------------------------------------------------------- helpers


def _dump(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def _no_repo_symlinks(target: Path, root: Path) -> None:
    """Refuse an output path that passes through a symlink inside the scanned repository.

    The repository is untrusted input: a committed symlink such as ``.archonix -> ../x``
    would otherwise redirect reports and artifacts outside it. Symlinks outside the
    repository (for example macOS ``/tmp`` or the user's own links) are not affected.
    """
    root_real = Path(os.path.realpath(root))
    current = Path(os.path.abspath(target))
    for candidate in (current, *current.parents):
        if not candidate.is_symlink():
            continue
        location = Path(os.path.realpath(candidate.parent)) / candidate.name
        if location.is_relative_to(root_real):
            raise PolicyError(
                f"refusing to write through {candidate}: it is a symlink inside the scanned "
                "repository (repository content is untrusted); choose a directory outside the "
                "repository, for example a fresh temporary directory"
            )


def _emit(
    text: str,
    out: Path | None,
    settings: Settings | None = None,
    overwrite: bool = False,
    root: Path | None = None,
) -> None:
    if out is None:
        sys.stdout.write(text)
        return
    if root is not None:
        _no_repo_symlinks(out, root)
    if settings is not None and not settings.permissions.artifact_writes:
        raise PolicyError("artifact writes are disabled by configuration")
    path = WriteGuard([out.parent], overwrite=overwrite).write_text(out, text)
    print(f"wrote {path}", file=sys.stderr)


def _root(path: str) -> Path:
    root = Path(path).resolve()
    if not root.is_dir():
        raise ArchonixError(f"{path} is not a directory")
    return root


def _settings(args: argparse.Namespace, root: Path | None) -> Settings:
    perms = {}
    for flag, name in (
        ("allow_tools", "external_tools"),
        ("allow_repo_code", "repo_code"),
        ("allow_network", "network"),
    ):
        if getattr(args, flag, False):
            perms[name] = True
    settings = load_settings(
        root,
        mode=getattr(args, "mode", "discovery") or "discovery",
        explicit_config=Path(args.config) if getattr(args, "config", None) else None,
        cli_permissions=perms,
        cli_overrides={
            "timeout_seconds": getattr(args, "timeout", None),
            "max_output_bytes": getattr(args, "max_output_bytes", None),
        },
        use_repo_config=not getattr(args, "no_repo_config", False),
    )
    for pattern in getattr(args, "exclude", None) or []:
        if pattern not in settings.exclude:
            settings.exclude.append(pattern)
    if getattr(args, "max_files", None):
        settings.max_files = args.max_files
    return settings


def _load(path: str) -> Any:
    from .schemas import load_json

    return load_json(Path(path))


# ---------------------------------------------------------------- commands


def cmd_inventory(args: argparse.Namespace) -> int:
    from .inventory import build_inventory, render_markdown

    root = _root(args.path)
    settings = _settings(args, root)
    inv = build_inventory(root, settings)
    _emit(
        _dump(inv) if args.format == "json" else render_markdown(inv),
        Path(args.out) if args.out else None,
        settings,
        args.overwrite,
        root,
    )
    return EXIT_OK


def cmd_tools(args: argparse.Namespace) -> int:
    from .tools import detect_tools

    tools = detect_tools(versions=args.versions)
    if args.format == "json":
        sys.stdout.write(_dump(tools))
    else:
        print("| Tool | Available | Version | Purpose |\n|---|---|---|---|")
        for t in tools:
            version = t["version"] or ("not checked" if not args.versions else "unknown")
            print(
                f"| {t['name']} | {'yes' if t['available'] else 'no'} | "
                f"{version if t['available'] else '—'} | {t['purpose']} |"
            )
    return EXIT_OK


def cmd_config_show(args: argparse.Namespace) -> int:
    root = _root(args.path)
    s = _settings(args, root)
    data = {
        "mode": s.mode,
        "permissions": s.permissions.as_dict(),
        "execution": {
            "timeout_seconds": s.timeout_seconds,
            "max_output_bytes": s.max_output_bytes,
            "env_passthrough": s.env_passthrough,
        },
        "inventory": {
            "exclude": s.exclude,
            "max_files": s.max_files,
            "max_file_bytes": s.max_file_bytes,
        },
        "checks": {k: vars(v) for k, v in s.checks.items()},
        "sources": dict(sorted(s.sources.items())),
        "ignored": s.ignored,
        "files_loaded": s.files_loaded,
    }
    sys.stdout.write(_dump(data))
    return EXIT_OK


def cmd_requirements_validate(args: argparse.Namespace) -> int:
    from .requirements import validate_ledger

    result = validate_ledger(_load(args.file))
    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in result.errors:
        print(f"error: {e}", file=sys.stderr)
    if result.ok:
        print(f"{args.file}: valid requirements ledger ({len(result.warnings)} warning(s))")
        return EXIT_OK
    return EXIT_NEGATIVE


def cmd_requirements_matrix(args: argparse.Namespace) -> int:
    from .requirements import (
        collect_cases,
        orphan_tests,
        render_matrix,
        traceability,
        validate_ledger,
    )
    from .schemas import validate
    from .testcases import parse_junit_cases

    ledger = _load(args.file)
    result = validate_ledger(ledger)
    if not result.ok:
        for e in result.errors:
            print(f"error: {e}", file=sys.stderr)
        return EXIT_NEGATIVE
    reports = []
    for path in args.report or []:
        doc = _load(path)
        validate(doc, "workflow-report")
        reports.append(doc)
    junit = []
    for path in args.junit or []:
        try:
            cases, truncated = parse_junit_cases(Path(path))
        except ValueError as exc:
            raise ValidationFailed(str(exc)) from exc
        if truncated:
            print(f"warning: {path}: only the first test cases were read", file=sys.stderr)
        junit.append((Path(path).name, [c.as_dict() for c in cases]))
    rows = traceability(ledger, reports, junit)
    for orphan in orphan_tests(ledger, collect_cases(reports, junit)):
        print(
            f"warning: test references an acceptance criterion not in the ledger: {orphan}",
            file=sys.stderr,
        )
    _emit(
        _dump(rows) if args.format == "json" else render_matrix(rows),
        Path(args.out) if args.out else None,
        overwrite=args.overwrite,
    )
    return EXIT_OK


def cmd_tests_scaffold(args: argparse.Namespace) -> int:
    from .testplan import scaffold

    root = _root(args.path)
    plan = scaffold(
        root,
        framework=args.framework,
        ledger_path=Path(args.ledger) if args.ledger else None,
        out_dir=args.out_dir,
        typescript=args.typescript,
        failing=args.failing,
        allow_source_writes=args.allow_source_writes,
        apply=args.apply,
    )
    verb = "created" if plan.written else "would create"
    for action, rel, count in plan.files:
        label = verb if action == "create" else "exists, left unchanged:"
        print(f"{label} {rel} ({count} stub(s))")
    for note in plan.notes:
        print(f"note: {note}")
    if not plan.files:
        print("nothing to scaffold: no requirement with acceptance criteria")
    elif not args.apply:
        print("dry run: re-run with --apply --allow-source-writes to write these files")
    return EXIT_OK


def cmd_check_list(args: argparse.Namespace) -> int:
    rows = [a.describe() for a in ADAPTERS.values()]
    if args.format == "json":
        sys.stdout.write(_dump(rows))
        return EXIT_OK
    print("| Check | Tool | Category | Repo code | Network | Status |\n|---|---|---|---|---|---|")
    for r in rows:
        req = r["requires"]
        print(
            f"| {r['id']} | {r['tool']} | {r['category']} | {'yes' if req['repo_code'] else 'no'} "
            f"| {'yes' if req['network'] else 'no'} | {r['status']} |"
        )
    return EXIT_OK


def _checks_arg(value: str | None) -> list[str] | None:
    return [c.strip() for c in value.split(",") if c.strip()] if value else None


def cmd_check_plan(args: argparse.Namespace) -> int:
    from .checks import plan_checks
    from .inventory import build_inventory

    root = _root(args.path)
    settings = _settings(args, root)
    plans = plan_checks(root, build_inventory(root, settings), settings, _checks_arg(args.checks))
    if args.format == "json":
        sys.stdout.write(
            _dump(
                {
                    "mode": settings.mode,
                    "permissions": settings.permissions.as_dict(),
                    "ignored_settings": settings.ignored,
                    "checks": [p.as_dict() for p in plans],
                }
            )
        )
        return EXIT_OK
    print(f"Plan for {root} (mode: {settings.mode}; nothing has been executed)\n")
    for p in plans:
        print(f"[{p.action:5}] {p.adapter.id}: {p.reason}")
        if p.action == "run":
            print(f"        $ {' '.join(p.argv_preview)}")
    for note in settings.ignored:
        print(f"\nignored: {note}")
    return EXIT_OK


def cmd_check_run(args: argparse.Namespace) -> int:
    from .checks import execute_plan, plan_checks
    from .inventory import build_inventory
    from .redact import Redactor
    from .report import build_workflow_report, render_workflow_report
    from .schemas import validate

    root = _root(args.path)
    settings = _settings(args, root)
    if args.out_dir:
        _no_repo_symlinks(Path(args.out_dir), root)
    out_dir = Path(args.out_dir).resolve() if args.out_dir else None
    if out_dir is not None:
        if not settings.permissions.artifact_writes:
            raise PolicyError("artifact writes are disabled by configuration")
        if out_dir.exists() and any(out_dir.iterdir()) and not args.overwrite:
            raise PolicyError(f"{out_dir} is not empty; choose a new directory or pass --overwrite")
        out_dir.mkdir(parents=True, exist_ok=True)
    inv = build_inventory(root, settings)
    plans = plan_checks(root, inv, settings, _checks_arg(args.checks))
    redactor = Redactor.from_environment(
        sensitive_env_names=settings.sensitive_env_names,
        extra_patterns=settings.extra_redaction_patterns,
    )
    executions, findings, skipped = execute_plan(
        root, plans, settings, artifact_dir=out_dir, redactor=redactor
    )
    report = build_workflow_report(
        workflow=args.workflow,
        root=str(root),
        settings=settings,
        inventory=inv,
        repository=inv["repository"],
        executions=executions,
        findings=findings,
        skipped=skipped,
        requested_checks=_checks_arg(args.checks),
        example=args.label_example,
    )
    validate(report, "workflow-report")
    markdown = render_workflow_report(report)
    if out_dir is not None:
        guard = WriteGuard([out_dir], overwrite=args.overwrite)
        guard.write_text(out_dir / "report.json", _dump(report))
        guard.write_text(out_dir / "report.md", markdown)
        print(f"wrote {out_dir / 'report.json'} and {out_dir / 'report.md'}", file=sys.stderr)
    else:
        sys.stdout.write(_dump(report) if args.format == "json" else markdown)
    if args.fail_on:
        limit = SEVERITIES.index(args.fail_on)
        if any(
            f["severity"] != "unknown" and SEVERITIES.index(f["severity"]) <= limit
            for f in report["findings"]
        ):
            return EXIT_NEGATIVE
    if args.fail_on_error and report["summary"]["failed"]:
        return EXIT_INCOMPLETE
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    from .schemas import validate

    doc = _load(args.file)
    name = validate(doc, args.schema)
    print(f"{args.file}: valid against {name} schema")
    return EXIT_OK


def cmd_render(args: argparse.Namespace) -> int:
    from .report import render_any
    from .schemas import validate

    doc = _load(args.file)
    validate(doc)
    _emit(render_any(doc), Path(args.out) if args.out else None, overwrite=args.overwrite)
    return EXIT_OK


def cmd_schema_list(args: argparse.Namespace) -> int:
    from .schemas import schema_names

    print("\n".join(schema_names()))
    return EXIT_OK


def cmd_readiness(args: argparse.Namespace) -> int:
    from .readiness import assess, load_policy
    from .report import render_readiness
    from .requirements import validate_ledger
    from .schemas import validate

    policy, source = load_policy(Path(args.policy) if args.policy else None)
    reports = []
    for path in args.report or []:
        doc = _load(path)
        validate(doc, "workflow-report")
        reports.append((path, doc))
    ledger = None
    if args.ledger:
        doc = _load(args.ledger)
        result = validate_ledger(doc)
        if not result.ok:
            raise ValidationFailed(
                "requirements ledger is invalid:\n  " + "\n  ".join(result.errors)
            )
        ledger = (args.ledger, doc)
    assessment = assess(policy, source, reports, ledger)
    if args.label_example:
        assessment["example"] = True
    validate(assessment, "release-readiness")
    _emit(
        _dump(assessment) if args.format == "json" else render_readiness(assessment),
        Path(args.out) if args.out else None,
        overwrite=args.overwrite,
    )
    return {"ready": EXIT_OK, "not-ready": EXIT_NEGATIVE}.get(
        assessment["verdict"], EXIT_INCOMPLETE
    )


def cmd_architecture(args: argparse.Namespace) -> int:
    from .architecture import inventory_diagram, python_import_graph, render_diagram_markdown
    from .inventory import build_inventory

    root = _root(args.path)
    if args.python_package:
        pkg = (root / args.python_package).resolve()
        if not pkg.is_relative_to(root):
            raise PolicyError("--python-package must be inside the repository")
        try:
            mermaid, evidence, limitations = python_import_graph(pkg, depth=args.depth)
        except ValueError as exc:
            raise ArchonixError(str(exc)) from exc
        title = f"Module dependencies: {pkg.name}"
    else:
        settings = _settings(args, root)
        inv = build_inventory(root, settings)
        mermaid, evidence = inventory_diagram(inv)
        limitations = inv["limitations"]
        title = "System context (inventory-derived)"
    text = (
        mermaid
        if args.format == "mermaid"
        else render_diagram_markdown(title, mermaid, evidence, limitations)
    )
    _emit(text, Path(args.out) if args.out else None, overwrite=args.overwrite, root=root)
    return EXIT_OK


def cmd_docs_list(args: argparse.Namespace) -> int:
    from .docsinit import TEMPLATE_SETS

    for name, items in TEMPLATE_SETS.items():
        print(f"{name}: {', '.join(dest for _, dest in items)}")
    return EXIT_OK


def _print_agents_plan(plan: Any, applied_verb: str, hint: str) -> None:
    for action, rel in plan.actions:
        if action != "unchanged":
            print(f"{action:13} {rel}")
    unchanged = sum(1 for a, _ in plan.actions if a == "unchanged")
    if unchanged:
        print(f"{'unchanged':13} {unchanged} file(s)")
    for note in plan.notes:
        print(f"note: {note}")
    for conflict in plan.conflicts:
        print(f"conflict: {conflict}", file=sys.stderr)
    if plan.applied:
        print(applied_verb)
    elif not plan.conflicts:
        print(hint)


def cmd_agents_init(args: argparse.Namespace) -> int:
    from .agents import init

    root = _root(args.path)
    plan = init(
        root, _settings(args, root), allow_source_writes=args.allow_source_writes, apply=args.apply
    )
    _print_agents_plan(
        plan,
        "drafted .ai/; review it, then run `archonix agents sync`",
        "dry run: re-run with --apply --allow-source-writes to write .ai/",
    )
    return EXIT_POLICY if plan.conflicts else EXIT_OK


def cmd_agents_sync(args: argparse.Namespace) -> int:
    from .agents import out_of_date, sync

    root = _root(args.path)
    targets = tuple(t.strip() for t in args.target.split(",") if t.strip())
    plan = sync(
        root,
        targets=targets,
        allow_source_writes=args.allow_source_writes,
        apply=args.apply and not args.check,
    )
    if args.check:
        stale = out_of_date(plan)
        _print_agents_plan(
            plan,
            "",
            "agent context is up to date"
            if not stale
            else "agent context is out of date: run `archonix agents sync --apply "
            "--allow-source-writes`",
        )
        return EXIT_NEGATIVE if stale else EXIT_OK
    _print_agents_plan(
        plan,
        "synced agent context from .ai/",
        "dry run: re-run with --apply --allow-source-writes to write these files",
    )
    return EXIT_POLICY if plan.conflicts else EXIT_OK


def cmd_docs_init(args: argparse.Namespace) -> int:
    from .docsinit import init_docs

    root = _root(args.path)
    plan = init_docs(
        root,
        args.set,
        project=args.project or root.name,
        allow_source_writes=args.allow_source_writes,
        apply=args.apply,
    )
    verb = "created" if plan.written else "would create"
    for p in plan.create:
        print(f"{verb}: {p}")
    for p in plan.exists:
        print(f"exists, left unchanged: {p}")
    if not args.apply:
        print("dry run: re-run with --apply --allow-source-writes to write these files")
    return EXIT_OK


def cmd_perf_endpoints(args: argparse.Namespace) -> int:
    from .perf import openapi_endpoints

    rows = openapi_endpoints(Path(args.spec))
    if args.format == "json":
        sys.stdout.write(_dump(rows))
    else:
        print("| Method | Path | Auth | Smoke candidate | Note |\n|---|---|---|---|---|")
        for r in rows:
            print(
                f"| {r['method']} | {r['path']} | {'yes' if r['requires_auth'] else 'no'} | "
                f"{'yes' if r['smoke_candidate'] else 'no'} | {r['note']} |"
            )
    return EXIT_OK


def cmd_perf_smoke(args: argparse.Namespace) -> int:
    from .perf import smoke
    from .report import render_performance
    from .schemas import validate

    if not args.allow_network:
        raise PolicyError("perf smoke sends HTTP requests; pass --allow-network to confirm")
    report = smoke(
        base_url=args.base_url,
        paths=args.path,
        method=args.method,
        requests=args.requests,
        concurrency=args.concurrency,
        warmup=args.warmup,
        timeout=args.timeout,
        authorized_host=args.authorized_host,
        auth_header_env=args.auth_header_env,
        p95_ms=args.p95_ms,
        max_error_rate=args.max_error_rate,
        revision=args.revision,
        environment=args.environment,
    )
    if args.label_example:
        report["example"] = True
    validate(report, "performance-report")
    _emit(
        _dump(report) if args.format == "json" else render_performance(report),
        Path(args.out) if args.out else None,
        overwrite=args.overwrite,
    )
    if any(e["threshold"]["result"] == "fail" for e in report["endpoints"]):
        return EXIT_NEGATIVE
    return EXIT_OK


def cmd_perf_k6(args: argparse.Namespace) -> int:
    from .perf import k6_script

    _emit(
        k6_script(
            args.base_url,
            args.path,
            vus=args.vus,
            duration=args.duration,
            p95_ms=args.p95_ms,
            max_error_rate=args.max_error_rate,
        ),
        Path(args.out) if args.out else None,
        overwrite=args.overwrite,
    )
    return EXIT_OK


def _print_plan(plan: Any, verb: str) -> None:
    for action, rel in plan.actions:
        if action != "unchanged":
            print(f"{action:13} {rel}")
    unchanged = sum(1 for a, _ in plan.actions if a == "unchanged")
    if unchanged:
        print(f"{'unchanged':13} {unchanged} file(s)")
    for c in plan.conflicts:
        print(f"conflict: {c}", file=sys.stderr)
    if plan.applied:
        print(f"{verb} {plan.target}")
    elif not plan.conflicts:
        print(f"dry run for {plan.target}: re-run with --apply to make these changes")


def cmd_install(args: argparse.Namespace) -> int:
    from .install import install

    plan = install(
        args.assistant,
        args.scope,
        home=Path.home(),
        project_dir=Path(args.project_dir) if args.project_dir else None,
        apply=args.apply,
    )
    _print_plan(plan, "installed into")
    return EXIT_POLICY if plan.conflicts else EXIT_OK


def cmd_uninstall(args: argparse.Namespace) -> int:
    from .install import uninstall

    plan = uninstall(
        args.assistant,
        args.scope,
        home=Path.home(),
        project_dir=Path(args.project_dir) if args.project_dir else None,
        apply=args.apply,
    )
    _print_plan(plan, "removed Archonix-managed files from")
    return EXIT_POLICY if plan.conflicts else EXIT_OK


def cmd_skill_validate(args: argparse.Namespace) -> int:
    from .install import validate_skill
    from .resources import skill_root

    target = Path(args.path) if args.path else skill_root()
    problems = validate_skill(target)
    blocking = [p for p in problems if "(informational)" not in p]
    for p in problems:
        print(f"{'warning' if p not in blocking else 'error'}: {p}", file=sys.stderr)
    if blocking:
        return EXIT_NEGATIVE
    print(f"{target}: valid skill")
    return EXIT_OK


def cmd_skill_path(args: argparse.Namespace) -> int:
    from .resources import skill_root

    print(skill_root())
    return EXIT_OK


# ---------------------------------------------------------------- parser


def _add_common(p: argparse.ArgumentParser, *, execution: bool = False) -> None:
    p.add_argument("--config", help="trusted config file (may grant permissions)")
    p.add_argument(
        "--no-repo-config", action="store_true", help="ignore archonix.toml in the repository"
    )
    p.add_argument("--exclude", action="append", metavar="GLOB", help="additional exclusion")
    p.add_argument("--max-files", type=int, help="stop scanning after this many files")
    p.add_argument(
        "--mode",
        choices=["discovery", "implementation", "audit"],
        default="discovery",
        help="workflow mode supplying permission defaults (default: discovery)",
    )
    p.add_argument("--allow-tools", action="store_true", help="permit launching external tools")
    if execution:
        p.add_argument(
            "--allow-repo-code",
            action="store_true",
            help="permit checks that execute repository code (trusted repos only)",
        )
        p.add_argument(
            "--allow-network", action="store_true", help="permit checks that use the network"
        )
        p.add_argument("--timeout", type=float, help="per-check timeout in seconds")
        p.add_argument("--max-output-bytes", type=int, help="capture limit per stream")


def _add_output(p: argparse.ArgumentParser, formats: Sequence[str] = ("md", "json")) -> None:
    p.add_argument("--format", choices=list(formats), default=formats[0])
    p.add_argument("--out", help="write to this file instead of stdout")
    p.add_argument("--overwrite", action="store_true", help="allow replacing an existing output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="archonix",
        description="Archonix: from product understanding to production-ready "
        "software. Deterministic helpers for the Archonix skill.",
    )
    parser.add_argument("--version", action="version", version=f"archonix {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser("inventory", help="static repository inventory and stack detection")
    p.add_argument("path", nargs="?", default=".")
    _add_common(p)
    _add_output(p)
    p.set_defaults(func=cmd_inventory)

    p = sub.add_parser("tools", help="detect supported tools on PATH")
    p.add_argument("--versions", action="store_true", help="run each tool's version command")
    p.add_argument("--format", choices=["md", "json"], default="md")
    p.set_defaults(func=cmd_tools)

    cfg = sub.add_parser("config", help="configuration commands").add_subparsers(
        dest="config_command", required=True, metavar="SUBCOMMAND"
    )
    p = cfg.add_parser("show", help="show effective configuration and where each value came from")
    p.add_argument("path", nargs="?", default=".")
    _add_common(p, execution=True)
    p.set_defaults(func=cmd_config_show)

    req = sub.add_parser("requirements", help="requirements ledger commands").add_subparsers(
        dest="requirements_command", required=True, metavar="SUBCOMMAND"
    )
    p = req.add_parser("validate", help="validate a requirements ledger (schema + rules)")
    p.add_argument("file")
    p.set_defaults(func=cmd_requirements_validate)
    p = req.add_parser("matrix", help="acceptance traceability matrix")
    p.add_argument("file")
    p.add_argument(
        "--report",
        action="append",
        help="workflow report: resolves check:<id> evidence and its recorded test cases",
    )
    p.add_argument(
        "--junit",
        action="append",
        help="JUnit XML from any test runner (pytest, Jest, Vitest); repeatable",
    )
    _add_output(p)
    p.set_defaults(func=cmd_requirements_matrix)

    tst = sub.add_parser("tests", help="tests generated from acceptance criteria").add_subparsers(
        dest="tests_command", required=True, metavar="SUBCOMMAND"
    )
    p = tst.add_parser(
        "scaffold", help="one test stub per acceptance criterion (dry run by default)"
    )
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--framework", required=True, choices=["pytest", "jest", "vitest"])
    p.add_argument("--ledger", help="requirements ledger (default: docs/requirements.json)")
    p.add_argument("--out-dir", help="directory inside the repository (default: tests/acceptance)")
    p.add_argument("--typescript", action="store_true", help="write .test.ts files (Jest/Vitest)")
    p.add_argument(
        "--failing",
        action="store_true",
        help="stubs fail until implemented (default: skipped, i.e. pending)",
    )
    p.add_argument("--apply", action="store_true", help="write the files")
    p.add_argument(
        "--allow-source-writes", action="store_true", help="permit writing into the repository"
    )
    p.set_defaults(func=cmd_tests_scaffold)

    chk = sub.add_parser("check", help="plan and run checks").add_subparsers(
        dest="check_command", required=True, metavar="SUBCOMMAND"
    )
    p = chk.add_parser("list", help="list built-in checks and their requirements")
    p.add_argument("--format", choices=["md", "json"], default="md")
    p.set_defaults(func=cmd_check_list)
    for name, func, helptext in (
        ("plan", cmd_check_plan, "show what would run (executes nothing)"),
        ("run", cmd_check_run, "run permitted checks and build a report"),
    ):
        p = chk.add_parser(name, help=helptext)
        p.add_argument("path", nargs="?", default=".")
        p.add_argument("--checks", help="comma-separated check ids (default: all applicable)")
        _add_common(p, execution=True)
        p.add_argument("--format", choices=["md", "json"], default="md")
        if name == "run":
            p.add_argument("--out-dir", help="write report.json, report.md and artifacts here")
            p.add_argument("--overwrite", action="store_true")
            p.add_argument(
                "--workflow", default="audit", help="workflow name recorded in the report"
            )
            p.add_argument(
                "--fail-on",
                choices=list(SEVERITIES[:-1]),
                help="exit 1 if findings at or above this severity exist",
            )
            p.add_argument(
                "--fail-on-error",
                action="store_true",
                help="exit 4 if any check failed or could not be parsed",
            )
            p.add_argument(
                "--label-example", action="store_true", help="mark the report as an example"
            )
        p.set_defaults(func=func)

    p = sub.add_parser("validate", help="validate a JSON document against an Archonix schema")
    p.add_argument("file")
    p.add_argument("--schema", help="schema name (default: inferred from 'kind')")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("render", help="render a JSON document as Markdown")
    p.add_argument("file")
    p.add_argument("--out")
    p.add_argument("--overwrite", action="store_true")
    p.set_defaults(func=cmd_render)

    sch = sub.add_parser("schema", help="schema commands").add_subparsers(
        dest="schema_command", required=True, metavar="SUBCOMMAND"
    )
    p = sch.add_parser("list", help="list bundled schemas")
    p.set_defaults(func=cmd_schema_list)

    rd = sub.add_parser("readiness", help="release readiness").add_subparsers(
        dest="readiness_command", required=True, metavar="SUBCOMMAND"
    )
    p = rd.add_parser("assess", help="assess release readiness against a policy")
    p.add_argument("--report", action="append", help="workflow report JSON (repeatable)")
    p.add_argument("--ledger", help="requirements ledger JSON")
    p.add_argument("--policy", help="readiness policy TOML (default: built-in)")
    _add_output(p)
    p.add_argument("--label-example", action="store_true", help="mark the output as an example")
    p.set_defaults(func=cmd_readiness)

    arch = sub.add_parser("architecture", help="architecture artifacts").add_subparsers(
        dest="architecture_command", required=True, metavar="SUBCOMMAND"
    )
    p = arch.add_parser("diagram", help="Mermaid diagram with evidence labels")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--python-package", help="package dir (relative to path) for an import graph")
    p.add_argument("--depth", type=int, default=2, help="module depth for the import graph")
    _add_common(p)
    _add_output(p, formats=("md", "mermaid"))
    p.set_defaults(func=cmd_architecture)

    agents = sub.add_parser(
        "agents", help="project agent context (.ai/ -> AGENTS.md, CLAUDE.md, skills)"
    ).add_subparsers(dest="agents_command", required=True, metavar="SUBCOMMAND")
    p = agents.add_parser("init", help="draft .ai/ from repository evidence (dry run by default)")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--apply", action="store_true", help="write the files")
    p.add_argument(
        "--allow-source-writes", action="store_true", help="permit writing into the repository"
    )
    _add_common(p)
    p.set_defaults(func=cmd_agents_init)
    p = agents.add_parser("sync", help="render .ai/ into AGENTS.md, CLAUDE.md and skill folders")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument(
        "--target",
        default="claude,agents",
        help="comma-separated: claude (.claude/skills + CLAUDE.md), "
        "agents (.agents/skills, read by Codex and Cursor)",
    )
    p.add_argument("--apply", action="store_true", help="write the files")
    p.add_argument(
        "--allow-source-writes", action="store_true", help="permit writing into the repository"
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if outputs are missing, stale or conflicting (for CI)",
    )
    p.set_defaults(func=cmd_agents_sync)

    docs = sub.add_parser("docs", help="project document templates").add_subparsers(
        dest="docs_command", required=True, metavar="SUBCOMMAND"
    )
    p = docs.add_parser("list", help="list template sets")
    p.set_defaults(func=cmd_docs_list)
    p = docs.add_parser("init", help="create templates for one workflow (dry run by default)")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--set", required=True, help="template set (see 'archonix docs list')")
    p.add_argument("--project", help="project name used in templates")
    p.add_argument("--apply", action="store_true", help="write the files")
    p.add_argument(
        "--allow-source-writes", action="store_true", help="permit writing into the repository"
    )
    p.set_defaults(func=cmd_docs_init)

    perf = sub.add_parser("perf", help="API performance helpers").add_subparsers(
        dest="perf_command", required=True, metavar="SUBCOMMAND"
    )
    p = perf.add_parser("endpoints", help="list endpoints from an OpenAPI document")
    p.add_argument("spec")
    p.add_argument("--format", choices=["md", "json"], default="md")
    p.set_defaults(func=cmd_perf_endpoints)
    p = perf.add_parser("smoke", help="bounded GET/HEAD latency smoke check")
    p.add_argument("--base-url", required=True)
    p.add_argument("--path", action="append", required=True, help="endpoint path (repeatable)")
    p.add_argument("--method", default="GET", choices=["GET", "HEAD"])
    p.add_argument("--requests", type=int, default=20)
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--warmup", type=int, default=2)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--authorized-host", help="required for non-loopback targets")
    p.add_argument("--auth-header-env", help="env var holding the Authorization header value")
    p.add_argument("--p95-ms", type=float)
    p.add_argument("--max-error-rate", type=float)
    p.add_argument("--revision")
    p.add_argument("--environment")
    p.add_argument("--allow-network", action="store_true")
    _add_output(p)
    p.add_argument("--label-example", action="store_true", help="mark the output as an example")
    p.set_defaults(func=cmd_perf_smoke)
    p = perf.add_parser("k6-script", help="generate a reviewable k6 load-test scenario")
    p.add_argument("--base-url", required=True)
    p.add_argument("--path", action="append", required=True)
    p.add_argument("--vus", type=int, default=5)
    p.add_argument("--duration", default="30s")
    p.add_argument("--p95-ms", type=float)
    p.add_argument("--max-error-rate", type=float)
    p.add_argument("--out")
    p.add_argument("--overwrite", action="store_true")
    p.set_defaults(func=cmd_perf_k6)

    for name, func, helptext in (
        ("install", cmd_install, "install the skill (dry run by default)"),
        ("uninstall", cmd_uninstall, "remove Archonix-managed skill files (dry run by default)"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--assistant", required=True, choices=["claude", "codex", "cursor"])
        p.add_argument("--scope", choices=["user", "project"], default="user")
        p.add_argument("--project-dir", help="project root for --scope project")
        p.add_argument("--apply", action="store_true", help="make the changes")
        p.set_defaults(func=func)

    sk = sub.add_parser("skill", help="skill package commands").add_subparsers(
        dest="skill_command", required=True, metavar="SUBCOMMAND"
    )
    p = sk.add_parser("validate", help="validate a skill directory (default: bundled skill)")
    p.add_argument("path", nargs="?")
    p.set_defaults(func=cmd_skill_validate)
    p = sk.add_parser("path", help="print the bundled skill directory")
    p.set_defaults(func=cmd_skill_path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        code: int = args.func(args)
        return code
    except PolicyError as exc:
        print(f"archonix: refused: {exc}", file=sys.stderr)
        return EXIT_POLICY
    except ValidationFailed as exc:
        print(f"archonix: {exc}", file=sys.stderr)
        return EXIT_NEGATIVE
    except ArchonixError as exc:
        print(f"archonix: error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
