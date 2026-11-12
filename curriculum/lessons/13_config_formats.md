# Module 13 — Config formats: systemd unit inspector

## Why this matters for Linux+

Services are configured with files, and Linux+ expects you to read them:
systemd units, `/etc/fstab`, network configs, SSH drop-ins. Python's standard
library can parse most of them without third-party packages.

This module builds a systemd `.service` inspector. It validates required
directives, extracts the fields an operator cares about, and reports JSON.
The same pattern works for any INI-style configuration.

## systemd units are INI files (mostly)

A minimal service:

```ini
[Unit]
Description=Nightly backup

[Service]
Type=simple
User=backup
ExecStart=/usr/local/bin/backup.py /srv /var/backups
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Sections in square brackets, `key=value` lines, `#` or `;` comments. That is
close enough to INI that `configparser` can read it.

Important differences from formal INI:

- keys are case-sensitive in systemd (`ExecStart` matters),
- values can contain `%` specifiers (`%i`, `%n`) and spaces,
- repeated keys have special merge semantics,
- line continuations use a trailing backslash,
- `[Install]` is only used by `systemctl enable`, not at runtime.

`configparser` is a pragmatic parser, not a systemd validator. Use
`systemd-analyze verify` for real validation. The mission is about the Python
parsing and reporting pattern.

## `configparser` basics

```python
import configparser

parser = configparser.ConfigParser()
parser.read("backup.service")

print(parser.sections())                       # ['Unit', 'Service', 'Install']
print(parser.get("Service", "ExecStart"))
print(parser.get("Service", "User", fallback="root"))
```

Three arguments that matter for unit files:

```python
parser = configparser.ConfigParser(
    interpolation=None,      # do not treat % as interpolation
    allow_no_value=True,     # permit bare keys
    strict=False,            # tolerate duplicate options
)
```

### Why `interpolation=None`?

By default, `configparser` treats `%` as a special interpolation character.
A systemd value such as `ExecStart=/bin/echo 100%` raises
`InterpolationSyntaxError`. Disable interpolation.

### Why `allow_no_value=True`?

Some config files contain bare flags. It also avoids surprising errors on
malformed units, which you may want to report rather than crash on.

### Why `strict=False`?

Real unit files and drop-ins can repeat keys. `strict=True` (the default)
raises `DuplicateOptionError`. For an inspector, tolerating duplicates and
reporting the last value is friendlier.

## Reading a file that may not exist

`parser.read(path)` silently ignores a missing file and returns an empty list.
That is convenient for config loading, dangerous for an inspector:

```python
parser.read("missing.service")
print(parser.sections())     # []
```

The mission distinguishes “file not found” (exit 2) from “file is invalid”
(exit 1). Open the file yourself so errors propagate:

```python
with path.open(encoding="utf-8") as fh:
    parser.read_file(fh)
```

`read_file` raises `FileNotFoundError`, `PermissionError`, and
`configparser.Error` as expected.

## Case sensitivity

`configparser` lowercases option names internally. These are equivalent:

```python
parser.get("Service", "ExecStart")
parser.get("Service", "execstart")
```

Section names are case-sensitive. systemd keys are case-sensitive too, but for
lookup this is usually harmless. Do not rewrite the file based on
`configparser` output unless you preserve the original casing separately.

## Validation

A service is useful only if it can start. Required fields for this mission:

```python
errors = []
if not parser.has_section("Unit") or not parser.get("Unit", "Description", fallback="").strip():
    errors.append("Missing [Unit] Description")
if not parser.has_section("Service") or not parser.get("Service", "ExecStart", fallback="").strip():
    errors.append("Missing [Service] ExecStart")
```

`Restart=` has a fixed vocabulary:

```python
ALLOWED_RESTART = {"no", "on-success", "on-failure", "always"}
restart = parser.get("Service", "Restart", fallback="").strip()
if restart and restart not in ALLOWED_RESTART:
    errors.append(f"Invalid Restart value: {restart}")
```

Report **all** errors, not just the first. An operator can fix several things in
one edit. The exit code is 1 if `errors` is non-empty.

## Optional values: `None` vs `""`

Use `None` for “not specified” and an empty string only if the file literally
contains an empty value. This makes JSON unambiguous:

```json
{
  "user": null,
  "restart": "on-failure"
}
```

Be consistent. A consumer should not have to guess whether `""` means missing
or empty.

## `[Install]` and `WantedBy`

```python
wanted_by = parser.get("Install", "WantedBy", fallback="").split()
```

`WantedBy=multi-user.target graphical.target` becomes
`["multi-user.target", "graphical.target"]`. `split()` on whitespace handles
multiple spaces, tabs, and newlines.

`[Install]` is metadata for `systemctl enable`; it does not affect a running
service. Still, reporting it helps an operator understand boot behaviour.

## Output as JSON

```python
report = {
    "valid": not errors,
    "errors": errors,
    "name": path.name.removesuffix(".service"),
    "description": ...,
    "exec_start": ...,
    "user": ...,
    "restart": ...,
    "wanted_by": wanted_by,
}
```

Print with `json.dump(..., indent=2)`. Exit 0 for valid, 1 for invalid. A
machine can now gate a deployment:

```bash
python3 unit_inspect.py app.service || exit 1
```

## Guided walkthrough

```bash
cd "$(python3 main.py doctor | sed -n 's/^  \[ok\] Lab: //p' | head -1)" 2>/dev/null || true
mkdir -p 13_unit_inspector
cd 13_unit_inspector
```

Look at a real unit on your system:

```bash
systemctl cat ssh.service 2>/dev/null || systemctl cat sshd.service 2>/dev/null
systemd-analyze verify ssh.service 2>/dev/null || true
```

Experiment with `configparser`:

```bash
python3 - <<'PY'
import configparser
cp = configparser.ConfigParser(interpolation=None, allow_no_value=True, strict=False)
cp.read_file(open("sample.service")) if __import__("os").path.exists("sample.service") else None
text = """
[Unit]
Description=Demo
[Service]
ExecStart=/bin/echo 100%
Restart=always
[Install]
WantedBy=multi-user.target
"""
import io
cp = configparser.ConfigParser(interpolation=None, allow_no_value=True, strict=False)
cp.read_file(io.StringIO(text))
print(cp.sections())
print(cp.get("Service", "ExecStart"))
print(cp.get("Install", "WantedBy").split())
PY
```

Then write `unit_inspect.py`, test a valid and an invalid unit, and inspect the
JSON:

```bash
python3 unit_inspect.py valid.service | python3 -m json.tool; echo "status=$?"
python3 unit_inspect.py broken.service | python3 -m json.tool; echo "status=$?"
python3 unit_inspect.py nope.service; echo "status=$?"
```

Verify:

```bash
python3 main.py verify 13
```

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| Default interpolation | `%` in ExecStart raises | `interpolation=None` |
| `parser.read(missing)` | silently empty, wrong exit code | open/read_file |
| `strict=True` and duplicate keys | crash | `strict=False` for inspection |
| `get()` without fallback | `NoOptionError` | `fallback=""` |
| Crashing on malformed INI | no report | catch `configparser.Error` |
| Returning “valid” with missing ExecStart | service cannot start | validate required keys |
| Not stripping values | `" backup"` comparison fails | `.strip()` |
| Printing a traceback for a missing file | noisy | exit 2 with stderr |

## Mission checklist

- [ ] `13_unit_inspector/unit_inspect.py` exists.
- [ ] Uses `configparser` with `interpolation=None`.
- [ ] Valid unit exits 0; JSON fields are correct.
- [ ] Missing Description/ExecStart makes it invalid; exit 1.
- [ ] Bad `Restart=` is reported; exit 1.
- [ ] `WantedBy` is a list; optional values are `null`.
- [ ] Missing file exits 2 cleanly.

Then run:

```bash
python3 main.py verify 13
```

## Extra practice

1. Support `Type=` validation (`simple`, `forking`, `oneshot`, `notify`).
2. Parse `Environment=` and `EnvironmentFile=` into a dict.
3. Read a directory of drop-ins (`app.service.d/*.conf`) and merge them.
4. Add a mode that extracts `ExecStart` and checks the binary exists.
5. Compare with `systemd-analyze verify`.
6. Support TOML with `tomllib` (Python 3.11+) for modern config files.
