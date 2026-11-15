"""Shared plumbing for missions.

A mission is a small, real Linux/Python task.  Its ``check`` function inspects
the learner's actual workspace and returns a list of :class:`Check` objects.
Nothing here requires root; all fixtures live inside the lab workspace.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class Check:
    """One pass/fail line in a mission verification report."""

    name: str
    ok: bool
    detail: str = ""


@dataclass
class Mission:
    """A lesson's hands-on task."""

    id: str
    num: int
    dir_name: str
    title: str
    domain: str
    brief: str
    hints: list[str] = field(default_factory=list)
    solution: dict[str, str] = field(default_factory=dict)
    setup: Callable[[Path], None] | None = None
    check: Callable[[Path], list[Check]] | None = None
    # Optional hook used when installing the *reference* solution, for
    # missions whose work is a command sequence (git, chmod, venv, ...).
    post_install: Callable[[Path], None] | None = None

    def prepare(self, workspace: Path) -> Path:
        """Create the mission directory and any fixtures (idempotent)."""
        mdir = workspace / self.dir_name
        mdir.mkdir(parents=True, exist_ok=True)
        if self.setup is not None:
            self.setup(mdir)
        return mdir

    def run_checks(self, workspace: Path) -> list[Check]:
        mdir = self.prepare(workspace)
        if self.check is None:
            return [Check("mission checker", False, "No checker implemented")]
        try:
            return self.check(mdir)
        except Exception as exc:  # defensive: never crash the whole app
            return [
                Check(
                    "mission checker crashed",
                    False,
                    f"{exc}\n{traceback.format_exc()}",
                )
            ]


# ---------------------------------------------------------------------------
# Helpers used by mission checkers
# ---------------------------------------------------------------------------
def run_script(
    script: Path,
    *args: object,
    cwd: Path | None = None,
    timeout: float = 20,
    direct: bool = False,
) -> subprocess.CompletedProcess:
    """Run a learner script and capture text output.

    ``direct=True`` executes the file itself (honouring the shebang); otherwise
    the current Python interpreter is used so a missing +x bit does not hide
    logic errors from the checker.
    """
    if direct:
        cmd = [str(script), *[str(a) for a in args]]
    else:
        cmd = [sys.executable, str(script), *[str(a) for a in args]]
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        out = _as_text(exc.stdout)
        err = _as_text(exc.stderr)
        return subprocess.CompletedProcess(
            cmd, 124, out, err + f"\n[timed out after {timeout}s]"
        )
    except OSError as exc:
        return subprocess.CompletedProcess(cmd, 127, "", f"{exc}")


def run_command(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: float = 20,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(cmd, 127, "", str(exc))


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def fresh_dir(path: Path) -> Path:
    """Remove and recreate a scratch directory."""
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def write_file(path: Path, text: str, mode: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)
    return path


def parse_json(proc: subprocess.CompletedProcess) -> tuple[object | None, str]:
    """Return (object, error) from a process's stdout."""
    raw = proc.stdout.strip()
    if not raw:
        return None, "stdout was empty (expected JSON)"
    try:
        return json.loads(raw), ""
    except json.JSONDecodeError as exc:
        return None, f"stdout was not valid JSON: {exc}\n---\n{raw[:600]}"


def no_traceback(proc: subprocess.CompletedProcess) -> bool:
    combined = (proc.stdout or "") + (proc.stderr or "")
    return "Traceback (most recent call last)" not in combined


def tail(text: str, limit: int = 400) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return "..." + text[-limit:]


def output(proc: subprocess.CompletedProcess, limit: int = 400) -> str:
    """A short diagnostic string for check details."""
    bits = [f"rc={proc.returncode}"]
    if proc.stdout.strip():
        bits.append("stdout: " + tail(proc.stdout, limit))
    if proc.stderr.strip():
        bits.append("stderr: " + tail(proc.stderr, limit))
    return "\n".join(bits)


def install_solution(mission: Mission, mdir: Path) -> list[Path]:
    """Write the reference solution into a mission directory."""
    written: list[Path] = []
    for rel, content in mission.solution.items():
        path = mdir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if content.startswith("#!") or path.suffix == ".sh":
            path.chmod(0o755)
        written.append(path)
    if mission.post_install is not None:
        mission.post_install(mdir)
    return written
