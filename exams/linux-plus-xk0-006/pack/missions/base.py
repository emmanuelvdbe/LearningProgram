"""Shared helpers for the XK0-006 mission pack.

The heavy lifting lives in :mod:`curriculum.missions.base` so the two Linux+
packs behave the same way.  These helpers add a little JSON-oriented sugar
used by most XK0-006 checkers.
"""
from __future__ import annotations

import json
from pathlib import Path

from curriculum.missions.base import (  # noqa: F401  (re-exported for packs)
    Check,
    Mission,
    fresh_dir,
    install_solution,
    no_traceback,
    output,
    parse_json,
    run_command,
    run_script,
    tail,
    write_file,
)


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def script_json(
    script: Path,
    *args: object,
    cwd: Path | None = None,
    timeout: float = 30,
) -> tuple[dict | None, object]:
    """Run a Python script that prints one JSON object.

    Returns ``(object, completed_process)``.  A non-dict result is returned as
    ``None`` with an explanatory process whose stderr is useful in a check.
    """
    proc = run_script(script, *args, cwd=cwd, timeout=timeout)
    if proc.returncode != 0:
        return None, proc
    data, error = parse_json(proc)
    if error:
        proc.stderr = (proc.stderr or "") + "\n" + error
        return None, proc
    if not isinstance(data, dict):
        proc.stderr = (proc.stderr or "") + "\nJSON root must be an object"
        return None, proc
    return data, proc


def check_file(checks: list[Check], path: Path, label: str | None = None) -> bool:
    ok = path.is_file()
    checks.append(Check(label or f"{path.name} exists", ok, str(path)))
    return ok


def has_keys(data: object, keys: set[str]) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "result is not a JSON object"
    missing = sorted(keys - data.keys())
    return not missing, f"missing keys: {missing}" if missing else "all keys present"


def text_contains(path: Path, needles: list[str]) -> tuple[bool, str]:
    if not path.is_file():
        return False, f"{path} does not exist"
    text = path.read_text(encoding="utf-8", errors="replace")
    missing = [needle for needle in needles if needle not in text]
    return not missing, f"missing: {missing}" if missing else "all required text present"


def file_mode(path: Path) -> int:
    return path.stat().st_mode & 0o7777
