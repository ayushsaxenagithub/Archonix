from __future__ import annotations

from typing import Any

from archonix.findings import deduplicate, make_finding, stable_id


def f(
    tool: str = "bandit", rule: str = "B602", line: int = 3, msg: str = "shell"
) -> dict[str, Any]:
    return make_finding(
        tool=tool,
        check_id=tool,
        category="security",
        title=msg,
        message=msg,
        severity="high",
        confidence="high",
        rule_id=rule,
        path="a.py",
        line=line,
    )


def test_stable_id_is_deterministic_and_ignores_message() -> None:
    assert stable_id("t", "R1", "a.py", 1, None) == stable_id("t", "R1", "a.py", 1, None)
    assert f(msg="one")["id"] == f(msg="two")["id"]
    assert f(line=3)["id"] != f(line=4)["id"]


def test_exact_duplicates_merge_and_count_occurrences() -> None:
    out = deduplicate([f(), f()])
    assert len(out) == 1
    assert out[0]["occurrences"] == 2


def test_similar_messages_at_different_locations_are_not_merged() -> None:
    out = deduplicate([f(line=3, msg="same"), f(line=9, msg="same")])
    assert len(out) == 2


def test_cross_tool_overlap_is_linked_not_merged() -> None:
    a, b = f(tool="bandit", rule="B602"), f(tool="ruff", rule="S602")
    out = deduplicate([a, b])
    assert len(out) == 2
    assert out[0]["related_ids"] == [out[1]["id"]]
    assert out[0]["source"]["rule_id"] in {"B602", "S602"}  # original identifiers preserved
