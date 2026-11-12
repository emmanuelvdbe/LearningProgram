# Module 11 — os.stat and bitmasks: permission audit

## Why this matters for Linux+

Permissions are a core Linux+ security topic. You are expected to explain
`rwxr-xr-x`, set SUID/SGID/sticky bits, and find dangerous files. The shell
answer is `find / -perm -4000`; the Python answer can run on a schedule, emit
JSON, and combine several checks in one pass.

This module builds a read-only permission audit. It also makes the Unix mode
model concrete instead of a memorized string.

## The Unix mode in one page

`ls -l` shows ten characters:

```text
-rwsr-xr-x  1 root root 12345 /usr/bin/passwd
```

Break it down:

```text
-  rws  r-x  r-x
|   |    |    |
|   |    |    +-- other
|   |    +------- group
|   +------------ owner
+---------------- file type
```

Each permission triad is **read (4)**, **write (2)**, **execute (1)**. Add them:

| Symbolic | Octal |
|---|---|
| `rwx` | 7 |
| `rw-` | 6 |
| `r-x` | 5 |
| `r--` | 4 |
| `-wx` | 3 |
| `-w-` | 2 |
| `--x` | 1 |
| `---` | 0 |

A mode is three octal digits: owner, group, other.

```text
755 = rwxr-xr-x
644 = rw-r--r--
600 = rw-------
777 = rwxrwxrwx
```

## Special bits

There are three extra bits above the triad:

| Bit | Octal | Symbolic | Meaning |
|---|---|---|---|
| SUID | 4000 | `s` in owner execute | run as file owner |
| SGID | 2000 | `s` in group execute | run as group / inherit dir group |
| sticky | 1000 | `t` in other execute | only owner can delete in a dir |

Examples:

```text
4755  -rwsr-xr-x   SUID
2755  -rwxr-sr-x   SGID
1777  drwxrwxrwt   sticky (/tmp)
```

A SUID root binary is powerful. If it has a bug, an unprivileged user can
become root. Finding unexpected SUID files is a standard hardening task.

World-writable files are also dangerous:

```text
0666  -rw-rw-rw-
0777  -rwxrwxrwx
```

The audit looks for the “other write” bit (`0o002`).

## Reading modes in Python

```python
import os
import stat

info = os.stat("/usr/bin/passwd")
print(info.st_mode)                  # includes file type bits, e.g. 35255
print(stat.S_IMODE(info.st_mode))    # 0o4755
print(f"{stat.S_IMODE(info.st_mode):04o}")   # '4755'
```

Why `S_IMODE`? `st_mode` packs the file type (regular, directory, symlink,
device) and the permission bits into one integer. `S_IMODE` masks the
permission/special bits; the rest is the type.

Type checks:

```python
stat.S_ISREG(info.st_mode)    # regular file?
stat.S_ISDIR(info.st_mode)    # directory?
stat.S_ISLNK(info.st_mode)    # symlink? (use lstat)
```

## Bitwise tests

```python
mode = stat.S_IMODE(info.st_mode)

if mode & stat.S_IWOTH:
    print("world-writable")
if mode & stat.S_ISUID:
    print("SUID")
if mode & stat.S_ISGID:
    print("SGID")
```

`&` is bitwise AND. `mode & 0o002` is non-zero exactly when the other-write bit
is set. Do not compare the whole mode to `0o002`; that would only match a file
with literally no other permission bits.

Flags can be combined:

```python
if mode & (stat.S_ISUID | stat.S_ISGID):
    print("setuid or setgid")
```

## Walking a tree safely

```python
for dirpath, dirnames, filenames in os.walk(root):
    for name in filenames:
        path = os.path.join(dirpath, name)
        info = os.lstat(path)
```

- `os.walk` is top-down by default.
- `filenames` includes symlinks to files; `lstat` does not follow them.
- Directories with no read permission may be skipped or raise, depending on
  version and flags.
- If you do not want to descend into a directory, remove it from `dirnames`
  in place.

`pathlib` equivalent:

```python
from pathlib import Path

for path in Path(root).rglob("*"):
    info = path.lstat()
    if stat.S_ISREG(info.st_mode):
        ...
```

Both are fine. `os.walk` gives more control over pruning.

## Symlinks

`os.stat` follows symlinks; `os.lstat` does not. For a security audit, use
`lstat` and report symlinks separately. A symlink’s mode is almost always
`0777`, which would produce false “world-writable” findings if you followed it.

```python
if stat.S_ISLNK(info.st_mode):
    continue          # or record the link separately
```

## Readability and `os.access`

```python
os.access(path, os.R_OK)    # can the effective user read it?
```

`os.access` checks the real UID/GID by default (not effective), which matters
for SUID programs. It is a snapshot; permissions can change immediately after.
For an audit, that is fine.

As root, `os.access` returns `True` for almost everything. Tests must account
for the user running them.

## Why path relative?

Reports should not depend on where the tree is mounted:

```python
rel = os.path.relpath(path, root).replace(os.sep, "/")
```

Use POSIX separators in JSON so a report produced on Linux is stable across
tools. Do not include the lab’s absolute path.

## Performance and race conditions

A full `find /` audit can be slow. Practical tips:

- prune pseudo-filesystems (`/proc`, `/sys`, `/dev`),
- skip network mounts unless requested,
- use `os.scandir` when you need speed (it caches metadata),
- handle `FileNotFoundError` for files deleted during the walk,
- never modify the tree during an audit.

```python
try:
    info = path.lstat()
except FileNotFoundError:
    continue
```

## Guided walkthrough

```bash
cd "$(python3 main.py doctor | sed -n 's/^  \[ok\] Lab: //p' | head -1)" 2>/dev/null || true
mkdir -p 11_permission_audit
cd 11_permission_audit
mkdir -p demo/sub
touch demo/normal demo/world demo/suid demo/sgid demo/locked
chmod 644 demo/normal
chmod 666 demo/world
chmod 4755 demo/suid
chmod 2755 demo/sgid
chmod 000 demo/locked
ls -l demo
```

Explore the bits:

```bash
python3 - <<'PY'
import os, stat
for name in ("normal", "world", "suid", "sgid", "locked"):
    info = os.stat(f"demo/{name}")
    mode = stat.S_IMODE(info.st_mode)
    print(
        f"{name:8} {mode:04o} "
        f"ww={bool(mode & stat.S_IWOTH)} "
        f"suid={bool(mode & stat.S_ISUID)} "
        f"sgid={bool(mode & stat.S_ISGID)} "
        f"readable={os.access(f'demo/{name}', os.R_OK)}"
    )
PY
```

Then implement `audit_perms.py` and test it:

```bash
python3 audit_perms.py demo | python3 -m json.tool
```

Verify:

```bash
python3 main.py verify 11
```

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| Comparing `st_mode == 0o666` | misses file-type bits | use `stat.S_IMODE` |
| Testing `mode & 0o002 == 0` | precedence bug | parenthesize: `(mode & 0o002) == 0` |
| Following symlinks with `stat` | false positives | use `lstat` |
| Forgetting special bits in output | SUID reported as 0755 | format `S_IMODE` as 4 octal digits |
| Auditing as root and expecting unreadable findings | root reads everything | skip or document |
| Not catching disappearing files | crash mid-walk | catch `FileNotFoundError` |
| Absolute paths in report | unstable | use `relative_to` / `relpath` |
| Modifying the tree | audit changes what it measures | read-only operations |

## Mission checklist

- [ ] `11_permission_audit/audit_perms.py` exists.
- [ ] Recurses through regular files, skips symlinks.
- [ ] `world_writable` uses `0o002`.
- [ ] `suid` uses `0o4000`; `sgid` uses `0o2000`.
- [ ] `unreadable` uses `os.access(path, os.R_OK)`.
- [ ] Modes are four-digit octal (`0666`, `4755`, `0000`).
- [ ] Paths are relative with `/`, lists sorted.
- [ ] Missing directory exits 2.

Then run:

```bash
python3 main.py verify 11
```

## Extra practice

1. Add `sticky` directories and `world_writable_dirs` to the report.
2. Report files owned by UID 0 outside `/usr` and `/bin`.
3. Add a `--max-depth` option.
4. Compare with `find demo -perm -0002 -printf '%m %p\n'`.
5. Write a remediation mode that prints the exact `chmod` command, but does
   not execute it.
6. Add a `--json`/`--text` output switch.
