# Module 6 — Functions and argparse: a multi-command toolkit

## Why this matters for Linux+

The best Linux tools are small commands with predictable interfaces:
`systemctl status`, `ip addr`, `tar -czf`. They share a shape:

- subcommands for different jobs,
- flags for options,
- exit codes for automation,
- `--help` for humans.

This module turns your earlier one-off scripts into one `syskit` command with
`info`, `disk`, and `users` subcommands. That is the structure of Ansible
modules, cloud CLIs, and most professional sysadmin tools.

## Functions

```python
def greet(name: str) -> str:
    """Return a greeting. The docstring is help for humans."""
    return f"Hello, {name}"


message = greet("deb")
```

Parts:

- `def` starts the definition.
- `name` is the function name (snake_case).
- Parameters may have type hints (optional at runtime, useful to readers).
- `return` sends a value back. A function without `return` returns `None`.
- The docstring is the first statement; `help(greet)` displays it.

Type hints are not enforced. `greet(42)` runs and returns `Hello, 42`. Use them
for clarity, not for validation. Validate at the boundary where data enters.

## Parameters

```python
def check(path, threshold=90, *, verbose=False):
    ...
```

- `path` is required.
- `threshold` has a default; callers can omit it.
- `*` makes everything after it keyword-only:
  `check("/", verbose=True)` works; `check("/", 90, True)` does not.
- Call with keywords for readability: `check("/var", threshold=80)`.

Variable arguments:

```python
def total(*numbers):
    return sum(numbers)

def show(**options):
    for key, value in options.items():
        print(key, value)
```

Use them sparingly. An explicit signature is easier to document and test.

### Mutable default arguments

This is a classic trap:

```python
def add(item, bucket=[]):     # BAD: shared across calls
    bucket.append(item)
    return bucket
```

The default list is created once. Use `None`:

```python
def add(item, bucket=None):
    if bucket is None:
        bucket = []
    bucket.append(item)
    return bucket
```

## Scope

```python
counter = 0

def increment():
    global counter       # avoid this
    counter += 1
```

Prefer passing values in and returning results out:

```python
def increment(value):
    return value + 1
```

Local names disappear when the function returns. If a function needs to change
shared state, a class or an explicit return value is usually clearer.

## Return values

A function can return several values as a tuple:

```python
def usage(path):
    info = shutil.disk_usage(path)
    return info.total, info.used, info.free

total, used, free = usage("/")
```

Return early for errors instead of nesting:

```python
def read_user(path):
    if not path.exists():
        return None
    ...
```

Do not print inside pure helpers. Printing is a side effect; return data and
let `main()` decide how to present it. This makes testing trivial.

## Modules and imports

Every `.py` file is a module. You can import your own code:

```python
from netmask import prefix_to_mask
import netmask
```

The import runs the file once and binds names. This is why the
`if __name__ == "__main__":` guard matters: importing should not start the
program.

Avoid naming a file after a standard-library module (`json.py`, `socket.py`);
it will shadow the real one and produce confusing imports.

## `argparse` basics

```python
import argparse

parser = argparse.ArgumentParser(prog="syskit", description="Linux+ toolkit")
parser.add_argument("path", help="filesystem path")
parser.add_argument("--threshold", type=float, default=90)
args = parser.parse_args()
print(args.path, args.threshold)
```

`argparse` gives you:

- `-h/--help` automatically,
- a usage error (exit 2) for bad arguments,
- type conversion via `type=`,
- consistent error messages on stderr.

## Subcommands

```python
parser = argparse.ArgumentParser(prog="syskit")
sub = parser.add_subparsers(dest="command", required=True)

info = sub.add_parser("info", help="host information")
info.set_defaults(func=cmd_info)

disk = sub.add_parser("disk", help="filesystem usage")
disk.add_argument("--path", default="/")
disk.set_defaults(func=cmd_disk)

args = parser.parse_args()
raise SystemExit(args.func(args))
```

Why `set_defaults(func=...)`? It avoids a long `if/elif` dispatch and lets each
command own its arguments. It is the standard pattern for multi-command CLIs.

The mission requires `main() -> int` and `sys.exit(main())`, so `--help` exits
0 and usage errors exit 2 without tracebacks.

## Designing a command interface

For `syskit`:

```text
syskit info
syskit disk [--path PATH]
syskit users PASSWD_FILE
```

Rules:

- One job per subcommand.
- Byte counts are raw integers; formatting is the caller's problem.
- Human counts print one integer, nothing else, so shell tools can consume it.
- Errors go to stderr.
- Missing files are expected errors, not crashes.

A good CLI is boring. Boring is automatable.

## Exit codes, again

```python
def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)

if __name__ == "__main__":
    sys.exit(main())
```

- `argparse` handles syntax errors with exit 2.
- Your command functions return 0 or 2.
- `main()` propagates the status.
- The shell sees the truth.

## Guided walkthrough

```bash
cd "$(python3 main.py doctor | sed -n 's/^  \[ok\] Lab: //p' | head -1)" 2>/dev/null || true
mkdir -p 06_syskit
cd 06_syskit
```

Prototype the parser in a scratch file:

```bash
python3 - <<'PY'
import argparse
p = argparse.ArgumentParser(prog="demo")
sub = p.add_subparsers(dest="command", required=True)
a = sub.add_parser("hello")
a.add_argument("--name", default="world")
args = p.parse_args(["hello", "--name", "deb"])
print(args)
PY
```

Try the automatic help and error behaviour:

```bash
python3 syskit.py --help
python3 syskit.py disk --help
python3 syskit.py nope        # exit 2
```

Then implement the three commands. Test each independently:

```bash
python3 syskit.py info
python3 syskit.py disk
python3 syskit.py disk --path /tmp
python3 syskit.py users passwd
```

Verify:

```bash
python3 main.py verify 6
```

The verifier supplies its own passwd fixture, so do not hard-code the path.

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| `def cmd(path, opts=[])` | shared mutable default | use `None` |
| Printing inside a helper | untestable, noisy | return data; print in `main` |
| `sys.exit()` inside a function | kills the process mid-flow | return an int |
| No `required=True` on subparsers | running with no command does nothing | make it required |
| Catching all exceptions | hides typos | catch `OSError`/`ValueError` only |
| Hard-coding `/etc/passwd` | fixture tests fail | take a path argument |
| Using `os.system` | no output capture, shell injection risk | `subprocess` (module 10) |
| Forgetting `if __name__ == "__main__"` | import runs the CLI | add the guard |

## Mission checklist

- [ ] `06_syskit/syskit.py` exists.
- [ ] `info` prints host, kernel, Python.
- [ ] `disk [--path]` prints total/used/free/percent; missing path exits 2.
- [ ] `users <file>` prints only the human count; missing file exits 2.
- [ ] argparse subcommands are real (`dest="command", required=True`).
- [ ] `--help` lists all three commands.
- [ ] No tracebacks for expected errors.

Then run:

```bash
python3 main.py verify 6
```

## Extra practice

1. Add `syskit ports` that prints listening sockets by calling `ss` later
   (after module 10).
2. Add `--json` to every command using a small formatting helper.
3. Add `syskit logs --since` and reuse module 5's parser.
4. Write a shell completion script for bash.
5. Split `syskit.py` into a package (`syskit/__main__.py`, `syskit/disk.py`)
   and keep the same CLI.
