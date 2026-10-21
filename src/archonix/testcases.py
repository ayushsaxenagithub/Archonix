"""Individual test cases from JUnit XML, and the naming convention that links them to
acceptance criteria.

Convention (written by ``archonix tests scaffold``, usable by hand):

* pytest: ``test_<encoded-id>__<anything>`` where the encoded ID is the acceptance
  criterion ID lower-cased with ``-`` replaced by ``_``. ``AC-001-1`` becomes
  ``test_ac_001_1__discount_applies``. The double underscore ends the ID, and because AC
  IDs cannot contain ``_`` the mapping is reversible.
* Jest / Vitest (or any framework): the literal ID anywhere in the test name, conventionally
  as a title prefix: ``"AC-001-1: discount applies"``.

Result mapping: a ``<failure>`` is failed, an ``<error>`` is errored, a ``<skipped>`` is
skipped, and anything else is passed. jest-junit 17 reports ``test.todo`` with no marker,
but excludes them from the suite's ``tests`` count; such suites' unmarked zero-time
cases are treated as pending. Archonix-generated stubs use ``test.skip`` regardless.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET  # nosec B405 - reports from the user's own test run
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_CASES = 10_000
AC_ID = re.compile(r"\bAC-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
PYTEST_ENCODED = re.compile(r"(?:^|[^a-z0-9])test_(ac(?:_[a-z0-9]+)+?)__")


def encode_ac(ac_id: str) -> str:
    return ac_id.lower().replace("-", "_")


def decode_ac(encoded: str) -> str:
    return encoded.upper().replace("_", "-")


def ac_ids(*texts: str | None) -> list[str]:
    """Acceptance-criterion IDs referenced by a test's name or class name."""
    found: list[str] = []
    for text in texts:
        if not text:
            continue
        for m in PYTEST_ENCODED.finditer(text):
            found.append(decode_ac(m.group(1)))
        found.extend(AC_ID.findall(text))
    return sorted(set(found))


@dataclass(frozen=True)
class TestCase:
    name: str
    classname: str
    file: str | None
    result: str  # passed | failed | errored | skipped

    @property
    def ac_ids(self) -> list[str]:
        return ac_ids(self.name, self.classname)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "classname": self.classname,
            "file": self.file,
            "result": self.result,
            "ac_ids": self.ac_ids,
        }


def _result(case: ET.Element) -> str:
    if case.find("failure") is not None:
        return "failed"
    if case.find("error") is not None:
        return "errored"
    if case.find("skipped") is not None:
        return "skipped"
    return "passed"


def _uncounted_pending(suite: ET.Element) -> bool:
    """jest-junit lists ``test.todo`` cases without a marker but leaves them out of the
    suite's ``tests`` count. More listed cases than counted means some unmarked cases are
    pending, not passed."""
    try:
        counted = int(suite.get("tests", ""))
    except ValueError:
        return False
    return len(suite.findall("testcase")) > counted


def cases_from_root(root: ET.Element) -> tuple[list[TestCase], bool]:
    """Return (cases, truncated) from a parsed JUnit document.

    In a suite that lists more cases than its ``tests`` count, unmarked zero-time cases
    are reported as skipped (pending). This is conservative: a genuine 0 ms pass in such
    a suite becomes "skipped", never the reverse.
    """
    cases: list[TestCase] = []
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite")) or [root]
    for suite in suites:
        pending_hint = _uncounted_pending(suite)
        for case in suite.findall("testcase"):
            if len(cases) >= MAX_CASES:
                return cases, True
            result = _result(case)
            if pending_hint and result == "passed" and case.get("time") in {"0", "0.0", "0.000"}:
                result = "skipped"
            cases.append(
                TestCase(
                    name=case.get("name", ""),
                    classname=case.get("classname", ""),
                    file=case.get("file"),
                    result=result,
                )
            )
    return cases, False


def parse_junit_cases(path: Path) -> tuple[list[TestCase], bool]:
    """Parse a JUnit XML file into test cases. Raises ValueError for unreadable input."""
    try:
        root = ET.parse(path).getroot()  # noqa: S314  # nosec B314
    except (OSError, ET.ParseError) as exc:
        raise ValueError(f"{path}: not a readable JUnit XML file ({exc})") from exc
    if root.tag not in {"testsuites", "testsuite"}:
        raise ValueError(f"{path}: root element <{root.tag}> is not a JUnit test report")
    return cases_from_root(root)


def matches_reference(reference: str, case: dict[str, Any]) -> bool:
    """Does a ledger ``test:<reference>`` point at this case? Supports a bare test name,
    ``classname::name``, ``file::name`` and pytest node IDs such as
    ``tests/test_x.py::test_name`` (classname ``tests.test_x``)."""
    name, classname = case.get("name") or "", case.get("classname") or ""
    if reference in {name, f"{classname}::{name}"}:
        return True
    if case.get("file") and reference == f"{case['file']}::{name}":
        return True
    module, sep, test = reference.rpartition("::")
    if sep and test == name and module.endswith(".py"):
        return module.removesuffix(".py").replace("/", ".") == classname
    return False
