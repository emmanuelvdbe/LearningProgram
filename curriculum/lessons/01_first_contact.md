# Module 1 — First contact: a real executable script

## Why this matters for Linux+

The Linux+ exam expects you to automate tasks with shell and Python, and to
understand what makes a file *executable*. This module installs the habits you
will use in every later mission:

- run Python in two modes (REPL and script),
- put a shebang on a file,
- set the execute bit,
- call a script by path,
- use an entry-point guard.

Those five things are also the answer to a common interview question:
“Why does `./backup.py` say *Permission denied* when `python3 backup.py`
works?”

## The interpreter: two ways to run Python

Check the version first:

```bash
python3 --version
# Python 3.13.5
```

Never assume `python` exists. On many distributions it does not, and on some
it is still Python 2. Use `python3` in scripts and documentation.

### Mode 1 — the REPL

Start it with no arguments:

```bash
python3
```

You get a `>>>` prompt. This is a read-eval-print loop: each expression is
evaluated immediately.

```python
>>> 2 + 2
4
>>> import platform
>>> platform.node()
'lab01'
>>> exit()
```

Use the REPL to test one idea, inspect an object, or check a standard-library
function. Do not build a program in it.

Useful REPL tricks:

```python
>>> help(str.split)      # documentation for a method
>>> dir(platform)        # names inside a module
>>> type(42), type("42")
```

### Mode 2 — a script

Create `hello.py`:

```python
print("Hello, Linux+")
```

Run it explicitly:

```bash
python3 hello.py
```

The interpreter reads the file top to bottom. No compilation step, no build
directory, no extension requirement (though `.py` is conventional).

## The shebang

A shebang is the first line of an executable text file:

```python
#!/usr/bin/env python3
```

It tells the kernel which program should interpret the rest of the file.
`/usr/bin/env` searches the current `PATH` for `python3`, so the script works
even when Python is installed in `/usr/local/bin` or a virtual environment.
Hard-coding `#!/usr/bin/python3` is more brittle.

The shebang must be the **first** line. Not the second. Not after a blank
line or a comment. The kernel looks at the first two bytes (`#!`).

## The execute bit

A text file is data. Adding the execute bit turns it into a program:

```bash
chmod +x hello.py
ls -l hello.py
# -rwxr-xr-x 1 deb deb 42 Nov 12 10:00 hello.py
```

Now run it by path:

```bash
./hello.py
```

The leading `./` matters. The shell does not search the current directory for
commands by default (for good security reasons). `hello.py` means “find
`hello.py` in `PATH`”; `./hello.py` means “this file, right here”.

Check the exit status of the last command:

```bash
./hello.py
echo $?
# 0
```

`0` means success. Any non-zero value means failure. That convention is used
by `systemd`, `cron`, `make`, Ansible, and every monitoring system you will
meet.

## The entry-point guard

Python does not require a `main()` function, but real scripts benefit from one:

```python
#!/usr/bin/env python3
"""Say hello and show the interpreter version."""
import getpass
import platform


def main() -> None:
    print(f"Hello, {getpass.getuser()}!")
    print(f"Python {platform.python_version()} on {platform.node()}")


if __name__ == "__main__":
    main()
```

Why the `if`?

- When the file is executed, Python sets `__name__` to `"__main__"`, so
  `main()` runs.
- When the file is imported (`import myscript`), `__name__` is `"myscript"`,
  so `main()` does **not** run. You can test functions without side effects.

This single pattern makes a script reusable as a module later. The capstone
depends on it.

## `print()` details

```python
print("a", "b")             # a b
print("a", "b", sep="-")    # a-b
print("no newline", end="") # stays on the same line
print("error", file=__import__("sys").stderr)
```

Import `sys` normally; the one-liner above only shows that `print` can write
to any file object. In real code:

```python
import sys
print("ERROR: something failed", file=sys.stderr)
```

Normal results go to **stdout**; diagnostics go to **stderr**. Redirection
(`>`) only captures stdout, so keeping errors on stderr is what makes scripts
composable.

## Guided walkthrough

Run these in your lab workspace (the app prints the exact path):

```bash
cd "$(python3 main.py doctor | sed -n 's/^  \[ok\] Lab: //p' | head -1)" 2>/dev/null || true
mkdir -p 01_first_contact
cd 01_first_contact
```

Then create the script from the mission brief with your editor:

```bash
nano hello_sys.py
```

Check syntax without executing:

```bash
python3 -m py_compile hello_sys.py
```

Run it both ways:

```bash
python3 hello_sys.py
chmod +x hello_sys.py
./hello_sys.py
```

Inspect what the kernel sees:

```bash
head -1 hello_sys.py
ls -l hello_sys.py
file hello_sys.py
```

`file` should report “Python script, ASCII text executable”.

Verify:

```bash
python3 main.py verify 1
```

## Common mistakes

| Symptom | Cause | Fix |
|---|---|---|
| `bash: ./hello_sys.py: Permission denied` | no execute bit | `chmod +x hello_sys.py` |
| `bash: ./hello_sys.py: /usr/bin/python3^M: bad interpreter` | Windows CRLF line endings | `dos2unix hello_sys.py` or write Unix line endings |
| `python: command not found` | no `python` alias | use `python3` |
| Script runs when imported | work outside the guard | put it in `main()` |
| `SyntaxError: invalid syntax` at `print "hi"` | Python 2 syntax | `print("hi")` |
| Output disappears when redirecting | message written to stderr | choose the stream deliberately |

## Mission checklist

- [ ] `01_first_contact/hello_sys.py` exists.
- [ ] First line is exactly `#!/usr/bin/env python3`.
- [ ] The file has the execute bit.
- [ ] It prints `Hello, <user>!` with the real current user.
- [ ] It prints `Python <version> on <hostname>` with real values.
- [ ] Work happens in `main()` behind `if __name__ == "__main__":`.
- [ ] Running `./hello_sys.py` succeeds.

Then run:

```bash
python3 main.py verify 1
```

## Extra practice

1. Add a `--shout` option that uppercases the output.
2. Print the interpreter path with `sys.executable` and compare it with
   `which python3`.
3. Deliberately remove the execute bit and read the exact error message.
4. Move the shebang to line 2 and see what the kernel does.
