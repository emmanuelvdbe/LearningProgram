# Module 18 — Python administration and virtual environments

> **Exam objective:** Linux+ 4.3 — Given a scenario, use Python basics for
> administration.
> **Study time:** about 120 minutes, including the mission.
> **Mission:** `disk_report.py`, `requirements.txt`, and `setup.sh` — a
> reproducible disk-usage report that runs from a virtual environment.

## What the exam expects

- **environments:** `python3 -m venv`, `pip`, `requirements.txt`, isolation
  from the system interpreter,
- **language basics:** variables, types, control flow, functions, classes,
  exceptions, modules and packages,
- **standard library:** `pathlib`, `os`, `sys`, `subprocess`, `json`,
  `argparse`, `csv`, `re`, `logging`, `dataclasses`,
- **style:** PEP 8, docstrings, type hints, `if __name__ == "__main__"`,
- **distribution:** shebang, executable bit, `pyproject.toml`,
- **use cases:** parsing command output, generating reports, idempotent
  configuration, calling system tools.

The exam does not test deep Python. It tests whether you can write a small,
readable, reliable tool and run it in a reproducible way.

## Virtual environments

A virtual environment is a directory with its own `python`, `pip`, and
`site-packages`. It isolates your project from the system Python, which is
managed by the distribution and must not be polluted.

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
deactivate
```

On a minimal or air-gapped system, `ensurepip` may be missing and
`python3 -m venv .venv` fails with “ensurepip is not available”. Two options:

```bash
python3 -m venv --without-pip .venv      # environment without pip
sudo apt install python3-venv            # Debian: install ensurepip
sudo dnf install python3-pip             # RHEL family
```

`--without-pip` still gives you an isolated interpreter, which is enough to run
a script that only uses the standard library. The mission uses this path
because the sandbox lacks `ensurepip`.

Always call the environment's interpreter explicitly in automation:

```bash
.venv/bin/python disk_report.py --root .
```

Do not rely on `source activate` in a cron job or a systemd unit.

## `requirements.txt` and pinning

```
PyYAML==6.0.2
requests==2.32.3
```

- **pin exact versions** (`==`), never `latest`,
- generate with `pip freeze > requirements.txt` after a known-good install,
- use a lock file for transitive dependencies,
- keep dev-only tools in a separate file (`requirements-dev.txt`),
- scan for CVEs before deploying.

Install:

```bash
pip install -r requirements.txt
pip install --no-cache-dir -r requirements.txt
pip check
```

## Language basics you will actually use

### Types and control flow

```python
name = "web01"
count = 3
ratio = 0.75
active = True
hosts = ["web01", "web02"]
pairs = {"web01": "10.0.0.11"}
unique = {"a", "b"}

if count > 2 and active:
    print(f"{name} has {count} connections")
elif count == 0:
    print("idle")
else:
    print("low")

for host in hosts:
    print(host)

while count > 0:
    count -= 1
```

f-strings (`f"{value}"`) are the modern formatting tool. `None` is “no value”;
test with `is None`, not `== None`.

### Functions, types, and docstrings

```python
def percent(used: int, total: int) -> float:
    """Return used/total as a percentage, or 0.0 when total is zero."""
    if total <= 0:
        return 0.0
    return used / total * 100
```

Type hints document intent and are checked by `mypy`, but Python does not
enforce them at runtime.

### Exceptions

```python
try:
    text = path.read_text(encoding="utf-8")
except FileNotFoundError:
    print(f"missing: {path}", file=sys.stderr)
    raise SystemExit(2)
except PermissionError as exc:
    print(f"permission denied: {exc}", file=sys.stderr)
    raise SystemExit(3)
```

Catch specific exceptions. A bare `except:` hides bugs. `raise SystemExit(n)`
sets the process exit code.

### Classes and dataclasses

```python
from dataclasses import dataclass

@dataclass
class Filesystem:
    device: str
    mount: str
    used: int
    capacity: int
```

`@dataclass` generates `__init__`, `__repr__`, and `__eq__`, which keeps small
data holders readable.

## The standard library for administration

### `pathlib`

```python
from pathlib import Path

root = Path("rootfs")
for path in sorted(root.glob("boot/vmlinuz-*")):
    print(path.name)
text = Path("etc/default/grub").read_text(encoding="utf-8")
Path("out/report.json").parent.mkdir(parents=True, exist_ok=True)
Path("out/report.json").write_text(json_text, encoding="utf-8")
```

Prefer `pathlib` over string concatenation and `os.path`. It handles separators
and gives you `name`, `stem`, `suffix`, `parent`, `exists()`, `is_file()`, and
`is_dir()`.

### `subprocess`

```python
import subprocess

proc = subprocess.run(
    ["ss", "-tulpn"],
    capture_output=True,
    text=True,
    timeout=10,
    check=False,
)
if proc.returncode != 0:
    print(proc.stderr, file=sys.stderr)
print(proc.stdout)
```

- pass a **list**, not a shell string, to avoid injection,
- `capture_output=True` and `text=True` give you strings,
- `timeout` prevents a hang,
- `check=True` raises on failure; otherwise inspect `returncode`,
- `shell=True` only when you genuinely need shell features, and never with
  untrusted input.

### `json`, `csv`, `argparse`

```python
import argparse, csv, json

parser = argparse.ArgumentParser(description="Disk usage report")
parser.add_argument("--root", default=".", help="mission directory")
parser.add_argument("--threshold", type=int, default=85)
args = parser.parse_args()

print(json.dumps(payload, indent=2, sort_keys=True))

with open("out.csv", "w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(["mount", "used"])
    writer.writerows(rows)
```

`argparse` gives you `-h`, type conversion, defaults, and clear errors for
free. Prefer it over manual `sys.argv` parsing.

### `re`

```python
import re

match = re.search(r"^(\S+)\s+(\d+)%", line)
if match:
    mount, percent = match.group(1), int(match.group(2))
```

Raw strings (`r"..."`) avoid double escaping. Compile a pattern once if you use
it in a loop.

### `logging`

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("disk-report")
log.info("checked %d filesystems", len(filesystems))
```

`logging` writes to stderr by default and supports levels, timestamps, and
handlers. `print` is for program output; `logging` is for diagnostics.

## Style: PEP 8 and readability

- four spaces, no tabs,
- lines ≤ 79–100 characters,
- `snake_case` functions and variables, `CamelCase` classes,
  `UPPER_CASE` constants,
- two blank lines between top-level definitions,
- imports grouped: standard library, third-party, local,
- spaces around operators, no space before `:` in slices,
- docstrings on public functions and modules,
- `if __name__ == "__main__":` guard so the module can be imported.

```python
#!/usr/bin/env python3
"""Report filesystem usage from df output."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    ...
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`from __future__ import annotations` makes type hints lazy, which is handy on
older interpreters. `raise SystemExit(main())` turns the return value into the
process exit code.

Format and lint:

```bash
python -m compileall -q .
python -m py_compile script.py
ruff check .
black --check .
mypy script.py
```

`compileall` byte-compiles without running; a syntax error fails the build.
The mission's `setup.sh` uses byte-compilation as a cheap correctness gate.

## Idempotent administration tools

A configuration tool should be safe to run repeatedly:

```python
def ensure_line(path: Path, line: str) -> bool:
    """Add line to path if absent. Return True when changed."""
    existing = path.read_text(encoding="utf-8").splitlines()
    if line in existing:
        return False
    path.write_text("\n".join([*existing, line]) + "\n", encoding="utf-8")
    return True
```

- return whether you changed something,
- validate input before writing,
- write to a temporary file and rename for atomicity,
- back up the original when the change is risky,
- log what changed.

Same idea as Ansible's “changed” status and systemd's declarative units.

## Packaging a tool

For a single script, a shebang and the executable bit are enough:

```bash
chmod +x disk_report.py
./disk_report.py --root .
```

For a reusable package:

```
project/
  pyproject.toml
  src/apptool/__init__.py
  src/apptool/cli.py
  tests/test_cli.py
```

`pyproject.toml` declares metadata, dependencies, and entry points; `pip
install .` or `pipx install .` puts the command on `PATH`. For administration,
`pipx` is ideal: each tool gets its own environment.

## Mission 18 — what you build

1. **`disk_report.py`** — `--root . --threshold 85`
   - read `fixtures/df.txt`, skip the header, parse device, size, used,
     available, capacity, and mount,
   - use a `@dataclass` for each filesystem and `pathlib.Path` for I/O,
   - print JSON with `filesystems`, `over_threshold` (mounts at or above the
     threshold), `count`, `threshold`, `python`, `executable`, and
     `total_used_gib`,
   - keep lines ≤ 100 characters, spaces (no tabs), and a final newline.
2. **`requirements.txt`** — pinned dependencies, one per line (for example
   `PyYAML==6.0.2`). Never unpinned or `latest`.
3. **`setup.sh`** — `set -euo pipefail`, create `venv/`, and byte-compile the
   script. The sandbox lacks `ensurepip`, so use
   `python3 -m venv --without-pip venv`. On a normal host the lesson shows
   `python3 -m venv .venv` plus `pip install -r requirements.txt`.

The checker runs `venv/bin/python disk_report.py`, so the result must come from
the virtual environment, not the system interpreter. Run
`python3 main.py verify 18`.

## Exam traps

- Installing packages with `sudo pip` pollutes the system Python.
- `venv` is not a security boundary; it is dependency isolation.
- `subprocess` with `shell=True` and untrusted input is command injection.
- A bare `except:` hides the bug you need to see.
- `json.dumps` output is a string; `json.dump` writes to a file.
- `open()` without `encoding=` uses the locale and breaks on other systems.
- A script without `if __name__ == "__main__":` runs on import.
- `pip install -r requirements.txt` with unpinned versions is not reproducible.
- `--without-pip` cannot install packages; it only isolates the interpreter.

## Check yourself

1. What does a virtual environment isolate, and what does it not isolate?
2. Why pin versions in `requirements.txt`?
3. How do you run a script with a specific environment's interpreter?
4. Why pass a list to `subprocess.run` instead of a shell string?
5. What does `@dataclass` generate for you?
6. Which module gives you `-h`, defaults, and type conversion?
7. What is the difference between `print` and `logging`?
8. Why is `if __name__ == "__main__":` useful?

## Going deeper

- Port a shell report to Python with `argparse`, `pathlib`, and `json`, then
  compare readability.
- Add tests with `unittest` and run them from the venv.
- Replace `subprocess` calls with direct file reads where possible and measure
  the difference.
- Package the tool with `pyproject.toml` and install it with `pipx`.
