# Module 17 — Production shell scripting

> **Exam objective:** Linux+ 4.2 — Given a scenario, script with shell
> commands.
> **Study time:** about 120 minutes, including the mission.
> **Mission:** `audit_report.sh` — a defensive log report with options,
> functions, `IFS` parsing, regex matching, CSV output, and meaningful exit
> codes.

## What the exam expects

- **expansion:** variable, command substitution, arithmetic, parameter
  expansion (`${var:-default}`, `${file##*/}`, `${var%.*}`, `${var//a/b}`),
- **quoting:** single, double, `$'...'`, and why unquoted variables break,
- **conditionals:** `if`, `case`, `[[ ... ]]` operators,
- **loops:** `for`, `while`, `until`, `select`,
- **tests:** string (`-z`, `-n`, `=`), numeric (`-eq`, `-lt`), file (`-f`,
  `-d`, `-x`, `-s`),
- **regular expressions:** `[[ $x =~ ^...$ ]]`, `grep -E`,
- **functions,** `local`, return codes,
- **arrays** and `IFS` splitting,
- **redirection** and `exec`,
- **exit codes** and error handling (`set -euo pipefail`, `trap`).

## The strict-mode header

```bash
#!/usr/bin/env bash
set -euo pipefail
```

- `-e` — exit on any command failure (with documented exceptions),
- `-u` — error on an undefined variable,
- `-o pipefail` — a pipeline fails if **any** command fails, not just the last.

Add traps for cleanup and diagnostics:

```bash
trap 'echo "error on line $LINENO" >&2' ERR
trap 'rm -f "$tmp"' EXIT
```

Never use `set -e` blindly: it interacts badly with `if cmd; then`, `|| true`,
and commands that legitimately return non-zero. The rule is to understand
each failure path.

`#!/usr/bin/env bash` finds bash in `PATH`, which is more portable than
`#!/bin/bash` (bash is not always in `/bin`).

## Expansion

### Variables and quoting

```bash
name="world"
echo "hello $name"
echo 'hello $name'          # single quotes: literal
echo "today is $(date +%F)"
count=$((1 + 2))
```

Double quotes preserve spaces and prevent globbing and word splitting. Always
quote variables:

```bash
for f in "$@"; do echo "$f"; done     # correct
for f in $@; do echo "$f"; done       # breaks on spaces
```

### Parameter expansion

```bash
file=/var/log/app/current.log

echo "${file##*/}"        # current.log     (strip longest prefix */)
echo "${file%/*}"         # /var/log/app    (strip shortest suffix /*)
echo "${file%.*}"         # /var/log/app/current
echo "${file##*.}"        # log
echo "${file/app/prod}"   # /var/log/prod/current.log
echo "${file//\//_}"      # _var_log_app_current.log
echo "${#file}"           # length
echo "${unset:-default}"  # default if unset/empty
echo "${unset:=default}"  # assign and use default
echo "${var:?must be set}"# error if unset
```

`${file##*/}` is the safe basename without calling `basename`. `${var%.*}`
removes an extension.

### Command substitution and arithmetic

```bash
now=$(date +%s)
files=$(find . -type f | wc -l)
echo $(( files * 2 ))
(( total += 5 ))
```

Use `$(...)` rather than backticks; it nests correctly.

## Tests and conditionals

```bash
if [[ -f "$config" && -r "$config" ]]; then
    echo "readable file"
elif [[ -d "$config" ]]; then
    echo "directory"
else
    echo "missing" >&2
    exit 1
fi
```

`[[ ... ]]` is bash's improved test. It supports `&&`, `||`, pattern matching
(`==` with globs), and regex (`=~`). Prefer it over `[ ... ]`.

### String tests

| Test | True when |
|---|---|
| `-z "$s"` | string is empty |
| `-n "$s"` | string is non-empty |
| `"$a" == "$b"` | equal (in `[[ ]]`, the right side may be a glob) |
| `"$a" != "$b"` | not equal |

### Numeric tests

| Test | True when |
|---|---|
| `-eq`, `-ne` | equal, not equal |
| `-lt`, `-le` | less than, less than or equal |
| `-gt`, `-ge` | greater than, greater than or equal |

### File tests

| Test | True when |
|---|---|
| `-e` | exists |
| `-f` | regular file |
| `-d` | directory |
| `-r` / `-w` / `-x` | readable / writable / executable |
| `-s` | exists and has size > 0 |
| `-L` | symbolic link |
| `file1 -nt file2` | file1 newer than file2 |

## `case`

```bash
case "$1" in
    -t|--threshold) threshold=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) usage >&2; exit 2 ;;
    *) break ;;
esac
```

`case` is the clean way to parse options without `getopts`'s limitations. It
supports globs: `*.log`, `[0-9]*`, `start|stop)`.

## Loops

```bash
for host in web01 web02 db01; do
    echo "checking $host"
done

for i in {1..5}; do echo "$i"; done

while IFS= read -r line; do
    echo "line: $line"
done < input.txt

while read -r service errs warns; do
    printf '%s,%s,%s\n' "$service" "$errs" "$warns"
done < <(tail -n +2 counts.txt)
```

Rules:

- `while IFS= read -r line` is the correct file-reading loop. Without
  `IFS=`, leading whitespace is trimmed; without `-r`, backslashes are eaten.
- Use `< file` for a file, `<<< "$var"` for a string, and
  `done < <(command)` for process substitution.
- A pipeline creates a subshell; variables set inside `cmd | while read` are
  lost. Use process substitution when you need them to persist.
- `break` exits the loop, `continue` skips to the next iteration.

## Arrays

```bash
hosts=(web01 web02 db01)
echo "${hosts[0]}"
echo "${#hosts[@]}"
for h in "${hosts[@]}"; do echo "$h"; done
hosts+=("cache01")
declare -A counts
counts[web]=3
echo "${counts[web]}"
```

Quote array expansion: `"${arr[@]}"`, not `${arr[@]}`. Associative arrays need
`declare -A` and are bash-only.

## Functions

```bash
usage() {
    cat >&2 <<'EOF'
usage: audit_report.sh [-t THRESHOLD] SOURCE OUT
EOF
}

report() {
    local service=$1
    local errors=$2
    printf '%s,%s\n' "$service" "$errors"
}
```

- `local` keeps variables from leaking into the caller.
- Functions return an exit status (0–255), not a value. Send data to stdout and
  capture with `$(...)`.
- `return 1` in a function behaves like `exit 1` inside the function only.

## Regular expressions

`[[ ... =~ ... ]]` uses POSIX extended regular expressions:

```bash
if [[ "$msg" =~ (timeout|disk\ full) ]]; then
    incidents=$((incidents + 1))
fi

if [[ "$line" =~ ^([A-Z]+)\|([^|]+)\|(.*)$ ]]; then
    level=${BASH_REMATCH[1]}
    service=${BASH_REMATCH[2]}
    message=${BASH_REMATCH[3]}
fi
```

`BASH_REMATCH` holds the captures. Quote the regex only when you want a literal
string; an unquoted regex is matched as a pattern.

`grep -E`, `sed -E`, and `awk` use the same ideas on files.

## `IFS` and delimited input

`IFS` is the internal field separator used by `read` and word splitting.

```bash
IFS='|' read -r level service message <<< "ERROR|api|connection timeout"
unset IFS
```

Setting `IFS` only for the `read` prefix keeps it from affecting the rest of
the script. For CSV, remember that fields can contain the delimiter; a real CSV
parser is safer than `cut` or `awk -F,` for arbitrary data.

## Redirection and `exec`

```bash
exec > >(tee -a "$log") 2>&1   # send all output to a log and stdout
exec 3> file                   # open FD 3 for writing
echo "x" >&3
exec 3>&-
```

`exec` with only redirections changes the current shell's file descriptors
permanently. Useful for logging an entire script.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | general failure |
| 2 | usage error (common convention) |
| 126 | found but not executable |
| 127 | command not found |
| 128+N | killed by signal N (130 = `SIGINT`) |

Exit codes let callers and CI systems react. `set -e` plus explicit `exit 2`
for usage errors, `exit 1` for a policy violation, and `exit 0` for success is
a clean contract.

## Writing defensively

1. Validate arguments before doing work.
2. Fail early with a clear message to stderr.
3. Use a temporary directory with `mktemp -d` and clean it with `trap`.
4. Quote every expansion.
5. Check that input files exist and are readable.
6. Never `eval` untrusted input.
7. Do not parse `ls`; use `find -print0` and `while read -d ''`.
8. Write to a temporary file and `mv` into place for atomic updates.
9. Log what you did and where.
10. Test the failure paths, not just the happy path.

```bash
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
```

## Debugging

```bash
bash -n script.sh        # syntax check only
bash -x script.sh        # trace each command
set -x / set +x          # trace a section
PS4='+${BASH_SOURCE}:${LINENO}: ' bash -x script.sh
shellcheck script.sh     # static analysis, install separately
```

`bash -n` catches syntax errors before you run anything dangerous. `-x` shows
what actually expanded, which is how you find a quoting bug.

## Mission 17 — what you build

Write an executable `audit_report.sh`:

```
./audit_report.sh [-t THRESHOLD] SOURCE OUT
```

Rules:

- `set -euo pipefail`, a `usage()` function, `local` variables, a `case`
  statement, `IFS='|'` reads, a `[[ ... =~ ... ]]` regex, and `${file##*/}`
  parameter expansion.
- No arguments or the wrong number: usage to stderr, exit 2.
- `SOURCE` not a directory: exit 2.
- Unknown option: usage, exit 2. `-h`: usage, exit 0.
- Read every `*.log` in `SOURCE`. Each line is `LEVEL|service|message`.
- Write `OUT` as CSV: header `service,errors,warnings`, one row per service,
  sorted by service.
- Print `services=N errors=N warnings=N` and `incidents=N`, where incidents
  are messages matching `timeout` or `disk full`.
- With `-t N`, exit 1 when total errors are greater than N; otherwise 0.
- Create `OUT`'s parent directory.

The fixture is `logs/`; write to `reports/summary.csv` while testing. Run
`python3 main.py verify 17`.

## Exam traps

- Unquoted `$var` splits on whitespace and expands globs.
- `[ $x = y ]` breaks when `$x` is empty; use `[[ "$x" == y ]]`.
- `read` without `-r` eats backslashes.
- `while read` in a pipeline runs in a subshell; changes are lost.
- `local` outside a function is an error.
- `set -e` is disabled inside `if`, `&&`, `||`, and `!` contexts — know where.
- `$(...)` strips trailing newlines.
- `echo -e` is not portable; use `printf`.
- `basename`/`dirname` are external; `${file##*/}` and `${file%/*}` are free.
- Exit codes above 255 wrap around.

## Check yourself

1. What do `set -e`, `set -u`, and `set -o pipefail` each do?
2. How do you strip the directory and the extension from a path without
   external commands?
3. Why is `while IFS= read -r line` the right file loop?
4. What does `${var:-default}` do when `var` is set but empty?
5. Where do regex captures go after `[[ $x =~ ... ]]`?
6. What exit code should a usage error use, and why?
7. Why can a variable set inside `cmd | while read` disappear?
8. Which two commands check syntax and trace execution?

## Going deeper

- Rewrite a fragile one-liner as a script with `set -euo pipefail`, functions,
  and a `trap`.
- Run `shellcheck` on your scripts and fix every warning.
- Parse a CSV with embedded delimiters and explain why `awk -F,` fails.
- Compare `for f in $(find ...)` with `find ... -print0 | while read -d ''` on
  filenames containing spaces and newlines.
