# Module 3 — Decisions, comparisons, and exit codes

## Why this matters for Linux+

A cron job does not read your output. It reads your exit status. `systemd`
uses exit codes to decide whether a service succeeded. Shell `&&` and `||`
branch on them. Monitoring systems alert on them.

This module builds a disk guard: a tiny script that answers one question
(“is the root filesystem too full?”) and communicates the answer the way Linux
expects — with a status code.

## Booleans and comparisons

```python
>>> 10 > 3
True
>>> "abc" == "ABC"
False
>>> 5 != 5
False
>>> 0 <= 50 <= 100        # chained comparison, same as 0 <= 50 and 50 <= 100
True
```

Comparison operators: `==  !=  <  <=  >  >=`.

Do not confuse `=` (assignment) with `==` (comparison). Python will raise a
`SyntaxError` for `if x = 1:`, which is friendlier than C.

Boolean operators:

```python
ready = is_mounted and has_space
alarm = usage > 90 or errors > 0
safe = not dangerous
```

`and` / `or` short-circuit: the second expression is not evaluated if the
first already decides the result. This is useful for guards:

```python
if user and user.is_active:
    ...
```

## Truthiness

Every object has a truth value. The falsy values are:

```python
False, None, 0, 0.0, "", [], {}, set(), ()
```

Everything else is truthy — including the string `"0"` and the string
`"False"`. This is a classic bug source when reading command output:

```python
value = "0"          # from a config file
if value:
    print("enabled") # prints! "0" is a non-empty string
```

Convert explicitly when the source is text:

```python
threshold = int(value)
if threshold:
    ...
```

## if / elif / else

```python
usage = 91.4

if usage >= 95:
    level = "critical"
elif usage >= 85:
    level = "warning"
else:
    level = "ok"
```

Only the first matching branch runs. Order matters: put the most severe or
most specific condition first.

Nested conditions work but should be rare:

```python
if path.exists():
    if path.is_dir():
        ...
```

Prefer early returns in functions:

```python
def check(path):
    if not path.exists():
        return "missing"
    if not path.is_dir():
        return "not a directory"
    return "ok"
```

Conditional expression (ternary):

```python
label = "CRITICAL" if usage >= threshold else "OK"
```

Use it for short, obvious choices. Do not nest ternaries.

## `sys.argv` and `sys.exit`

`sys.argv` is a list of strings:

```python
import sys
# python3 disk_guard.py 85
sys.argv == ["disk_guard.py", "85"]
```

`sys.exit(code)` raises `SystemExit`, which the interpreter turns into the
process status:

```python
sys.exit(0)   # success
sys.exit(1)   # general failure
sys.exit(2)   # usage error (a common convention)
```

The mission uses `main() -> int` plus `sys.exit(main())`. That keeps the logic
testable and still gives the shell a real status.

## Exit-status conventions

| Code | Conventional meaning |
|---|---|
| 0 | success |
| 1 | general failure / “not healthy” |
| 2 | command-line usage error |
| 126 | found but not executable |
| 127 | command not found |
| 128+N | killed by signal N (e.g. 130 = Ctrl-C) |

Check a status in the shell:

```bash
python3 disk_guard.py 0
echo "status=$?"
# status=1
```

Use it:

```bash
if python3 disk_guard.py 90; then
    echo "disk is fine"
else
    echo "disk needs attention"
fi

python3 disk_guard.py 90 && echo fine || echo alert
```

## Computing disk usage

`shutil.disk_usage` returns total/used/free in bytes:

```python
import shutil

usage = shutil.disk_usage("/")
percent = usage.used / usage.total * 100
print(f"{percent:.1f}% used")
```

Guard against division by zero? On a real filesystem `total > 0`, but a robust
tool could check. The mission does not require it; a reviewer might.

## A complete pattern

```python
#!/usr/bin/env python3
"""Exit-code driven disk guard."""
import shutil
import sys


def main() -> int:
    if len(sys.argv) > 2:
        print("usage: disk_guard.py [threshold]", file=sys.stderr)
        return 2
    try:
        threshold = float(sys.argv[1]) if len(sys.argv) == 2 else 90.0
    except ValueError:
        print("usage: disk_guard.py [threshold]", file=sys.stderr)
        return 2

    usage = shutil.disk_usage("/")
    percent = usage.used / usage.total * 100
    if percent >= threshold:
        print(f"CRITICAL: / is {percent:.1f}% used (threshold {threshold:g}%)")
        return 1
    print(f"OK: / is {percent:.1f}% used (threshold {threshold:g}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Notes:

- `float()` accepts `"90"`, `"90.5"`, `"1e2"`.
- `:g` avoids printing `90.0` when the input was an integer.
- Errors go to **stderr**.
- The `len(sys.argv) > 2` check prevents silently ignoring extra arguments.

## Guided walkthrough

```bash
cd "$(python3 main.py doctor | sed -n 's/^  \[ok\] Lab: //p' | head -1)" 2>/dev/null || true
mkdir -p 03_disk_guard
cd 03_disk_guard
```

Experiment with status codes before writing the full script:

```bash
python3 - <<'PY'
import shutil, sys
u = shutil.disk_usage("/")
print("total", u.total, "used", u.used, "free", u.free)
print(f"{u.used / u.total * 100:.1f}% used")
PY

# A one-line exit test
python3 -c 'import sys; sys.exit(7)'; echo "status=$?"
```

After writing `disk_guard.py`:

```bash
python3 disk_guard.py 101; echo "status=$?"   # expect 0 / OK
python3 disk_guard.py 0;   echo "status=$?"   # expect 1 / CRITICAL
python3 disk_guard.py nope; echo "status=$?"  # expect 2, usage on stderr
python3 disk_guard.py 101 102; echo "status=$?"  # expect 2
```

Separate streams to prove your diagnostics are on stderr:

```bash
python3 disk_guard.py nope 2>/dev/null
python3 disk_guard.py nope 1>/dev/null
```

Verify:

```bash
python3 main.py verify 3
```

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| `if usage = threshold:` | `SyntaxError` | use `==` for comparison |
| Comparing `float` with `"90"` | `TypeError` | convert the argument once |
| Printing usage errors to stdout | monitoring captures them as data | use `file=sys.stderr` |
| Returning `None` from `main()` | `sys.exit(None)` gives 0 even on failure | return an int everywhere |
| Using `exit()` in library code | kills the interpreter | return a status; exit at the top |
| Treating `"0"` as false | wrong branch | convert text to int/float first |

## Mission checklist

- [ ] `03_disk_guard/disk_guard.py` exists.
- [ ] `threshold 101` → exit 0, output starts `OK`.
- [ ] `threshold 0` → exit 1, output contains `CRITICAL` and `threshold 0`.
- [ ] Non-numeric threshold → exit 2, usage on stderr, no traceback.
- [ ] No argument → default 90, exit 0 or 1, output contains `%`.
- [ ] Too many arguments → exit 2.

Then run:

```bash
python3 main.py verify 3
```

## Extra practice

1. Add `--path` so the guard can check `/var` or `/home`.
2. Add a `--warn` threshold: exit 1 for warning, 2 for critical.
3. Emit a one-line JSON object instead of human text; keep the same exit
   codes. Which interface is easier for cron to consume?
4. Run the guard from a systemd timer and inspect `systemctl status`.
