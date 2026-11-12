# Module 4 — Lists, dictionaries, and /etc/passwd

## Why this matters for Linux+

`/etc/passwd` is a colon-separated database, not a text file you read for fun.
Every account on the system is one line with seven fields. Linux+ asks you to
reason about UIDs, shells, service accounts, and duplicate identities. Python's
core collections turn that file into a queryable inventory in a dozen lines.

This module builds a report that would be useful during an audit:

- how many records exist,
- which accounts are human (UID 1000–65533),
- which shells are in use,
- whether any UID is duplicated.

## Lists

A list is an ordered, mutable sequence:

```python
users = ["root", "daemon", "deb"]
users.append("alice")        # ['root', 'daemon', 'deb', 'alice']
users[0]                     # 'root'
users[-1]                    # 'alice'
users[1:3]                   # ['daemon', 'deb']
len(users)                   # 4
users.sort()                 # in place, returns None
sorted(users)                # new sorted list
"deb" in users               # True
```

Important methods:

```python
users.remove("daemon")       # by value; ValueError if absent
last = users.pop()           # remove and return last
users.insert(1, "bin")       # insert at index
users.extend(["sys", "sync"])
```

List comprehensions (module 5 covers them in depth):

```python
human = [name for name in users if name != "root"]
```

## Tuples

A tuple is an ordered, immutable sequence. Use it for fixed-shape records:

```python
record = ("deb", 1000, "/bin/bash")
name, uid, shell = record          # unpacking
name, uid, shell = record
```

Unpacking is the cleanest way to read `/etc/passwd`:

```python
fields = "deb:x:1000:1000:Deb:/home/deb:/bin/bash".split(":")
name, password, uid, gid, gecos, home, shell = fields
```

If the line has the wrong number of fields, unpacking raises `ValueError`.
That is useful: skip malformed records instead of indexing blindly.

A single-element tuple needs a trailing comma: `("root",)`.

## Dictionaries

A dict maps keys to values:

```python
shells = {"/bin/bash": 4, "/usr/sbin/nologin": 4}
shells["/bin/zsh"] = 1
shells.get("/bin/fish", 0)          # 0, no KeyError
"/bin/bash" in shells               # True
del shells["/bin/zsh"]
```

Iterating:

```python
for shell, count in shells.items():
    print(shell, count)
```

Dicts preserve insertion order (Python 3.7+). For deterministic reports, sort:

```python
dict(sorted(shells.items()))
```

Do not rely on the order of a dict built from a set or from a file if the
output is compared byte-for-byte. Sort explicitly.

Common methods:

```python
shells.keys()
shells.values()
shells.items()
shells.setdefault("/bin/sh", 0)
shells.update({"/bin/sh": 2})
```

### Counting without `Counter`

```python
counts = {}
for user in users:
    counts[user.shell] = counts.get(user.shell, 0) + 1
```

### Counting with `Counter`

```python
from collections import Counter

shells = Counter(user.shell for user in users)
shells["/bin/bash"]              # count, 0 if absent
shells.most_common(3)            # [(shell, count), ...]
```

`Counter` is a dict subclass, so `dict(sorted(shells.items()))` still works.

## Sets

A set stores unique values, unordered:

```python
uids = {1000, 1001, 1000}
len(uids)                 # 2
uids.add(1002)
uids & {1000, 9999}       # intersection
uids | {9999}             # union
uids - {1000}             # difference
```

Use sets when you care about membership, not order. Do not use a set for a
report field unless you sort it first.

## Parsing /etc/passwd

The seven fields are:

```
name:password:uid:gid:gecos:home:shell
```

Example:

```
deb:x:1000:1000:Deb:/home/deb:/bin/bash
```

Rules for a robust parser:

1. Read line by line.
2. Skip blank lines and comments (`#`).
3. Split on `":"`.
4. Require exactly seven fields.
5. Convert UID to `int` inside a `try`.
6. Keep the fields you need in a dict.

```python
def parse_passwd(lines):
    users = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split(":")
        if len(fields) != 7:
            continue
        name, password, uid, gid, gecos, home, shell = fields
        try:
            uid = int(uid)
        except ValueError:
            continue
        users.append({"name": name, "uid": uid, "shell": shell})
    return users
```

Why a dict per user instead of a tuple? Named fields survive change. A tuple
is fine for a fixed local loop; a dict is better when the record crosses a
function boundary or becomes JSON.

## Human vs. system accounts

Distributions vary, but the usual convention:

| UID range | Meaning |
|---|---|
| 0 | root |
| 1–999 | system/service accounts (varies) |
| 1000+ | regular human accounts |
| 65534 | `nobody` (unmapped/anonymous) |

The mission defines human as `1000 <= uid < 65534`. That excludes `nobody`
and includes normal users. Real systems may have `nobody` at 65534 or other
values, so always state your definition.

## Sorting and determinism

```python
names = sorted(user["name"] for user in users)
by_uid = sorted(users, key=lambda user: (user["uid"], user["name"]))
```

Key functions return a tuple when you need tie-breakers. `sorted()` is stable,
so ties keep their original order — but explicit keys make the intent clear.

## JSON output

`json.dump` converts Python objects to text:

```python
import json

report = {
    "total": len(users),
    "human_users": sorted(...),
    "shells": dict(sorted(shells.items())),
    "duplicate_uids": duplicates,
}
json.dump(report, sys.stdout, indent=2)
print()
```

Why JSON? Because the next tool (a dashboard, Ansible, `jq`) can consume it
without parsing prose. A human can still read it. The mission's verifier reads
it, too.

## Finding duplicates

```python
from collections import Counter

uids = Counter(user["uid"] for user in users)
duplicates = sorted(uid for uid, count in uids.items() if count > 1)
```

Duplicate UIDs are a security problem: two names resolve to the same identity
and file ownership becomes ambiguous. Linux+ expects you to notice.

## Guided walkthrough

```bash
cd "$(python3 main.py doctor | sed -n 's/^  \[ok\] Lab: //p' | head -1)" 2>/dev/null || true
mkdir -p 04_passwd_report
cd 04_passwd_report
```

Inspect the provided sample and the real file:

```bash
cat passwd.sample
head -5 /etc/passwd
awk -F: '{print $1, $3, $7}' /etc/passwd | head
```

Try the parser logic in the REPL:

```bash
python3 - <<'PY'
line = "deb:x:1000:1000:Deb:/home/deb:/bin/bash"
fields = line.split(":")
print(len(fields), fields)
name, pw, uid, gid, gecos, home, shell = fields
print(name, int(uid), shell)
PY
```

Then write `passwd_report.py`, run it, and pretty-print the result:

```bash
python3 passwd_report.py passwd.sample
python3 passwd_report.py passwd.sample | python3 -m json.tool
python3 passwd_report.py /etc/passwd | head
```

Verify:

```bash
python3 main.py verify 4
```

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| Comparing `uid` as a string | `"1000" < "999"` is true | convert with `int()` first |
| `dict[missing]` | `KeyError` | use `.get(key, default)` or `Counter` |
| Printing a dict directly | insertion order, not sorted | `dict(sorted(...))` |
| Counting `nobody` as human | wrong count | state the UID range |
| Indexing `fields[2]` without checking length | `IndexError` on malformed rows | check `len(fields) == 7` |
| Sorting users by `(uid, name)` but reporting only names | okay, but document it | keep the key visible |
| Mutating a list while iterating it | skipped elements | build a new list |

## Mission checklist

- [ ] `04_passwd_report/passwd_report.py` exists.
- [ ] Reads the file path from `sys.argv[1]`.
- [ ] Skips blank/comment lines and malformed records.
- [ ] `total` is the number of valid records.
- [ ] `human_users` is sorted and uses UID 1000–65533.
- [ ] `shells` counts per shell and is sorted by shell name.
- [ ] `duplicate_uids` is sorted.
- [ ] Output is indented JSON.

Then run:

```bash
python3 main.py verify 4
```

## Extra practice

1. Add `"uid0"` (accounts with UID 0) and `"empty_passwords"` (password field
   equal to `""`) to the report.
2. Add `"duplicate_names"`; can two records share a name?
3. Join with `/etc/group` and report each human user's primary group name.
4. Rewrite the report as CSV with `csv.DictWriter`.
5. Compare your `human_users` list with
   `getent passwd | awk -F: '$3>=1000 && $3<65534 {print $1}'`.
