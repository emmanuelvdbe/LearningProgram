# Module 9 — Regex: parse ss and ip output

## Why this matters for Linux+

Linux+ troubleshooting is largely about reading command output:
`ip addr`, `ss -tuln`, `ping`, `dig`, `journalctl`. Python gets much more
useful when it can extract fields from that text and turn them into JSON.

This module builds a parser for saved `ss` and `ip` output. The patterns are
the same ones you would use in a monitoring agent.

## When to use regex

Use regex when:

- the data is line-oriented text with a stable but space-padded layout,
- you need one field out of a noisy line,
- the command has no JSON/`-o` mode.

Do **not** use regex when:

- a parser already exists (`json`, `configparser`, `csv`),
- you can split on a simple delimiter (`line.split(":")`),
- the format is HTML/XML/JSON.

Regex is powerful and easy to over-apply. Prefer the simplest tool that is
correct.

## The core syntax

| Pattern | Matches |
|---|---|
| `.` | any character except newline |
| `\d` | a digit `[0-9]` |
| `\w` | word character `[A-Za-z0-9_]` |
| `\s` | whitespace |
| `\S` | non-whitespace |
| `[abc]` | one of a, b, c |
| `[^abc]` | anything except a, b, c |
| `*` | zero or more |
| `+` | one or more |
| `?` | zero or one |
| `{3}` / `{2,5}` | exact / range count |
| `^` / `$` | start / end of line (or string) |
| `( ... )` | capture group |
| `(?P<name>...)` | named capture group |
| `\|` | alternation |
| `\\.` | a literal dot |

Always use **raw strings** for regex: `r"\d+"`, not `"\d+"`. Otherwise Python
interprets backslashes before the regex engine sees them.

## `search`, `match`, `fullmatch`, `findall`

```python
import re

text = "Failed password for root from 203.0.113.7 port 40001 ssh2"

re.search(r"from (\S+)", text)     # first match anywhere
re.match(r"Failed", text)          # only at the start
re.fullmatch(r"Failed.*", text)    # the whole string
re.findall(r"\d+", text)           # ['203', '0', '113', '7', '40001']
```

`search` returns a `Match` object or `None`. Always check before using:

```python
match = re.search(r"from (\S+)", text)
if match:
    print(match.group(1))
```

Using `match.group(1)` when `match` is `None` raises
`AttributeError: 'NoneType' object has no attribute 'group'`. That is one of
the most common Python regex bugs.

## Groups

```python
pattern = re.compile(r"^(tcp|udp)\s+(LISTEN|UNCONN)\s+(\S+):(\d+)")
match = pattern.search(line)
if match:
    proto, state, address, port = match.groups()
```

Named groups make the code self-documenting:

```python
pattern = re.compile(
    r"^(?P<proto>tcp|udp)\s+"
    r"(?P<state>LISTEN|UNCONN)\s+"
    r"(?P<address>\S+):(?P<port>\d+)"
)
match = pattern.search(line)
if match:
    data = match.groupdict()
    data["port"] = int(data["port"])
```

`re.compile` once at module level is faster and keeps the pattern in one
place. For short scripts, `re.search(pattern, text)` is fine.

## Greedy vs. specific

`.*` is greedy: it consumes as much as possible, then backtracks. That can
swallow the field you wanted.

```python
line = "from 203.0.113.7 port 40001"
re.search(r"from (.*) port", line).group(1)   # '203.0.113.7' (works)
re.search(r"from (.*) ", line).group(1)       # '203.0.113.7'
```

Prefer a precise character class over `.*`:

```python
r"from (\d{1,3}(?:\.\d{1,3}){3})"
```

`(?:...)` is a non-capturing group: it groups without adding a backreference.
Use it when you only need the outer value.

## Anchors and multiline text

By default, `^` and `$` match the start and end of the whole string. When you
search line by line (the usual case for command output), each line is its own
string, so anchors behave as expected.

If you pass a whole file to `re.finditer`, use `re.MULTILINE`:

```python
for match in re.finditer(pattern, text, re.MULTILINE):
    ...
```

## Escaping

A literal dot is `\.`. A literal backslash is `\\`. A literal `[` is `\[`.

```python
re.search(r"\d+\.\d+", "version 3.13")   # '3.13'
```

If you build a pattern from user input, escape it:

```python
re.escape(user_supplied_string)
```

Never interpolate untrusted text into a regex without escaping; a crafted
pattern can be expensive (ReDoS) or match the wrong thing.

## Parsing `ss -tuln`

Sample:

```text
Netid State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process
tcp   LISTEN 0      128    0.0.0.0:22         0.0.0.0:*     users:(("sshd",pid=567,fd=3))
udp   UNCONN 0      0      [::]:546           [::]:*        users:(("dhclient",pid=1234,fd=9))
```

Columns are whitespace-separated, but the local address may contain `[::]` and
`0.0.0.0`, and the process column contains punctuation. A robust pattern:

```python
SS_RE = re.compile(
    r"^(?P<proto>tcp|udp)\s+"
    r"(?P<state>LISTEN|UNCONN)\s+"
    r"\d+\s+\d+\s+"
    r"(?P<address>\S+):(?P<port>\d+)\s+"
    r"\S+\s*"
    r"(?P<rest>.*)$"
)
```

Then extract the process name separately:

```python
PROC_RE = re.compile(r'users:\(\("(?P<name>[^"]+)"')
```

Why parse the rest separately? Because the process column is optional and its
format varies across `ss` versions. Keeping the main pattern focused on the
stable columns is more maintainable.

Filter states:

- `LISTEN` for TCP listening sockets,
- `UNCONN` for UDP sockets (UDP has no connection state),
- ignore `ESTAB`, `TIME-WAIT`, etc.

## Parsing `ip -o addr show`

Sample:

```text
2: eth0    inet 192.168.1.10/24 brd 192.168.1.255 scope global dynamic eth0\       valid_lft ...
1: lo    inet6 ::1/128 scope host \       valid_lft forever ...
```

Pattern:

```python
IP_RE = re.compile(
    r"^\d+:\s+(?P<iface>\S+)\s+"
    r"(?P<family>inet6?)\s+"
    r"(?P<address>[0-9a-fA-F:.]+)/(?P<prefix>\d+)\s"
)
```

The prefix is part of `address/prefix`. Convert it to `int`.

Note that `inet6` must be matched before `inet` if you use alternation without
anchoring the boundary. `(inet6?|inet)` is ambiguous; here `inet6?` greedily
matches the optional `6`, which is what we want.

## Sorting the output

JSON arrays have order. For stable verification and diffs, define it:

```python
sockets.sort(key=lambda item: (item["proto"], item["port"], item["local_address"]))
addresses.sort(key=lambda item: (item["iface"], item["family"], item["address"]))
```

Document the order in the docstring or the mission brief. “Whatever the file
happened to contain” is not an interface.

## Guided walkthrough

```bash
cd "$(python3 main.py doctor | sed -n 's/^  \[ok\] Lab: //p' | head -1)" 2>/dev/null || true
mkdir -p 09_netparse
cd 09_netparse
```

Look at the samples:

```bash
cat fixtures/ss.txt
cat fixtures/ip_addr.txt
```

Experiment in the REPL:

```bash
python3 - <<'PY'
import re
line = 'tcp   LISTEN 0      128    0.0.0.0:22         0.0.0.0:*     users:(("sshd",pid=567,fd=3))'
m = re.search(r'^(tcp|udp)\s+(LISTEN|UNCONN)\s+\d+\s+\d+\s+(\S+):(\d+)', line)
print(m.groups() if m else None)
print(re.search(r'users:\(\("([^"]+)"', line).group(1))
PY
```

Then write `netparse.py` with `ss` and `ip` modes. Test both:

```bash
python3 netparse.py ss fixtures/ss.txt | python3 -m json.tool
python3 netparse.py ip fixtures/ip_addr.txt | python3 -m json.tool
```

Verify:

```bash
python3 main.py verify 9
```

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| `re.search(...).group(1)` without a None check | `AttributeError` | use `if match:` |
| Using `match` when the pattern is not anchored | misses real matches | use `search` |
| Forgetting `r""` | `\d` becomes a backspace or escape | raw string |
| `.*` swallowing fields | wrong capture | use `\S+` / `\d+` |
| Assuming `ss` columns are fixed-width | breaks with long addresses | split on whitespace |
| Parsing `inet` before `inet6` | family truncated | order the alternatives |
| Ignoring `UNCONN` | UDP sockets missing | include it |
| Output order depends on input | unstable test | sort explicitly |

## Mission checklist

- [ ] `09_netparse/netparse.py` exists.
- [ ] `ss` mode keeps LISTEN/UNCONN, ignores ESTAB.
- [ ] Local address and port are split correctly (`0.0.0.0`, `[::]`, IPv4).
- [ ] Process name is extracted or `""`.
- [ ] `ip` mode extracts iface, family, address, prefix.
- [ ] Output is JSON, sorted by the documented keys.
- [ ] Missing file / unknown mode exits 2.

Then run:

```bash
python3 main.py verify 9
```

## Extra practice

1. Parse `ss -tnp` and report only established connections.
2. Add a mode for `ip route show`.
3. Handle IPv6 zone IDs (`fe80::1%eth0`) without breaking.
4. Compare your parser with `ss -tulnH` (no header) and `ip -j addr show`
   (JSON output). Which is easier to maintain?
5. Write unit tests for five malformed lines that must be ignored.
