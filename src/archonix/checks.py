"""Plan and execute checks, producing execution records and normalized findings.

Planning is passive (``which`` lookups and inventory). Execution launches only the
checks the effective policy allows; everything else is recorded as blocked/skipped
with the reason, so a report always shows what was *not* checked.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import ADAPTERS, Adapter, Context, ParseOutcome
from .config import Settings
from .errors import ArchonixError
from .policy import blocking_reasons
from .redact import Redactor
from .runner import RunResult, build_env, run
from .tools import tool_version

EXCERPT_CHARS = 4000


@dataclass
class PlannedCheck:
    adapter: Adapter
    action: str  # run | skip | block
    reason: str
    argv_preview: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.adapter.id,
            "tool": self.adapter.tool,
            "action": self.action,
            "reason": self.reason,
            "requires": self.adapter.requires.as_dict(),
            "command": self.argv_preview,
        }


def plan_checks(
    root: Path, inventory: dict[str, Any], settings: Settings, requested: list[str] | None
) -> list[PlannedCheck]:
    if requested:
        unknown = [c for c in requested if c not in ADAPTERS]
        if unknown:
            raise ArchonixError(
                f"unknown check(s): {', '.join(unknown)}; available: {', '.join(ADAPTERS)}"
            )
        selected = [ADAPTERS[c] for c in requested]
    else:
        selected = list(ADAPTERS.values())
    preview_ctx = Context(root=root, artifact_dir=Path("<artifact-dir>"), excludes=settings.exclude)
    plans = []
    for adapter in selected:
        cfg = settings.check(adapter.id)
        preview_ctx.extra_args = cfg.extra_args
        argv = adapter.argv(preview_ctx)
        applies, why = adapter.applies(inventory, root)
        if not cfg.enabled:
            plans.append(PlannedCheck(adapter, "skip", "disabled by configuration", argv))
        elif not applies:
            plans.append(PlannedCheck(adapter, "skip", f"not applicable: {why}", argv))
        elif blockers := blocking_reasons(adapter.requires, settings.permissions):
            plans.append(PlannedCheck(adapter, "block", "; ".join(blockers), argv))
        elif (
            shutil.which(adapter.executable, path=build_env(settings.env_passthrough).get("PATH"))
            is None
        ):
            plans.append(
                PlannedCheck(adapter, "skip", f"{adapter.executable} is not installed", argv)
            )
        else:
            plans.append(PlannedCheck(adapter, "run", why, argv))
    return plans


def _stream(
    text: str, total: int, truncated: bool, redactor: Redactor
) -> tuple[dict[str, Any], int]:
    excerpt, n = redactor.redact(text[:EXCERPT_CHARS])
    return {
        "excerpt": excerpt or None,
        "bytes_total": total,
        "truncated": truncated or len(text) > EXCERPT_CHARS,
    }, n


def _redact_findings(findings: list[dict[str, Any]], redactor: Redactor) -> int:
    count = 0
    for f in findings:
        for key in ("title", "message", "evidence"):
            if isinstance(f.get(key), str):
                f[key], n = redactor.redact(f[key])
                count += n
    return count


def _redact_artifacts(
    directory: Path, redactor: Redactor, limit: int = 20_000_000
) -> tuple[int, list[str]]:
    """Redact retained artifacts in place, recursively, without following symlinks.

    Returns (replacements, notes). A file that cannot be redacted (binary, oversized,
    unreadable, or a symlink) cannot be retained safely, so it is removed from the
    artifact directory and named in the notes. Only Archonix's own artifact directory
    is touched; repository files are never deleted.
    """
    count = 0
    notes: list[str] = []
    for current, _dirs, files in os.walk(directory, followlinks=False):
        for name in sorted(files):
            path = Path(current) / name
            rel = path.relative_to(directory).as_posix()
            reason: str | None = None
            if path.is_symlink():
                reason = "is a symlink"
            else:
                try:
                    if path.stat().st_size > limit:
                        reason = f"exceeds {limit} bytes"
                    else:
                        text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    reason = "is not UTF-8 text"
                except OSError as exc:
                    reason = f"could not be read ({exc.strerror or exc})"
            if reason is not None:
                path.unlink(missing_ok=True)
                notes.append(
                    f"retained artifact {rel} {reason}, could not be redacted, and was removed"
                )
                continue
            redacted, n = redactor.redact(text)
            if n:
                path.write_text(redacted, encoding="utf-8")
                count += n
    return count, notes


def _redact_cases(
    cases: list[dict[str, Any]] | None, redactor: Redactor | None
) -> list[dict[str, Any]] | None:
    if cases is None or redactor is None:
        return cases
    out = []
    for case in cases:
        clean = dict(case)
        for key in ("name", "classname", "file"):
            if isinstance(clean.get(key), str):
                clean[key] = redactor.redact(clean[key])[0]
        out.append(clean)
    return out


def _finalize_artifacts(
    work: Path, tool: str, redactor: Redactor
) -> tuple[list[dict[str, Any]], int, list[str]]:
    """Redact and list every retained artifact. Runs on every exit path of a check."""
    replaced, notes = _redact_artifacts(work, redactor)
    artifacts = [
        {"path": str(p), "description": f"{tool} output", "retained": True}
        for p in sorted(work.rglob("*"))
        if p.is_file() and not p.is_symlink()
    ]
    return artifacts, replaced, notes


def _record(
    plan: PlannedCheck,
    *,
    status: str,
    outcome: str,
    detail: str,
    cwd: Path,
    result: RunResult | None = None,
    parsed: ParseOutcome | None = None,
    version: str | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    redactor: Redactor | None = None,
    extra_limitations: list[str] | None = None,
) -> dict[str, Any]:
    replacements = 0
    stdout = stderr = None
    if result is not None and redactor is not None:
        stdout, n1 = _stream(
            result.stdout.text(), result.stdout.bytes_total, result.stdout.truncated, redactor
        )
        stderr, n2 = _stream(
            result.stderr.text(), result.stderr.bytes_total, result.stderr.truncated, redactor
        )
        replacements = n1 + n2
    argv = result.argv if result is not None else plan.argv_preview
    if redactor is not None:
        red = [redactor.redact(a) for a in argv]
        argv = [a for a, _ in red]
        replacements += sum(n for _, n in red)
    limitations = [*(parsed.limitations if parsed else []), *(extra_limitations or [])]
    if redactor is not None:
        # Details and limitations can quote tool output (for example an npm error that
        # contains a registry URL with credentials), so they are redacted too.
        detail, n = redactor.redact(detail)
        replacements += n
        red_lims = [redactor.redact(x) for x in limitations]
        limitations = [x for x, _ in red_lims]
        replacements += sum(n for _, n in red_lims)
    return {
        "id": f"exec-{plan.adapter.id}",
        "check_id": plan.adapter.id,
        "tool": plan.adapter.tool,
        "tool_version": version,
        "argv": argv,
        "cwd": str(cwd),
        "started_at": result.started_at if result else None,
        "duration_seconds": result.duration_seconds if result else None,
        "exit_code": result.exit_code if result else None,
        "status": status,
        "outcome": outcome,
        "outcome_detail": detail,
        "stdout": stdout,
        "stderr": stderr,
        "artifacts": artifacts or [],
        "redaction": {"applied": redactor is not None, "replacements": replacements},
        "test_totals": parsed.test_totals if parsed else None,
        "test_cases": _redact_cases(parsed.test_cases, redactor) if parsed else None,
        "findings_count": len(parsed.findings) if parsed and outcome != "parse-error" else None,
        "parse_limitations": limitations,
        "coverage": None
        if parsed is None or outcome == "parse-error"
        else {
            "complete": parsed.complete,
            "detail": redactor.redact(parsed.coverage_detail)[0]
            if redactor is not None and parsed.coverage_detail
            else parsed.coverage_detail,
        },
        "requires": plan.adapter.requires.as_dict(),
    }


def execute_plan(
    root: Path,
    plans: list[PlannedCheck],
    settings: Settings,
    *,
    artifact_dir: Path | None,
    redactor: Redactor,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    """Run planned checks. Returns (execution_records, findings, skipped)."""
    executions: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    env = build_env(settings.env_passthrough)
    for plan in plans:
        if plan.action != "run":
            skipped.append({"check_id": plan.adapter.id, "reason": plan.reason})
            executions.append(
                _record(
                    plan,
                    status="blocked" if plan.action == "block" else "skipped",
                    outcome="not-run",
                    detail=plan.reason,
                    cwd=root,
                    redactor=redactor,
                )
            )
            continue
        retained = artifact_dir is not None
        work = (
            (artifact_dir / "artifacts" / plan.adapter.id)
            if artifact_dir
            else Path(tempfile.mkdtemp(prefix=f"archonix-{plan.adapter.id}-"))
        )
        work.mkdir(parents=True, exist_ok=True)
        version: str | None = None
        result: RunResult | None = None
        parsed: ParseOutcome | None = None
        failure: str | None = None
        try:
            version = tool_version(plan.adapter.executable, plan.adapter.version_args)
            ctx = Context(
                root=root,
                artifact_dir=work,
                excludes=settings.exclude,
                extra_args=settings.check(plan.adapter.id).extra_args,
                tool_version=version,
            )
            cfg = settings.check(plan.adapter.id)
            plan.adapter.prepare(ctx)
            result = run(
                plan.adapter.argv(ctx),
                root,
                env={**env, **plan.adapter.env},
                timeout=cfg.timeout_seconds or settings.timeout_seconds,
                max_output_bytes=settings.max_output_bytes,
            )
            if result.status == "completed":
                parsed = plan.adapter.interpret(result, ctx)
        except Exception as exc:  # one broken adapter must not lose the whole run
            failure = f"{type(exc).__name__}: {exc}"
        finally:
            # Artifacts are finalized on every path (timeouts and errors included) so that
            # a tool cannot leave unredacted output behind in a retained directory.
            if retained:
                artifacts, art_replaced, art_notes = _finalize_artifacts(
                    work, plan.adapter.tool, redactor
                )
            else:
                artifacts, art_replaced, art_notes = [], 0, []
                shutil.rmtree(work, ignore_errors=True)

        if parsed is not None and result is not None:
            replaced = (
                _redact_findings(parsed.findings, redactor)
                if parsed.outcome != "parse-error"
                else 0
            )
            if parsed.outcome != "parse-error":
                findings.extend(parsed.findings)
            if parsed.complete is False:
                parsed.detail += " (partial scan)"
            record = _record(
                plan,
                status="completed",
                outcome=parsed.outcome,
                detail=parsed.detail,
                cwd=root,
                result=result,
                parsed=parsed,
                version=version,
                artifacts=artifacts,
                redactor=redactor,
                extra_limitations=art_notes,
            )
            record["redaction"]["replacements"] += replaced + art_replaced
        elif failure is not None:
            record = _record(
                plan,
                status=result.status if result else "failed-to-start",
                outcome="parse-error" if result and result.status == "completed" else "tool-error",
                detail=f"adapter error: {failure}",
                cwd=root,
                result=result,
                version=version,
                artifacts=artifacts,
                redactor=redactor,
                extra_limitations=art_notes,
            )
            record["redaction"]["replacements"] += art_replaced
        else:
            if result is None:  # pragma: no cover - run() either returns or raises
                raise RuntimeError("check finished without a result")
            record = _record(
                plan,
                status=result.status,
                outcome="not-run" if result.status == "missing-tool" else "tool-error",
                detail=result.error or result.status,
                cwd=root,
                result=result,
                version=version,
                artifacts=artifacts,
                redactor=redactor,
                extra_limitations=art_notes,
            )
            record["redaction"]["replacements"] += art_replaced
        executions.append(record)
    return executions, findings, skipped
