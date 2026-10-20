"""Requirements ledger: semantic validation and acceptance traceability.

Schema validation checks shape. The rules here check meaning: unique identifiers,
resolvable acyclic dependencies, and approval gates (approved work needs acceptance
criteria; critical questions must be answered or explicitly accepted as assumptions;
``verified`` needs passing evidence).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .schemas import errors_for

ACTIVE_STATUSES = {"approved", "in-progress", "implemented", "verified"}


@dataclass
class LedgerResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_ledger(ledger: Any) -> LedgerResult:
    result = LedgerResult(errors=errors_for(ledger, "requirements"))
    if result.errors:
        return result  # semantic checks assume a well-formed document
    reqs: list[dict[str, Any]] = ledger["requirements"]
    ids = [r["id"] for r in reqs]
    seen: set[str] = set()
    for rid in ids:
        if rid in seen:
            result.errors.append(f"duplicate requirement id {rid}")
        seen.add(rid)
    ac_seen: dict[str, str] = {}
    for r in reqs:
        for ac in r["acceptance_criteria"]:
            if ac["id"] in ac_seen:
                result.errors.append(
                    f"{r['id']}: acceptance criterion {ac['id']} already used by "
                    f"{ac_seen[ac['id']]}"
                )
            ac_seen[ac["id"]] = r["id"]

    by_id = {r["id"]: r for r in reqs}
    for r in reqs:
        rid, status = r["id"], r["status"]
        for dep in r["dependencies"]:
            if dep == rid:
                result.errors.append(f"{rid}: depends on itself")
            elif dep not in by_id:
                result.errors.append(f"{rid}: unknown dependency {dep}")
        if status in ACTIVE_STATUSES and not r["acceptance_criteria"]:
            result.errors.append(
                f"{rid}: status '{status}' requires at least one acceptance criterion"
            )
        for q in r.get("open_questions", []):
            unresolved = not q.get("resolution") and not q.get("accepted_as_assumption")
            if q["critical"] and unresolved:
                msg = f"{rid}: critical question {q['id']} is unresolved"
                if status in ACTIVE_STATUSES:
                    result.errors.append(
                        msg + f" but status is '{status}' (answer it or accept it "
                        "explicitly as an assumption)"
                    )
                else:
                    result.warnings.append(msg)
        ver = r["verification"]
        evidence = ver.get("evidence", [])
        if status == "verified":
            if ver["method"] == "not-yet-defined":
                result.errors.append(f"{rid}: verified but verification method is not defined")
            if not evidence:
                result.errors.append(f"{rid}: verified but no verification evidence is recorded")
            elif any(e["result"] != "pass" for e in evidence):
                result.errors.append(f"{rid}: verified but not all evidence passed")
            covered = {e.get("acceptance_criterion") for e in evidence}
            missing = [ac["id"] for ac in r["acceptance_criteria"] if ac["id"] not in covered]
            if missing and None not in covered:
                result.errors.append(
                    f"{rid}: verified but criteria lack evidence: {', '.join(missing)}"
                )
        for e in evidence:
            ac = e.get("acceptance_criterion")
            if ac is not None and ac_seen.get(ac) != rid:
                result.errors.append(f"{rid}: evidence references unknown criterion {ac}")
        if r["source"]["type"] == "assumption" and r["priority"] == "must":
            result.warnings.append(f"{rid}: 'must' requirement rests on an assumption; confirm it")
        if status == "approved" and r["source"]["type"] in {"inferred", "assumption"}:
            result.warnings.append(f"{rid}: approved but its source is '{r['source']['type']}'")

    cycle = _find_cycle(by_id)
    if cycle:
        result.errors.append("dependency cycle: " + " -> ".join(cycle))
    return result


def _find_cycle(by_id: dict[str, dict[str, Any]]) -> list[str] | None:
    state: dict[str, int] = {}  # 1 = visiting, 2 = done
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for dep in by_id[node]["dependencies"]:
            if dep not in by_id or dep == node:
                continue
            if state.get(dep) == 1:
                return [*stack[stack.index(dep) :], dep]
            if state.get(dep) is None:
                found = visit(dep)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return None

    for rid in by_id:
        if state.get(rid) is None:
            found = visit(rid)
            if found:
                return found
    return None


def traceability(ledger: dict[str, Any], reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per acceptance criterion: linked evidence and whether it is present.

    Evidence references of the form ``check:<check_id>`` are resolved against the
    supplied workflow reports; anything else is reported as recorded-but-unchecked.
    """
    executions = {e["check_id"]: e for r in reports for e in r.get("executions", [])}
    rows = []
    for req in ledger["requirements"]:
        evidence = req["verification"].get("evidence", [])
        criteria = req["acceptance_criteria"] or [{"id": "—", "description": "(no criteria)"}]
        for ac in criteria:
            linked = [e for e in evidence if e.get("acceptance_criterion") in (ac["id"], None)]
            resolved = []
            for e in linked:
                ref = e["reference"]
                if ref.startswith("check:"):
                    ex = executions.get(ref.removeprefix("check:"))
                    resolved.append(
                        f"{ref} -> "
                        + (
                            f"{ex['status']}/{ex['outcome']}"
                            if ex
                            else "not present in supplied reports"
                        )
                    )
                else:
                    resolved.append(f"{ref} ({e['result']}, not machine-checked)")
            if not linked:
                state = "missing"
            elif all(e["result"] == "pass" for e in linked):
                state = "pass"
            elif any(e["result"] == "fail" for e in linked):
                state = "fail"
            else:
                state = "unknown"
            rows.append(
                {
                    "requirement": req["id"],
                    "priority": req["priority"],
                    "status": req["status"],
                    "criterion": ac["id"],
                    "method": req["verification"]["method"],
                    "evidence": resolved,
                    "result": state,
                }
            )
    return rows


def render_matrix(rows: list[dict[str, Any]]) -> str:
    out = [
        "# Acceptance traceability matrix",
        "",
        "| Requirement | Priority | Status | Criterion | Method | Result | Evidence |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        out.append(
            f"| {r['requirement']} | {r['priority']} | {r['status']} | {r['criterion']} | "
            f"{r['method']} | {r['result']} | {'; '.join(r['evidence']) or '—'} |"
        )
    return "\n".join(out) + "\n"


def render_ledger(ledger: dict[str, Any]) -> str:
    out = []
    if ledger.get("example"):
        out += ["> **EXAMPLE LEDGER** — synthetic requirements for documentation.", ""]
    out += [f"# Requirements: {ledger['project']}", ""]
    for r in ledger["requirements"]:
        out += [
            f"## {r['id']} — {r['title']}",
            "",
            f"- Priority: {r['priority']}; status: {r['status']}; source: {r['source']['type']}"
            + (f" ({r['source']['reference']})" if r["source"].get("reference") else ""),
            f"- Depends on: {', '.join(r['dependencies']) or 'none'}",
            f"- Verification: {r['verification']['method']}",
            "",
            r["description"],
            "",
        ]
        if r["acceptance_criteria"]:
            out += [f"- **{ac['id']}**: {ac['description']}" for ac in r["acceptance_criteria"]]
            out.append("")
        for q in r.get("open_questions", []):
            state = q.get("resolution") or (
                "accepted as assumption" if q.get("accepted_as_assumption") else "OPEN"
            )
            out.append(
                f"- Question {q['id']}{' (critical)' if q['critical'] else ''}: "
                f"{q['question']} — {state}"
            )
        if r.get("open_questions"):
            out.append("")
    return "\n".join(out)
