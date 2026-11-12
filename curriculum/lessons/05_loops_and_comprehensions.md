# Module 5 — Loops, comprehensions, and Counter

## Why this matters for Linux+

Logs are the richest and messiest data on a Linux system. Linux+ asks you to
find failed logins, identify noisy hosts, and explain what a service recorded.
The exam does not require Python, but Python makes you faster: a forty-line
script can answer “which IP is attacking us?” in one second.

This module builds a log triage tool. It introduces iteration patterns you
will use in nearly every automation you write.

## `for` loops

Python iterates over *iterables*, not C-style index counters:

```python
for user in ["root", "deb", "alice"]:
    print(user)
```

To count, use `enumerate`:

```python
for index, user in enumerate(["root", "deb"], start=1):
    print(index, user)
```

To walk two sequences in parallel, use `zip`:

```python
hosts = ["web01", "web02"]
ports = [22, 443]
for host, port in zip(hosts, ports):
    print(f"{host}:{port}")
```

`zip` stops at the shortest input. If lengths may differ and that matters,
validate first or use `itertools.zip_longest`.

Ranges:

```python
for i in range(3):        # 0 1 2
    ...
for i in range(2, 10, 2): # 2 4 6 8
    ...
```

## `while`, `break`, `continue`

```python
attempts = 0
while attempts < 3:
    attempts += 1
    if attempts == 2:
        continue          # skip the rest of this iteration
    if attempts == 3:
        break             # leave the loop entirely
```

Use `while` when the number of iterations is unknown (waiting for a service,
reading until EOF). Use `for` when you have a collection.

`for ... else` runs the `else` block only if the loop was not broken:

```python
for user in users:
    if user.name == "root":
        break
else:
    print("no root account")   # only if the loop completed
```

This is Python-specific and occasionally useful; do not overuse it.

## Reading files line by line

```python
with open("/var/log/auth.log", encoding="utf-8", errors="replace") as fh:
    for line in fh:
        if "Failed password" in line:
            ...
```

- `with` closes the file even if an exception occurs.
- Iterating a file yields one line at a time, including the trailing `\n`.
- `errors="replace"` keeps one bad byte from crashing a triage script.
- `readlines()` loads everything into memory; fine for small lab logs, bad for
  multi-gigabyte logs.

## String searching

```python
if "Failed password" in line:
    ...
if line.startswith("Jan 12"):
    ...
position = line.find("from ")
lower = line.lower()
```

For structured extraction, use `split` or regex (module 9). For a first pass,
substring checks are clear and fast.

## Comprehensions

A list comprehension builds a list from a loop:

```python
lengths = [len(line) for line in lines]
failed = [line for line in lines if "Failed password" in line]
ips = [line.split("from ")[1].split()[0] for line in failed]
```

A set comprehension removes duplicates:

```python
unique_ips = {extract_ip(line) for line in failed}
```

A dict comprehension builds a mapping:

```python
length_by_ip = {ip: len(ip) for ip in unique_ips}
```

Generator expression: like a comprehension but lazy.

```python
total = sum(len(line) for line in lines)
```

Use a comprehension when the whole result is the point. Use a normal loop when
you need logging, `break`, or several side effects.

## Counting with `Counter`

```python
from collections import Counter

counts = Counter()
for line in lines:
    counts[classify(line)] += 1
```

`Counter` ignores the `None` key if you choose to filter first. It also has:

```python
counts.most_common(3)       # [(item, count), ...] sorted by count
sum(counts.values())
counts["missing"]           # 0, no KeyError
```

For a deterministic top-N with ties, sort yourself:

```python
top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:3]
```

Explain the key: descending count (`-count`), then ascending IP. Without the
second component, tie order depends on insertion order and your report becomes
unstable.

## Classifying log lines

Order matters. A line can contain both “Failed password” and “invalid user”:

```
Failed password for invalid user admin from 198.51.100.22 ...
```

The mission defines this as **failed**, not invalid. Encode that precedence:

```python
def classify(line):
    if "Accepted " in line:
        return "accepted"
    if "Failed password" in line:
        return "failed"
    if "Invalid user" in line:
        return "invalid"
    return None
```

Write the rules down before coding. “It looked right on my sample” is how log
dashboards quietly lie.

## Extracting an IP without regex

```python
def extract_ip(line):
    marker = " from "
    if marker not in line:
        return None
    return line.split(marker, 1)[1].split()[0]
```

This works for the sample. It breaks if the format changes or if “from” appears
elsewhere. Regex (module 9) is more precise, but simple splitting is a valid
first tool. Know which assumptions you are making.

## Writing JSON

```python
import json

with open(output_path, "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=2)
```

Use `encoding="utf-8"` explicitly. Use `indent=2` for humans and tests.
`json.dump` does not add a trailing newline; add one if your tooling expects it.

## Guided walkthrough

```bash
cd "$(python3 main.py doctor | sed -n 's/^  \[ok\] Lab: //p' | head -1)" 2>/dev/null || true
mkdir -p 05_log_triage
cd 05_log_triage
```

Explore the provided log:

```bash
wc -l auth.log
grep -c "Accepted " auth.log
grep -c "Failed password" auth.log
grep -c "Invalid user" auth.log
grep "Failed password" auth.log | awk '{print $NF}' | head
```

Careful: the last column is not the IP; look at the text after `from`.
Practice in the REPL:

```bash
python3 - <<'PY'
from collections import Counter
lines = open("auth.log", encoding="utf-8").readlines()
counts = Counter()
for line in lines:
    if "Accepted " in line:
        counts["accepted"] += 1
    elif "Failed password" in line:
        counts["failed"] += 1
    elif "Invalid user" in line:
        counts["invalid"] += 1
print(counts, "total", len(lines))
PY
```

Then write `log_triage.py` and run:

```bash
python3 log_triage.py auth.log report.json
python3 -m json.tool report.json
```

Verify:

```bash
python3 main.py verify 5
```

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| Counting `invalid` before `failed` | failed+invalid lines land in the wrong bucket | follow the documented precedence |
| Sorting `most_common()` | ties in insertion order | `key=lambda item: (-count, ip)` |
| Forgetting `strip()` | IP has a trailing newline | strip before splitting |
| Reading a huge file with `readlines()` | high memory | iterate the file handle |
| `except:` around the whole loop | hides real bugs | catch specific exceptions |
| Writing JSON without `indent` | unreadable diff | `indent=2` |
| Using `set` for top IPs | order lost | sort before output |

## Mission checklist

- [ ] `05_log_triage/log_triage.py` exists.
- [ ] Takes the log path and output path as arguments.
- [ ] Classification order: accepted, failed, invalid.
- [ ] `total_lines` counts every line.
- [ ] `top_bad_ips` includes failed + invalid events, top 3, stable sort.
- [ ] Writes indented JSON to the requested path.

Then run:

```bash
python3 main.py verify 5
```

## Extra practice

1. Add `"first_seen"` and `"last_seen"` timestamps per bad IP.
2. Group counts by hour using the leading `Jan 12 03:15:xx` timestamp.
3. Add `--top N` and `--since "03:15:00"` options.
4. Handle gzip logs with the `gzip` module (`.gz` suffix).
5. Compare your top IPs with:
   `grep -E "Failed password|Invalid user" auth.log | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | sort | uniq -c | sort -rn`.
