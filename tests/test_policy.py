from __future__ import annotations

import os
from pathlib import Path

import pytest

from archonix.errors import PolicyError
from archonix.policy import Permissions, Requirements, WriteGuard, blocking_reasons


def test_blocking_reasons_are_independent() -> None:
    perms = Permissions(external_tools=True)
    assert blocking_reasons(Requirements(), perms) == []
    reasons = blocking_reasons(Requirements(repo_code=True, network=True), perms)
    assert len(reasons) == 2
    assert blocking_reasons(Requirements(), Permissions())[0].startswith("requires external tool")


def test_write_guard_confines_writes(tmp_path: Path) -> None:
    allowed = tmp_path / "out"
    guard = WriteGuard([allowed])
    guard.write_text(allowed / "nested" / "r.md", "ok")
    with pytest.raises(PolicyError, match="outside the allowed"):
        guard.write_text(tmp_path / "src" / "app.py", "x")
    with pytest.raises(PolicyError, match="outside the allowed"):
        guard.write_text(allowed / ".." / "escape.md", "x")
    with pytest.raises(PolicyError, match="overwrite"):
        guard.write_text(allowed / "nested" / "r.md", "again")
    WriteGuard([allowed], overwrite=True).write_text(allowed / "nested" / "r.md", "again")


@pytest.mark.skipif(os.name != "posix", reason="symlinks")
def test_write_guard_rejects_symlink_escape(tmp_path: Path) -> None:
    allowed = tmp_path / "out"
    allowed.mkdir()
    (allowed / "link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(PolicyError):
        WriteGuard([allowed]).write_text(allowed / "link" / "pwned.txt", "x")
    assert not (tmp_path / "pwned.txt").exists()
