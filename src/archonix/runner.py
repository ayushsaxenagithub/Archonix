"""Subprocess execution with explicit argv, cwd, environment, timeout and bounded capture.

This wrapper controls *how* a command is launched and recorded. It does not make an
untrusted tool safe: the child process runs with the caller's privileges and may read
files, write caches or use the network unless the operating system prevents it.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

from .timeutil import utc_now

# Variables passed through to children by default. Everything else must be listed
# explicitly so credentials in the caller's environment are not leaked to tools.
BASE_ENV_PASSTHROUGH = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "TMPDIR",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
    "VIRTUAL_ENV",
)
KILL_GRACE_SECONDS = 3.0


@dataclass
class CapturedStream:
    data: bytes = b""
    bytes_total: int = 0
    truncated: bool = False

    def text(self) -> str:
        return self.data.decode("utf-8", errors="replace")


@dataclass
class RunResult:
    argv: list[str]
    cwd: str
    started_at: str
    duration_seconds: float
    exit_code: int | None
    status: str  # completed | timeout | failed-to-start | missing-tool
    stdout: CapturedStream = field(default_factory=CapturedStream)
    stderr: CapturedStream = field(default_factory=CapturedStream)
    error: str | None = None


def build_env(
    passthrough: Sequence[str] = (),
    extra: Mapping[str, str] | None = None,
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source = os.environ if source is None else source
    names = set(BASE_ENV_PASSTHROUGH) | set(passthrough)
    env = {k: v for k, v in source.items() if k in names}
    env.update(extra or {})
    if "PATH" in env:
        env["PATH"] = safe_path(env["PATH"])
    return env


def safe_path(value: str) -> str:
    """Drop empty and relative PATH entries.

    An entry such as ``.`` or ``bin`` resolves against the working directory, which is
    usually the repository being inspected, so a repository could otherwise supply its
    own ``ruff`` or ``git`` executable.
    """
    return os.pathsep.join(p for p in value.split(os.pathsep) if p and os.path.isabs(p))


def _drain(pipe: IO[bytes], sink: CapturedStream, limit: int) -> None:
    while True:
        chunk = pipe.read(65536)
        if not chunk:
            break
        sink.bytes_total += len(chunk)
        room = limit - len(sink.data)
        if room > 0:
            sink.data += chunk[:room]
        if len(chunk) > max(room, 0):
            sink.truncated = True
    pipe.close()


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate(proc: subprocess.Popen[bytes]) -> None:
    """Terminate the child and its whole process group, escalating to SIGKILL.

    The parent exiting after SIGTERM is not enough: descendants in the same group may
    ignore SIGTERM. The group is polled for the grace period and then sent SIGKILL
    regardless, so no member outlives the timeout.
    """
    if os.name == "posix":
        pgid = proc.pid  # start_new_session=True makes the child a group leader
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGTERM)
        deadline = time.monotonic() + KILL_GRACE_SECONDS
        while time.monotonic() < deadline:
            if proc.poll() is not None and not _group_alive(pgid):
                break
            time.sleep(0.05)
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGKILL)
    else:  # pragma: no cover - exercised only on Windows
        proc.kill()
    proc.wait()


def run(
    argv: Sequence[str],
    cwd: Path,
    *,
    env: Mapping[str, str],
    timeout: float,
    max_output_bytes: int,
) -> RunResult:
    """Run ``argv`` (never through a shell) and capture bounded output."""
    if isinstance(argv, str):  # defensive: a string would be split by nobody
        raise TypeError("argv must be a sequence of arguments, not a string")
    argv = [str(a) for a in argv]
    started = utc_now()
    t0 = time.monotonic()
    executable = shutil.which(argv[0], path=safe_path(env.get("PATH", ""))) if argv else None
    if executable is not None:
        executable = os.path.abspath(executable)
    if executable is None:
        return RunResult(
            argv,
            str(cwd),
            started,
            0.0,
            None,
            "missing-tool",
            error=f"executable not found on PATH: {argv[0] if argv else '<empty>'}",
        )
    try:
        proc = subprocess.Popen(
            [executable, *argv[1:]],
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=(os.name == "posix"),
        )
    except OSError as exc:
        return RunResult(
            argv, str(cwd), started, time.monotonic() - t0, None, "failed-to-start", error=str(exc)
        )

    out, err = CapturedStream(), CapturedStream()
    if proc.stdout is None or proc.stderr is None:  # pragma: no cover - PIPE always sets them
        raise RuntimeError("subprocess pipes were not created")
    readers = [
        threading.Thread(target=_drain, args=(proc.stdout, out, max_output_bytes), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr, err, max_output_bytes), daemon=True),
    ]
    for r in readers:
        r.start()
    status = "completed"
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        status = "timeout"
        _terminate(proc)
    for r in readers:
        r.join(timeout=KILL_GRACE_SECONDS)
    duration = time.monotonic() - t0
    exit_code = proc.returncode if status == "completed" else None
    return RunResult(
        argv,
        str(cwd),
        started,
        round(duration, 3),
        exit_code,
        status,
        out,
        err,
        error=f"timed out after {timeout}s" if status == "timeout" else None,
    )
