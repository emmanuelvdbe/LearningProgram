# Module 7 — Pathlib and file metadata: the janitor

## Why this matters for Linux+

Disk cleanup is a recurring Linux+ scenario: old logs, temporary files,
abandoned backups. The shell answer is `find /var/tmp -name '*.tmp' -mtime +7
-delete`. The Python answer gives you logging, safety checks, and a dry-run
mode that a production team can review before anything disappears.

This module builds a file janitor. It also teaches the most important safety
habit in automation: **make destructive operations opt-in**.

## `pathlib` vs `os.path`

Both work. `pathlib` is clearer and is the modern default:

```python
from pathlib import Path

log = Path("/var/log/syslog")
print(log.name)          # syslog
print(log.parent)        # /var/log
print(log.suffix)        # .log
print(log.exists())
print(log.is_file())
```

Build paths with `/`:

```python
base = Path("/var/log")
candidate = base / "nginx" / "access.log"
```

Never concatenate with string `+`; it breaks on trailing slashes and is harder
to read.

Useful methods:

| Method | Meaning |
|---|---|
| `.exists()` | path exists (file, dir, or symlink) |
| `.is_file()` / `.is_dir()` | type check |
| `.stat()` | metadata (`st_size`, `st_mtime`, `st_mode`) |
| `.read_text()` / `.write_text()` | small text files |
| `.glob("*.tmp")` | non-recursive pattern |
| `.rglob("*.tmp")` | recursive pattern |
| `.relative_to(root)` | path relative to a base |
| `.unlink()` | delete a file |
| `.rmdir()` | delete an empty directory |

`Path` objects are immutable: `path.with_suffix(".gz")` returns a new path, it
does not modify `path`.

## Reading and writing text

```python
text = Path("notes.txt").read_text(encoding="utf-8")
Path("out.txt").write_text("hello\n", encoding="utf-8")
```

Convenient for configuration and reports. For line-by-line processing of large
files, use `with open(...)` as in module 5.

Always pass `encoding="utf-8"` explicitly. The default depends on the locale
and can differ between a laptop and a server. That is exactly the kind of bug
that appears only in production.

## Metadata: mtime, size, mode

```python
info = Path("old.tmp").stat()
print(info.st_size)                 # bytes
print(info.st_mtime)                # seconds since the epoch (float)
print(info.st_mtime_ns)             # nanoseconds
print(info.st_mode)                 # includes file type + permission bits
```

Convert a timestamp for humans:

```python
from datetime import datetime

print(datetime.fromtimestamp(info.st_mtime).isoformat())
```

Age in seconds:

```python
import time

age_seconds = time.time() - info.st_mtime
age_days = age_seconds / 86400
```

Using `time.time()` and file mtimes is fine. Be aware of clock skew on network
filesystems and of files whose mtime is in the future.

## Recursive matching

```python
root = Path("/var/tmp")
for path in root.rglob("*.tmp"):
    if path.is_file():
        ...
```

`rglob` can follow into directories you cannot read. In Python 3.13 it may
raise `PermissionError`; catch `OSError` or run with appropriate permissions.
On older versions it silently skips some directories. Do not assume identical
behaviour across versions.

Sort results for deterministic output:

```python
matches = sorted(path for path in root.rglob("*.tmp") if path.is_file())
```

## The dry-run pattern

Destructive tools should have two modes:

1. **Dry run (default):** print what would happen.
2. **Apply:** perform the action, but only when explicitly requested.

```python
parser.add_argument("--apply", action="store_true")
...
if args.apply:
    path.unlink()
    print(f"DELETED: {rel}")
else:
    print(f"WOULD DELETE: {rel}")
```

Why default to dry run? Because a typo in a glob or a wrong root directory can
erase data. A reviewable list costs nothing. `rsync --dry-run`, `apt --simulate`,
and `terraform plan` follow the same principle.

## Safe deletion

Before unlinking:

- Confirm the path is inside the intended root.
- Confirm it is a regular file, not a directory or symlink.
- Confirm it matches the requested age and pattern.
- Consider a `--min-size` or `--exclude` guard.

```python
if path.is_file() and path.is_relative_to(root):
    path.unlink()
```

`Path.is_relative_to` (3.9+) protects against `..` tricks when paths come from
outside. In this mission the paths come from `rglob`, but the habit matters.

Deletion is permanent. A recycle bin is a desktop feature, not a Linux server
feature. Dry-run first.

## Glob patterns

| Pattern | Matches |
|---|---|
| `*.tmp` | names ending in `.tmp` in the current directory |
| `**/*.log` | all log files below (with `glob`, not `rglob`) |
| `backup-????-*.tar.gz` | `?` is one character |
| `[0-9]*` | names starting with a digit |

`rglob("*.tmp")` is equivalent to `glob("**/*.tmp")`. Use `rglob` for a tree.

## Relative paths in output

```python
rel = path.relative_to(root)
print(rel)
```

Output paths relative to the scanned directory. Absolute paths leak the lab
location into reports and make them non-portable and harder to compare.

On Windows, `str(rel)` uses backslashes. On Linux you will see `/`. If a report
crosses platforms, use `rel.as_posix()`.

## Guided walkthrough

```bash
cd "$(python3 main.py doctor | sed -n 's/^  \[ok\] Lab: //p' | head -1)" 2>/dev/null || true
mkdir -p 07_file_janitor
cd 07_file_janitor
```

Explore the sample sandbox:

```bash
find sandbox -type f -printf '%TY-%Tm-%Td %p\n' | sort
stat sandbox/old.tmp
python3 - <<'PY'
import time
from pathlib import Path
for p in sorted(Path("sandbox").rglob("*.tmp")):
    age = (time.time() - p.stat().st_mtime) / 86400
    print(f"{age:5.1f} days  {p.relative_to('sandbox')}")
PY
```

Write `janitor.py`. Test the safe path first:

```bash
python3 janitor.py sandbox --days 7
python3 janitor.py sandbox --days 7 --pattern '*.log'
```

Confirm nothing changed:

```bash
find sandbox -type f | sort
```

Then apply on a copy, not the original, if you want a second experiment:

```bash
cp -a sandbox /tmp/janitor-demo
python3 janitor.py /tmp/janitor-demo --days 7 --apply
find /tmp/janitor-demo -type f | sort
rm -rf /tmp/janitor-demo
```

Verify:

```bash
python3 main.py verify 7
```

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| Deleting by default | unrecoverable surprise | require `--apply` |
| Using `mtime > cutoff` | deletes new files | older means `mtime < cutoff` |
| Comparing seconds to days | wrong age | convert: days * 86400 |
| `root.rglob(pattern)` without `is_file()` | tries to delete directories | filter with `is_file()` |
| String path concatenation | double slashes / wrong paths | use `Path / "name"` |
| Assuming `Path.stat()` cannot fail | race with deletion | catch `FileNotFoundError`/`OSError` |
| Using local time for file ages | DST confusion | epoch seconds are timezone-free |
| Not sorting output | unstable diffs | sort matches |

## Mission checklist

- [ ] `07_file_janitor/janitor.py` exists.
- [ ] Takes a directory, `--pattern`, `--days`, `--apply`.
- [ ] Dry run lists paths relative to the directory and deletes nothing.
- [ ] `--apply` deletes only old matching files.
- [ ] `new.tmp`, `keep.log`, and `sub/keep.txt` survive.
- [ ] Missing directory exits 2 with stderr, no traceback.
- [ ] Prints `no matching files` when nothing matches.

Then run:

```bash
python3 main.py verify 7
```

## Extra practice

1. Add `--exclude GLOB` and `--max-size BYTES`.
2. Send deleted files to a quarantine directory instead of unlinking them.
3. Add `--json` output with path, age_days, and size.
4. Run the janitor from a systemd timer with `--apply`; log the output.
5. Replace `rglob` with `os.walk` and compare error behaviour on unreadable
   directories.
6. Add a confirmation prompt when more than N files would be deleted.
