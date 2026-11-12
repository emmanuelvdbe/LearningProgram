# Module 2 — Variables, types, and f-strings

## Why this matters for Linux+

Every sysadmin script starts by collecting facts: hostname, kernel, CPU count,
free space, load average. On Linux+ you are expected to know where those facts
come from and how to present them without ambiguity. This module builds a
small, parseable system report — the same shape you would feed into
monitoring, an inventory database, or a support ticket.

## Variables are names, not boxes

```python
hostname = "lab01"
cpus = 4
load = 0.42
healthy = True
nothing = None
```

Python is dynamically typed: a name can point at any object, and the object
knows its own type. You do not declare `int cpus`. You can inspect:

```python
>>> type(cpus)
<class 'int'>
>>> isinstance(cpus, int)
True
```

Use `snake_case` for variables and functions, `UPPER_CASE` for constants.
Names are case-sensitive: `Hostname` and `hostname` are different.

Assignment does not copy an object; it binds a name to it. This matters for
mutable objects such as lists (see module 4).

## The core types

### Integers and floats

```python
cpus = 8
free_bytes = 230_000_000_000      # underscores are ignored
free_gib = free_bytes / 1024**3   # true division -> float
whole = 7 // 2                    # floor division -> 3
remainder = 7 % 2                 # 1
power = 2**10                     # 1024
```

| Operator | Meaning | Example |
|---|---|---|
| `+ - * /` | arithmetic; `/` always returns float | `4 / 2 == 2.0` |
| `//` | floor division | `7 // 2 == 3` |
| `%` | remainder | `7 % 2 == 1` |
| `**` | power | `2**10 == 1024` |

Floats are binary approximations. Do not test equality with `==` after
arithmetic; compare with a tolerance or round the displayed value.

### Strings

```python
name = "web01"
path = '/var/log/syslog'          # single or double quotes are equivalent
escaped = "line1\nline2"
raw = r"C:\temp\new"              # raw string: backslashes are literal
multi = """first
second"""
```

Useful operations:

```python
host = "web01.example.com"
host.lower()              # 'web01.example.com'
host.split(".")           # ['web01', 'example', 'com']
host.startswith("web")    # True
host.replace(".", "-")    # 'web01-example-com'
"  padded  ".strip()      # 'padded'
"22".zfill(5)             # '00022'
",".join(["a", "b"])      # 'a,b'
```

### Booleans and `None`

```python
is_root = False
result = None             # "no value yet", distinct from 0 / "" / False
```

`None` is the correct “absent” value. Use it when a function might not find
something. Do not use `"None"` (a string) or `-1` unless the interface
demands it.

## f-strings

An f-string starts with `f` and evaluates `{expressions}` inside it:

```python
host = "lab01"
cpus = 8
usage = 73.4567

print(f"host={host}")
print(f"cpus={cpus}")
print(f"usage={usage:.1f}%")        # one decimal place
print(f"bytes={230_000_000_000:,}") # thousands separators
print(f"hex={255:#x}")              # 0xff
print(f"mode={0o755:04o}")          # 0755
print(f"debug={cpus=}")             # debug=8  (Python 3.8+)
```

Format spec after the colon:

| Spec | Meaning |
|---|---|
| `.2f` | two decimal places |
| `>10` | right-align in width 10 |
| `<10` | left-align |
| `,` | thousands separator |
| `04o` | octal, zero-padded to 4 |
| `%` | multiply by 100 and add `%` |
| `!r` | `repr()` instead of `str()` |

The mission uses `.1f` and `.2f` because a human-readable report should not
dump 17 digits of float noise.

## Standard-library facts

```python
import os
import platform
import shutil

platform.node()                 # hostname
platform.release()              # kernel release
platform.system()               # 'Linux'
platform.machine()              # 'x86_64'
platform.python_version()       # '3.13.5'
os.cpu_count()                  # logical CPUs
os.getloadavg()                 # (1min, 5min, 15min) floats
shutil.disk_usage("/")          # usage(total=..., used=..., free=...)
```

`shutil.disk_usage` returns a named tuple, so both styles work:

```python
usage = shutil.disk_usage("/")
print(usage.total, usage.used, usage.free)
total, used, free = shutil.disk_usage("/")
```

On Linux, “free” here includes space reserved for root; `df` uses a slightly
different calculation. For a learning lab, either is fine as long as you say
which one you use.

## Conversions

```python
int("42")          # 42
int("0x1f", 16)    # 31
float("73.5")      # 73.5
str(42)            # '42'
bool("")           # False
bool("0")          # True  <- a non-empty string is truthy!
```

`int()` raises `ValueError` when the text is not a number. That is not a bug;
it is a signal you must handle (module 8). For now, let the traceback teach you
where bad data enters, then add validation.

## Guided walkthrough

In the lab:

```bash
cd "$(python3 main.py doctor | sed -n 's/^  \[ok\] Lab: //p' | head -1)" 2>/dev/null || true
mkdir -p 02_system_report
cd 02_system_report
```

Explore the facts interactively:

```bash
python3 - <<'PY'
import os, platform, shutil
print(platform.node())
print(platform.release())
print(os.cpu_count())
print(os.getloadavg())
print(shutil.disk_usage("/"))
PY
```

Then write `system_report.py` to print the six required key=value lines.
Test edge formatting:

```bash
python3 system_report.py
python3 system_report.py | sort
python3 system_report.py | grep -E '^(cpus|loadavg)='
```

Verify:

```bash
python3 main.py verify 2
```

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| `"cpus=" + os.cpu_count()` | `TypeError` | f-string or `str()` |
| `f"{usage:.1f}%"` where usage is 0.734 | `0.7%` | multiply by 100 or use `:.1%` |
| `int(usage)` truncates | loses information | decide if you want `round()` |
| Hard-coding the hostname | report lies after migration | read it from the system |
| Using `platform.uname().release` | works, but noisier | `platform.release()` |
| Forgetting that `os.cpu_count()` can be `None` | rare, but possible | handle or document |

## Mission checklist

- [ ] `02_system_report/system_report.py` exists.
- [ ] Six lines: `hostname`, `kernel`, `python`, `cpus`, `loadavg`,
      `root_free_gib`.
- [ ] Every value comes from Python.
- [ ] `cpus` is an integer.
- [ ] `loadavg` has three comma-separated numbers.
- [ ] `root_free_gib` is within 2 GiB of the real value.
- [ ] f-strings are used.

Then run:

```bash
python3 main.py verify 2
```

## Extra practice

1. Add `arch=` from `platform.machine()` and `distro=` from
   `platform.system()`.
2. Print `uptime=` using `time.monotonic()`? (It is not boot time; find the
   right source in `/proc/uptime` instead.)
3. Make the report valid JSON with `json.dumps`, then feed it to
   `python3 -m json.tool`.
4. Compare `shutil.disk_usage("/")` with `df -B1 /` and explain the
   difference.
