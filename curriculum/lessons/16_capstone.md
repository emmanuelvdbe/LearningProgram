# Module 16 — Capstone: package a Linux+ security audit kit

## Why this matters for Linux+

The exam domains are not isolated. A real audit combines:

- **System management:** users, services, filesystems.
- **Security:** UID 0, empty passwords, SUID, world-writable files.
- **Scripting/automation:** parsing, JSON, CLI, exit codes.
- **Troubleshooting:** read-only inspection, robust error handling.

This capstone asks you to package those skills as `auditkit`, a small Python
package you can run with `python3 -m auditkit`. You have already written every
piece in earlier missions; the new skill is composition.

## From script to package

A single `audit.py` works. A package is better when the tool grows:

```text
16_audit_kit/
└── auditkit/
    ├── __init__.py      # package marker, version, public API
    ├── core.py          # pure functions: parse, scan, audit
    └── __main__.py      # CLI entry point for python -m
```

Why:

- `core.py` is importable and testable without running the CLI.
- `__main__.py` keeps argument parsing and I/O at the edge.
- `__init__.py` controls what `import auditkit` exposes.
- The package can be installed later with a `pyproject.toml`.

## `__init__.py`

```python
"""linuxplus audit kit."""

__version__ = "1.0.0"
```

Keep it light. Importing a package should not run an audit or read files. Heavy
side effects at import time make tests and tooling slow and surprising.

If you want a public API:

```python
from .core import audit

__all__ = ["audit", "__version__"]
```

## `__main__.py`

```python
import argparse
import json
import sys
from pathlib import Path

from .core import audit


def main() -> int:
    parser = argparse.ArgumentParser(prog="auditkit")
    parser.add_argument("--root", default="/")
    parser.add_argument("--out", default="audit-report.json")
    args = parser.parse_args()
    root = Path(args.root)
    if not root.is_dir():
        print(f"ERROR: root not found: {root}", file=sys.stderr)
        return 2
    report = audit(root)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"risk_score={report['risk_score']} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run it:

```bash
python3 -m auditkit --root sample_root --out report.json
```

The relative import (`from .core import audit`) works because the module is
executed as part of the package. Running `python3 auditkit/__main__.py` directly
will fail with “attempted relative import with no known parent package”. Use
`-m`.

## Composition

`audit()` should read like a table of contents:

```python
def audit(root: Path) -> dict:
    users = parse_passwd(root / "etc/passwd")
    permissions = scan_permissions(root)
    services = scan_services(root)
    ...
    return {...}
```

Each helper does one job and returns plain data:

- `parse_passwd(path) -> list[dict]`
- `scan_permissions(root) -> dict`
- `scan_services(root) -> dict`
- `inspect_unit(path) -> dict`

Plain data is easy to test, serialize, and combine. Avoid passing a logger,
argparse namespace, or output stream into core logic. Keep I/O at the edges.

## The audit rules

### Users

```python
uid0 = sorted(user["name"] for user in users if user["uid"] == 0)
uid0_nonroot = [name for name in uid0 if name != "root"]
no_password = sorted(user["name"] for user in users if user["password"] == "")
human_count = sum(1 for user in users if 1000 <= user["uid"] < 65534)
```

Why `uid0_nonroot` separately? UID 0 is root’s identity. Any *other* name with
UID 0 is a backdoor or a serious misconfiguration. The risk score should count
the anomaly, not root itself.

### Empty passwords

An empty password field is not the same as a locked account:

| Field | Meaning |
|---|---|
| `""` | no password required (dangerous) |
| `*` | disabled/locked (common) |
| `!` | locked (common) |
| `$6$...` | hashed password |

The mission counts only `""`.

### Permissions

```python
if mode & stat.S_IWOTH:
    world_writable.append(rel)
if mode & stat.S_ISUID:
    suid.append(rel)
```

Store paths relative to the root, with `/` separators. Do not follow symlinks.

### Services

A unit is valid for this audit if it has a `[Service]` section and a non-empty
`ExecStart`. `running_as_root` means valid and either no `User=` or `User=root`.

```python
running_as_root = sorted(
    unit["name"]
    for unit in units
    if unit["valid"] and (unit["user"] is None or unit["user"] == "root")
)
```

Long-running network services should usually have a dedicated user. That is a
Linux+ security principle, not just a Python exercise.

### Risk score

```python
risk_score = (
    len(uid0_nonroot)
    + len(no_password)
    + len(world_writable)
    + len(suid)
    + len(running_as_root)
)
```

A risk score is a communication tool. Document exactly what it counts. Do not
pretend it is a CVSS score. The value here is that the same input always
produces the same number and each component is visible in the report.

## Read-only by design

An audit must not change what it measures. Concretely:

- open files for reading only (`"r"` / `Path.read_text`),
- never `chmod`, `unlink`, `rename`, or write inside the audited tree,
- write the report to a separate output path,
- skip sockets/devices rather than opening them.

This is both safe and testable. The verifier can run the audit twice and compare.

## Error handling at the edges

Core helpers should tolerate missing files where it makes sense:

```python
try:
    text = path.read_text(encoding="utf-8", errors="replace")
except OSError:
    return []
```

But the CLI should reject a missing `--root` with exit 2. “Nothing to audit” is
a usage error, not an empty report. Distinguish “the tree exists but has no
users” from “you pointed me at the wrong path.”

## Report design

```json
{
  "generated_at": "2026-11-12T18:00:00+00:00",
  "root": "/srv/fixture",
  "users": {
    "uid0": ["root", "toor"],
    "uid0_nonroot": ["toor"],
    "no_password": ["toor"],
    "human_count": 2
  },
  "permissions": {
    "world_writable": ["etc/world.txt"],
    "suid": ["etc/suid.bin"]
  },
  "services": {
    "count": 3,
    "valid": ["backup.service", "web.service"],
    "invalid": ["evil.service"],
    "running_as_root": ["web.service"]
  },
  "risk_score": 5
}
```

Properties of a good report:

- deterministic ordering (sort every list),
- explicit null/empty values,
- timestamps in ISO 8601 with a time zone,
- paths relative to the audited root,
- no secrets (never include password hashes),
- a stable schema you can version later.

## Packaging (optional next step)

A minimal `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "linuxplus-auditkit"
version = "1.0.0"
description = "Read-only Linux security audit"
requires-python = ">=3.10"

[project.scripts]
auditkit = "auditkit.__main__:main"
```

Then:

```bash
python3 -m pip install --user -e .
auditkit --root sample_root
```

Now it is a real command, not a folder of scripts.

## Guided walkthrough

```bash
cd "$(python3 main.py doctor | sed -n 's/^  \[ok\] Lab: //p' | head -1)" 2>/dev/null || true
mkdir -p 16_audit_kit/auditkit
cd 16_audit_kit
```

Inspect the provided sample tree:

```bash
find sample_root -printf '%M %p\n' | sort
cat sample_root/etc/passwd
for f in sample_root/etc/systemd/system/*.service; do echo "== $f"; cat "$f"; done
```

Build the three files, then run:

```bash
python3 -m auditkit --help
python3 -m auditkit --root sample_root --out report.json
python3 -m json.tool report.json
```

Test the components in the REPL:

```bash
python3 - <<'PY'
from pathlib import Path
from auditkit.core import parse_passwd, scan_permissions, scan_services
root = Path("sample_root")
print(parse_passwd(root / "etc/passwd"))
print(scan_permissions(root))
print(scan_services(root))
PY
```

Verify:

```bash
python3 main.py verify 16
```

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| Running `python3 auditkit/__main__.py` | relative import error | `python3 -m auditkit` |
| Importing core in `__init__` with side effects | slow/fragile imports | keep `__init__` light |
| Following symlinks in the audit | false positives, escapes root | `lstat`, skip links |
| Counting root in `uid0_nonroot` | inflated risk score | filter `name != "root"` |
| Counting `*`/`!` as empty passwords | false positives | only `""` |
| Writing the report inside the audited tree | audit modifies target | separate `--out` |
| Unsorted lists | unstable diffs | sort every list |
| Hard-coding fixture paths | fails the verifier | take `--root` |
| Crashing on a missing `/etc/passwd` | no report for partial trees | return empty lists |
| No `--help` documentation | unusable CLI | argparse does it for you |

## Mission checklist

- [ ] `16_audit_kit/auditkit/__init__.py` exists.
- [ ] `16_audit_kit/auditkit/__main__.py` exists.
- [ ] `core.py` separates parse/scan/audit logic (recommended).
- [ ] `python3 -m auditkit --help` works.
- [ ] `--root` audits the fixture; `--out` writes the report.
- [ ] Users: `uid0`, `uid0_nonroot`, `no_password`, `human_count`.
- [ ] Permissions: relative, sorted world-writable and SUID paths.
- [ ] Services: count, valid, invalid, running_as_root.
- [ ] `risk_score` matches the documented sum.
- [ ] Missing root exits 2 cleanly.
- [ ] The audited tree is unchanged.

Then run:

```bash
python3 main.py verify 16
```

## Where to go next

You now have a toolkit of patterns, not just syntax. Good next steps:

1. Add unit tests for every core function (`tests/test_core.py`).
2. Add a `--json`/`--text` report mode and a human summary.
3. Add checks for SSH config, `fstab` options (`nosuid`, `noexec`), and
   password aging in `/etc/shadow` (read-only, requires root).
4. Add a `--fail-on-risk N` option for CI.
5. Package it with `pyproject.toml` and run it in a container.
6. Wire it into a systemd timer and ship the JSON to a monitoring system.

For the exam, be able to explain every line: why `lstat`, why `S_IMODE`, why
`None` vs `""`, why exit 2, why sort, and why the audit is read-only.
