# Module 8 — Exceptions: read files without crashing

## Why this matters for Linux+

A sysadmin script runs unattended. If it dies with a traceback because a file
is missing or unreadable, the cron mail may go unread and the job silently
stops. Linux+ troubleshooting expects you to read errors, isolate failures, and
keep the rest of the system working.

This module turns “it works on my machine” into “it fails predictably and
tells you why.”

## Reading a traceback

```text
Traceback (most recent call last):
  File "/home/deb/safe_read.py", line 12, in <module>
    with open(path) as fh:
         ^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '/srv/hosts.csv'
```

Read it bottom-up:

1. **Exception type:** `FileNotFoundError`.
2. **Message:** which path, which errno.
3. **Call chain:** the line that failed and its callers.

The last line is usually the most informative. The first line is not the cause;
it is where Python started.

## `try` / `except`

```python
try:
    with open(path, encoding="utf-8") as fh:
        data = fh.read()
except FileNotFoundError:
    print(f"ERROR: file not found: {path}", file=sys.stderr)
    sys.exit(2)
```

Catch the **narrowest** exception that you can actually handle. `except
Exception:` around a whole program hides typos, programming errors, and
KeyboardInterrupt-style bugs.

Multiple exceptions:

```python
try:
    ...
except (FileNotFoundError, IsADirectoryError) as exc:
    print(f"ERROR: cannot read {path}: {exc}", file=sys.stderr)
except PermissionError:
    print(f"ERROR: permission denied: {path}", file=sys.stderr)
except OSError as exc:
    print(f"ERROR: I/O failure: {exc}", file=sys.stderr)
```

Order matters: `PermissionError` and `FileNotFoundError` are subclasses of
`OSError`, so put the specific ones first.

### The exception hierarchy (selected)

```text
BaseException
├── SystemExit
├── KeyboardInterrupt
└── Exception
    ├── OSError
    │   ├── FileNotFoundError
    │   ├── PermissionError
    │   ├── IsADirectoryError
    │   └── TimeoutError
    ├── ValueError
    ├── TypeError
    ├── KeyError
    └── json.JSONDecodeError (subclass of ValueError)
```

Catching `Exception` does not catch `SystemExit` or `KeyboardInterrupt`
(both inherit directly from `BaseException`). That is usually what you want.

## `else` and `finally`

```python
try:
    fh = open(path, encoding="utf-8")
except OSError as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    return 2
else:
    with fh:
        process(fh)       # only runs if open succeeded
finally:
    print("attempt finished")   # always runs
```

`with open(...)` already handles closing, so `finally` is mostly for cleanup
that is not a context manager (temporary directories, locks, sockets). `else`
keeps the happy path out of the `try`, which makes it clearer what you expect
to fail.

## EAFP vs LBYL

Two styles:

**LBYL — Look Before You Leap:**

```python
if os.path.exists(path):
    with open(path) as fh:
        ...
```

The file can disappear between the check and the open (a race condition).

**EAFP — Easier to Ask Forgiveness than Permission:**

```python
try:
    with open(path) as fh:
        ...
except FileNotFoundError:
    ...
```

EAFP is usually better for files, sockets, and permissions because the
operation itself is the check. Use LBYL when the check is cheap and the
operation is expensive or destructive.

## Raising your own errors

```python
def validate_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError(f"port out of range: {port}")
```

Raising is how a function refuses invalid input. The caller decides whether to
recover, print, or exit.

Custom exceptions document intent:

```python
class MalformedInventory(ValueError):
    """Raised when a CSV row has the wrong shape."""


raise MalformedInventory("expected 3 fields")
```

Do not invent an exception when a built-in one fits. `ValueError` is right for
“right type, wrong value.”

## Exit codes and stderr

The mission maps failures to distinct statuses:

| Condition | Status |
|---|---|
| success | 0 |
| file not found | 2 |
| permission denied | 3 |
| malformed content | 4 |

Why distinct codes? A wrapper script can react differently:

```bash
python3 safe_read.py hosts.csv
case $? in
  0) echo "loaded" ;;
  2) echo "missing file; using defaults" ;;
  3) echo "fix permissions" ;;
  4) echo "bad data; page the owner" ;;
esac
```

Print the human explanation on stderr, return the numeric code on stdout’s
exit status. Do not mix them.

## Never swallow errors silently

```python
try:
    ...
except Exception:
    pass          # BAD
```

This turns a real failure into a mysterious wrong result. If you must ignore an
error, say why in a comment and catch the narrow type:

```python
try:
    path.unlink()
except FileNotFoundError:
    pass          # already gone; deletion is idempotent
```

## Validating CSV

```python
import csv

with open(path, newline="", encoding="utf-8") as fh:
    reader = csv.reader(fh)
    header = next(reader)
    if header != ["host", "port", "role"]:
        raise ValueError("bad header")
    for line_no, row in enumerate(reader, start=2):
        if len(row) != 3:
            raise ValueError(f"row {line_no}: expected 3 fields, got {len(row)}")
```

Use `newline=""` with `csv` so quoted fields containing newlines work
correctly. Do not split on commas yourself; CSV quoting is surprisingly subtle.

## Guided walkthrough

```bash
cd "$(python3 main.py doctor | sed -n 's/^  \[ok\] Lab: //p' | head -1)" 2>/dev/null || true
mkdir -p 08_safe_reader
cd 08_safe_reader
```

Reproduce each failure before handling it:

```bash
python3 - <<'PY'
for path in ("fixtures/nope.csv", "fixtures/locked.csv", "fixtures/bad.csv"):
    try:
        with open(path, encoding="utf-8") as fh:
            print(path, "opened")
    except Exception as exc:
        print(path, type(exc).__name__, exc)
PY
```

Observe that `locked.csv` is mode `0000`. As your user it is unreadable; as
root it is not. Good tests account for the user running them.

Then implement `safe_read.py` with one `try` around the open/read and specific
`except` clauses. Test all four paths:

```bash
python3 safe_read.py fixtures/good.csv;   echo "status=$?"
python3 safe_read.py fixtures/nope.csv;   echo "status=$?"
python3 safe_read.py fixtures/locked.csv; echo "status=$?"
python3 safe_read.py fixtures/bad.csv;    echo "status=$?"
```

Confirm there are no tracebacks:

```bash
python3 safe_read.py fixtures/nope.csv 2>&1 | grep -c Traceback   # 0
```

Verify:

```bash
python3 main.py verify 8
```

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| `except:` | catches Ctrl-C and `SystemExit` | catch specific types |
| Catching `OSError` before `PermissionError` | permission branch never runs | specific first |
| Printing errors to stdout | breaks pipelines | `file=sys.stderr` |
| Returning 0 after a failure | automation thinks it worked | return non-zero |
| `open()` without `encoding` | locale-dependent decoding | `encoding="utf-8"` |
| Using `os.path.exists` then `open` | race condition | EAFP |
| `except Exception: pass` | silent corruption | narrow catch + comment |
| Not closing files | descriptor leaks | `with` |

## Mission checklist

- [ ] `08_safe_reader/safe_read.py` exists.
- [ ] Valid CSV prints `OK: N records`, exit 0.
- [ ] Missing file exits 2, message on stderr.
- [ ] Unreadable file exits 3, message on stderr.
- [ ] Malformed row exits 4, names the line and field count.
- [ ] Empty file is treated as malformed, exit 4.
- [ ] No traceback for any of these cases.

Then run:

```bash
python3 main.py verify 8
```

## Extra practice

1. Add `--strict` to stop at the first bad row and `--skip-bad` to continue
   while reporting the count.
2. Add a summary of duplicates by `host`.
3. Validate ports are integers in 1–65535 and roles are in a known set.
4. Log errors with the `logging` module (module 14) instead of `print`.
5. Test the script as root and explain why the permission case differs.
