# Module 10 — subprocess: run commands and capture the truth

## Why this matters for Linux+

Python is good at logic and data. Linux tools are good at inspecting the
system. Real automation combines them: call `ss`, `df`, `systemctl`, `tar`, or
`ip`, capture the output, inspect the return code, and decide what to do.

This module builds a health-check runner that reads a JSON list of commands and
produces a report. It is the same core loop used by configuration-management
modules and monitoring agents.

## The old way (do not start here)

```python
import os
os.system("df -h")
```

Problems:

- no clean access to stdout/stderr,
- the shell interprets metacharacters (injection risk),
- return codes are awkward,
- quoting is platform-dependent.

Use `subprocess` with an argument list.

## The basic call

```python
import subprocess

result = subprocess.run(
    ["df", "-h", "/"],
    capture_output=True,
    text=True,
)
print("status:", result.returncode)
print("stdout:", result.stdout)
print("stderr:", result.stderr)
```

`subprocess.run` returns a `CompletedProcess`:

| Attribute | Meaning |
|---|---|
| `args` | the command that ran |
| `returncode` | exit status (0 = success) |
| `stdout` | captured standard output (if `capture_output=True`) |
| `stderr` | captured standard error |

`text=True` decodes bytes using the locale encoding. It is convenient. For
binary output (tar streams, images), leave it off and handle bytes.

## `shell=False` is the default and the right choice

```python
subprocess.run(["echo", "hello world"])          # one argument, safe
subprocess.run("echo hello world", shell=True)   # shell parses it, risky
```

With a list:

- no word splitting by the shell,
- no glob expansion (do it in Python with `pathlib`),
- no variable expansion (do it in Python with f-strings),
- user input cannot inject `; rm -rf /`.

If you genuinely need shell features (pipes, redirection, wildcards), build the
string carefully and never interpolate untrusted data. Better: use `sh -c`
only for fixed, trusted commands.

```python
subprocess.run(["sh", "-c", "ps aux | grep '[s]shd'"])   # fixed command
```

## Capturing, checking, timing

```python
try:
    result = subprocess.run(
        ["systemctl", "is-active", "ssh"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
except subprocess.TimeoutExpired:
    ...
except FileNotFoundError:
    ...
```

- `timeout=` raises `TimeoutExpired` after N seconds. `run` kills the child
  (SIGKILL on POSIX) before raising.
- `check=True` raises `CalledProcessError` for a non-zero status. Useful when
  failure is exceptional; the health-check mission prefers `check=False` and
  records the status.
- `FileNotFoundError` means the executable itself is missing.
- `PermissionError` means it exists but cannot be executed.

Catch these per command, not around the whole loop. One broken probe should not
abort the other checks.

## Return codes and expected values

A check specification might include an expected status:

```json
{"name": "ssh", "cmd": ["systemctl", "is-active", "ssh"], "expect": 0}
```

`systemctl is-active` returns 0 for active, 3 for inactive. The report should
keep the real code and decide `ok` by comparison:

```python
ok = (not timed_out) and returncode == expect
```

Do not rewrite the status to 0/1; preserve the truth. Whoever reads the report
may need to distinguish “inactive” from “not found”.

## Measuring duration

```python
import time

started = time.perf_counter()
result = subprocess.run(...)
duration_ms = int((time.perf_counter() - started) * 1000)
```

`perf_counter()` is monotonic and high-resolution. Do not use
`datetime.now()` for durations; the wall clock can jump (NTP, DST).

## Building a report

```python
results = [run_one(spec) for spec in specs]
passed = sum(1 for item in results if item["ok"])
report = {
    "ok": passed == len(results),
    "passed": passed,
    "failed": len(results) - passed,
    "checks": results,
}
```

Write it with `json.dump(..., indent=2)`. Exit 0 only if every check passed;
exit 1 otherwise. A missing or invalid spec file exits 2 (usage/config error).

## Reading JSON input

```python
import json

with open(path, encoding="utf-8") as fh:
    specs = json.load(fh)
```

Validate the shape:

```python
if not isinstance(specs, list):
    print("ERROR: expected a JSON list", file=sys.stderr)
    return 2
```

Python's dynamic typing means a valid JSON object where you expected a list
will fail later with a confusing error. Check at the boundary.

## Why not `os.popen` or `commands`?

`os.popen` is legacy, returns a file object, and makes status handling awkward.
`commands` was removed in Python 3. Use `subprocess.run`.

## Guided walkthrough

```bash
cd "$(python3 main.py doctor | sed -n 's/^  \[ok\] Lab: //p' | head -1)" 2>/dev/null || true
mkdir -p 10_healthcheck
cd 10_healthcheck
```

Explore `subprocess` in the REPL:

```bash
python3 - <<'PY'
import subprocess
for cmd in (["true"], ["false"], ["sh", "-c", "echo hi"], ["nope-xyz"]):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        print(cmd, "->", p.returncode, repr(p.stdout), repr(p.stderr))
    except FileNotFoundError as exc:
        print(cmd, "-> missing:", exc)
PY
```

Create a small checks file and run your implementation:

```bash
cat > checks.json <<'JSON'
[
  {"name": "ok", "cmd": ["python3", "-c", "raise SystemExit(0)"], "expect": 0},
  {"name": "bad", "cmd": ["python3", "-c", "raise SystemExit(3)"], "expect": 0},
  {"name": "echo", "cmd": ["sh", "-c", "echo linux"]},
  {"name": "missing", "cmd": ["definitely-not-a-real-command"]},
  {"name": "slow", "cmd": ["python3", "-c", "import time; time.sleep(3)"], "timeout": 0.5}
]
JSON
python3 healthcheck.py checks.json --out report.json; echo "status=$?"
python3 -m json.tool report.json
```

Verify:

```bash
python3 main.py verify 10
```

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| `shell=True` with user input | command injection | pass an argv list |
| Forgetting `capture_output=True` | `stdout` is `None` | capture explicitly |
| Forgetting `text=True` | bytes printed as `b'...'` | decode or `text=True` |
| No timeout | check can hang forever | set a small timeout |
| Catching only `CalledProcessError` | missing command crashes | catch `FileNotFoundError` too |
| Looking at stdout only | failures often explain on stderr | record both |
| `datetime.now()` for durations | clock jumps | `perf_counter()` |
| Aborting the loop on first failure | no full picture | record and continue |

## Mission checklist

- [ ] `10_healthcheck/healthcheck.py` exists.
- [ ] Reads a JSON list of `{name, cmd, expect?, timeout?}`.
- [ ] Runs with `shell=False`, captures stdout/stderr, honours timeout.
- [ ] Missing command is a failure with `returncode: null`.
- [ ] Timeout sets `timed_out: true`.
- [ ] Report has `ok`, `passed`, `failed`, `checks`, `duration_ms`.
- [ ] Exits 0 only when every check passes; 1 otherwise; 2 for bad input.

Then run:

```bash
python3 main.py verify 10
```

## Extra practice

1. Add `retries` and `delay` per check.
2. Add an `env` field to the spec for per-check environment variables.
3. Run commands in parallel with `concurrent.futures.ThreadPoolExecutor` and
   compare the total time.
4. Stream output live instead of capturing it (`Popen` + `readline`).
5. Send a non-zero exit when `stderr` is non-empty even if the status is 0.
