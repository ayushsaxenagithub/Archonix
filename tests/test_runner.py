from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from archonix.runner import build_env, run

PY = sys.executable


def test_captures_output_and_exit_code(tmp_path: Path) -> None:
    r = run(
        [PY, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"],
        tmp_path,
        env=build_env(),
        timeout=10,
        max_output_bytes=4096,
    )
    assert r.status == "completed" and r.exit_code == 3
    assert r.stdout.text().strip() == "out" and r.stderr.text().strip() == "err"


def test_missing_tool_is_not_an_execution(tmp_path: Path) -> None:
    r = run(
        ["definitely-not-a-real-tool-xyz"],
        tmp_path,
        env=build_env(),
        timeout=5,
        max_output_bytes=4096,
    )
    assert r.status == "missing-tool" and r.exit_code is None


def test_timeout_kills_process_group(tmp_path: Path) -> None:
    marker = tmp_path / "child-survived"
    grandchild = tmp_path / "grandchild.py"
    grandchild.write_text(f"import time\ntime.sleep(3)\nopen({str(marker)!r}, 'w').close()\n")
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, {str(grandchild)!r}])\n"
        "time.sleep(30)\n"
    )
    t0 = time.monotonic()
    r = run([PY, str(parent)], tmp_path, env=build_env(), timeout=0.5, max_output_bytes=4096)
    assert r.status == "timeout" and r.exit_code is None
    assert time.monotonic() - t0 < 10
    time.sleep(3.5)
    assert not marker.exists(), "grandchild should have been killed with the process group"


def test_output_is_bounded(tmp_path: Path) -> None:
    r = run(
        [PY, "-c", "print('x' * 100000)"],
        tmp_path,
        env=build_env(),
        timeout=10,
        max_output_bytes=1024,
    )
    assert len(r.stdout.data) == 1024 and r.stdout.truncated and r.stdout.bytes_total > 100000


def test_no_shell_interpretation(tmp_path: Path) -> None:
    r = run(
        [PY, "-c", "import sys; print(sys.argv[1])", "a; echo pwned > hacked"],
        tmp_path,
        env=build_env(),
        timeout=10,
        max_output_bytes=4096,
    )
    assert r.stdout.text().strip() == "a; echo pwned > hacked"
    assert not (tmp_path / "hacked").exists()


def test_string_argv_rejected(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        run("echo hi", tmp_path, env=build_env(), timeout=1, max_output_bytes=1024)  # type: ignore[arg-type]


def test_environment_is_minimal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUD_SECRET", "should-not-leak")
    monkeypatch.setenv("ALLOWED_VAR", "ok")
    env = build_env(passthrough=["ALLOWED_VAR"])
    r = run(
        [
            PY,
            "-c",
            "import os; print(os.environ.get('CLOUD_SECRET'), os.environ.get('ALLOWED_VAR'))",
        ],
        tmp_path,
        env=env,
        timeout=10,
        max_output_bytes=4096,
    )
    assert r.stdout.text().strip() == "None ok"


def test_explicit_cwd(tmp_path: Path) -> None:
    r = run(
        [PY, "-c", "import os; print(os.getcwd())"],
        tmp_path,
        env=build_env(),
        timeout=10,
        max_output_bytes=4096,
    )
    assert Path(r.stdout.text().strip()).resolve() == tmp_path.resolve()


def test_timeout_kills_descendants_that_ignore_sigterm(tmp_path: Path) -> None:
    """A cooperative parent exits on SIGTERM; its child ignores SIGTERM and must not survive."""
    import os
    import signal

    if os.name != "posix":
        pytest.skip("process groups")
    pid_file = tmp_path / "child.pid"
    child = tmp_path / "child.py"
    child.write_text(
        "import os, signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, {str(child)!r}])\n"
        "time.sleep(60)\n"
    )
    t0 = time.monotonic()
    r = run([PY, str(parent)], tmp_path, env=build_env(), timeout=1, max_output_bytes=1024)
    assert r.status == "timeout"
    assert time.monotonic() - t0 < 10
    pid = int(pid_file.read_text())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    os.kill(pid, signal.SIGKILL)  # do not leak the process if the assertion fails
    pytest.fail("descendant that ignores SIGTERM survived the timeout")
