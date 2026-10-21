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
from .testcases import matches_reference

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


# Machine-checkable outcome of a referenced check -> evidence result. "findings" needs a
# human decision (a finding may or may not violate the criterion), so it is unknown.
CHECK_OUTCOME_RESULT = {"clean": "pass", "tests-failed": "fail"}


CASE_RESULT = {"passed": "pass", "failed": "fail", "errored": "fail", "skipped": "unknown"}


def collect_cases(
    reports: list[dict[str, Any]], junit: list[tuple[str, list[dict[str, Any]]]] | None = None
) -> list[dict[str, Any]]:
    """Test cases from workflow reports (``executions[].test_cases``) and from directly
    supplied JUnit files, each tagged with where it came from."""
    cases = [
        {**c, "source": e["check_id"]}
        for r in reports
        for e in r.get("executions", [])
        for c in (e.get("test_cases") or [])
    ]
    for label, junit_cases in junit or []:
        cases += [{**c, "source": label} for c in junit_cases]
    return cases


def _case_evidence(case: dict[str, Any]) -> tuple[str, str, str]:
    result = CASE_RESULT.get(case.get("result", ""), "unknown")
    return result, "verified", f"test {case['name']} ({case['source']}) -> {case.get('result')}"


def _test_reference(e: dict[str, Any], cases: list[dict[str, Any]]) -> tuple[str, str, str]:
    """Resolve an explicit ``test:<name>`` ledger reference against supplied test cases."""
    ref, recorded = e["reference"].removeprefix("test:"), e["result"]
    matched = [c for c in cases if matches_reference(ref, c)]
    if not matched:
        return "unknown", "verified", f"test:{ref} -> not found in supplied test results"
    results = {CASE_RESULT.get(c.get("result", ""), "unknown") for c in matched}
    resolved = "fail" if "fail" in results else "unknown" if results - {"pass"} else "pass"
    result = "fail" if "fail" in (resolved, recorded) else resolved
    outcomes = ", ".join(sorted({str(c.get("result")) for c in matched}))
    return result, "verified", f"test:{ref} -> {outcomes}"


def _evidence_result(
    e: dict[str, Any],
    executions: dict[str, dict[str, Any]],
    cases: list[dict[str, Any]] | None = None,
) -> tuple[str, str, str]:
    """Return (result, basis, description) for one evidence entry.

    ``check:<id>`` references are resolved against the supplied reports and the
    resolved outcome decides the result; a recorded "fail" is never overridden by a
    pass. Other references keep their recorded result but are labelled as recorded
    assertions rather than verified execution evidence.
    """
    ref, recorded = e["reference"], e["result"]
    if ref.startswith("test:"):
        return _test_reference(e, cases or [])
    if not ref.startswith("check:"):
        return recorded, "recorded", f"{ref} (recorded {recorded}; not machine-checked)"
    ex = executions.get(ref.removeprefix("check:"))
    if ex is None:
        return "unknown", "verified", f"{ref} -> not present in supplied reports"
    if ex.get("status") != "completed":
        resolved = "unknown"
    else:
        resolved = CHECK_OUTCOME_RESULT.get(ex.get("outcome", ""), "unknown")
    result = "fail" if "fail" in (resolved, recorded) else resolved
    note = "" if recorded == result else f"; ledger recorded {recorded}"
    return result, "verified", f"{ref} -> {ex.get('status')}/{ex.get('outcome')}{note}"


def traceability(
    ledger: dict[str, Any],
    reports: list[dict[str, Any]],
    junit: list[tuple[str, list[dict[str, Any]]]] | None = None,
) -> list[dict[str, Any]]:
    """One row per acceptance criterion with its evidence and a conservative result.

    Evidence is the ledger's entries (``check:<id>``, ``test:<name>`` or recorded
    assertions) plus every supplied test case whose name carries the criterion's ID.
    Results: ``fail`` if any evidence fails, else ``unknown`` if any is unresolved (a
    skipped test, a missing check), else ``pass``; ``missing`` when nothing is linked.
    ``basis`` says whether the result rests on resolved executions and test results
    (``verified``), on recorded assertions only (``recorded``), or both (``mixed``).
    """
    executions = {e["check_id"]: e for r in reports for e in r.get("executions", [])}
    cases = collect_cases(reports, junit)
    rows = []
    for req in ledger["requirements"]:
        evidence = req["verification"].get("evidence", [])
        criteria = req["acceptance_criteria"] or [{"id": "—", "description": "(no criteria)"}]
        for ac in criteria:
            linked = [e for e in evidence if e.get("acceptance_criterion") in (ac["id"], None)]
            judged = [_evidence_result(e, executions, cases) for e in linked]
            judged += [_case_evidence(c) for c in cases if ac["id"] in c.get("ac_ids", [])]
            results = {r for r, _, _ in judged}
            bases = {b for _, b, _ in judged}
            if not judged:
                state, basis = "missing", "none"
            else:
                state = "fail" if "fail" in results else "unknown" if results - {"pass"} else "pass"
                basis = bases.pop() if len(bases) == 1 else "mixed"
            rows.append(
                {
                    "requirement": req["id"],
                    "priority": req["priority"],
                    "status": req["status"],
                    "criterion": ac["id"],
                    "method": req["verification"]["method"],
                    "evidence": [d for _, _, d in judged],
                    "result": state,
                    "basis": basis,
                }
            )
    return rows


def orphan_tests(ledger: dict[str, Any], cases: list[dict[str, Any]]) -> list[str]:
    """Test cases naming acceptance-criterion IDs that the ledger does not define."""
    known = {ac["id"] for r in ledger["requirements"] for ac in r["acceptance_criteria"]}
    return sorted(
        {
            f"{c['name']} -> {ac_id}"
            for c in cases
            for ac_id in c.get("ac_ids", [])
            if ac_id not in known
        }
    )


def render_matrix(rows: list[dict[str, Any]]) -> str:
    out = [
        "# Acceptance traceability matrix",
        "",
        "Basis: `verified` = resolved against supplied check executions or test results; "
        "`recorded` = assertion recorded in the ledger, not machine-checked.",
        "",
        "| Requirement | Priority | Status | Criterion | Method | Result | Basis | Evidence |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        out.append(
            f"| {r['requirement']} | {r['priority']} | {r['status']} | {r['criterion']} | "
            f"{r['method']} | {r['result']} | {r['basis']} | {'; '.join(r['evidence']) or '—'} |"
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
