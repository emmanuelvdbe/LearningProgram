# Linux+ Python Lab

An in-depth, hands-on Python course built around the kind of work a CompTIA
Linux+ (XK0-005) administrator actually does: scripting, log triage, user and
permission audits, network checks, service inspection, backups, and automated
testing.

This is not a quiz app. Every module has a written lesson, a real mission, and
an automatic verifier that inspects files, permissions, command output,
sockets, or archives you produced in a sandbox workspace. You pass by doing the
work, not by selecting an answer.

- **16 modules**, roughly 25–30 hours of guided work
- **No third-party dependencies** — Python 3.10+ standard library only
- **Root-free** — every mission uses fixtures inside a lab directory
- **Reference solutions included** for when you are genuinely stuck
- **Self-tests** that prove every reference solution passes its own checker

---

## Quick start

```bash
cd "/mnt/Main/code/vsc/python/Learning Program"
python3 main.py
```

With no arguments you get the interactive menu. To go straight to work:

```bash
python3 main.py doctor        # check Python, tools, lab, and files
python3 main.py list          # see all 16 modules and progress
python3 main.py next          # jump to the next incomplete module
python3 main.py show 1        # read module 1's lesson
python3 main.py mission 1     # print the hands-on task and workspace path
python3 main.py verify 1      # run the real checks against your work
```

Other useful commands:

| Command | Purpose |
| --- | --- |
| `python3 main.py hint N` | Progressive hints, without giving away the whole answer |
| `python3 main.py solution N` | Page the reference solution |
| `python3 main.py solution N --write` | Copy it to `<lab>/_reference/` for study |
| `python3 main.py progress` | Detailed status and next step |
| `python3 main.py reset N --yes` | Delete one mission workspace and its progress |
| `python3 main.py reset --yes` | Start the whole course over |

Module numbers (`1`–`16`) and IDs (`m01`–`m16`) both work.

---

## How a module works

1. **Read** the lesson (`show N`). Lessons explain the concept with Linux+
   context and runnable examples.
2. **Attempt** the mission in the lab (`mission N`). You write real scripts and
   run real commands.
3. **Verify** (`verify N`). Each check reports `[ok]` or `[!!]` with a concrete
   reason. Failed checks do not reveal the answer; use a hint if needed.
4. **Compare** with the reference solution only after a real attempt, then move
   on with `next`.

Progress is stored in `progress.json` next to `main.py` (or inside the lab if
the project folder is read-only).

### Where your work lives

Missions never ask you to modify system files. They create a workspace under
the **lab directory**:

```
~/.local/share/linuxplus-python-lab/     # default fallback
    01_first_contact/
    02_system_report/
    ...
    _reference/                          # solution copies, if requested
```

The app first tries a `workspace/` folder in the project. Some network shares
(CIFS/SMB, for example) silently discard `chmod` and SUID bits, which would
break the permission missions. When that is detected, the lab automatically
falls back to local disk and `doctor` explains why.

Override the location explicitly when you want to:

```bash
python3 main.py --lab ~/python-lab doctor
LINUXPLUS_LAB=/srv/python-lab python3 main.py mission 11
```

Use a local `ext4`, `xfs`, or `btrfs` filesystem for the full course,
especially module 11 (permission audit). `doctor` tells you whether the current
lab supports Unix permission bits.

---

## Curriculum

### Part I — Python foundations

| # | Module | Linux+ focus | Time |
| --- | --- | --- | --- |
| 1 | First contact: a real executable script | 3.1 Scripting basics | 45 min |
| 2 | Variables, types, and f-strings | 1.1 System information | 60 min |
| 3 | Decisions, comparisons, and exit codes | 4.1 Storage troubleshooting | 60 min |
| 4 | Lists, dictionaries, and real `/etc/passwd` data | 1.5 Users and groups | 90 min |

### Part II — Working with Linux data

| # | Module | Linux+ focus | Time |
| --- | --- | --- | --- |
| 5 | Loops, comprehensions, and `Counter` | 2.2 Log analysis | 90 min |
| 6 | Functions and `argparse`: a multi-command toolkit | 3.1 Scripting / 3.3 Automation | 100 min |
| 7 | `pathlib` and file metadata: the janitor | 1.4 Storage management | 90 min |
| 8 | Exceptions: read files without crashing | 4.3 Troubleshooting methodology | 90 min |
| 9 | Regex: parse `ss` and `ip` output | 4.4 Network troubleshooting | 120 min |

### Part III — Talking to the system

| # | Module | Linux+ focus | Time |
| --- | --- | --- | --- |
| 10 | `subprocess`: run commands and capture the truth | 3.1 Scripting / 4.3 Troubleshooting | 100 min |
| 11 | `os.stat` and bitmasks: permission audit | 2.1 Security / file permissions | 110 min |
| 12 | Sockets: build a TCP port checker | 4.4 Network troubleshooting | 90 min |
| 13 | Config formats: systemd unit inspector | 1.2 Services / systemd | 100 min |

### Part IV — Production habits

| # | Module | Linux+ focus | Time |
| --- | --- | --- | --- |
| 14 | Logging, `tarfile`, and retention: a real backup tool | 1.4 Storage / 3.3 Automation | 120 min |
| 15 | Debugging and `unittest`: fix it, then prove it | 4.5 Troubleshooting | 120 min |
| 16 | Capstone: package a Linux+ security audit kit | All domains | 180 min |

### Suggested schedules

- **Six weeks (steady):** 2–3 modules per week. Pair modules 7–8, 11–12, and
  13–14 because they share fixtures and concepts.
- **Three weeks (focused):** one part per week; do the capstone on a weekend.
- **Weekend sprint:** modules 1–6 as a refresher, then 11, 14, and 16. Do not
  skip the missions; reading alone will not build the skill.
- **Exam-first:** work modules 2, 4, 5, 9, 10, 11, and 13 before your exam date,
  then return for the rest.

---

## What the missions actually check

The verifiers are ordinary Python, and they look at evidence rather than
intentions:

- Scripts exist, have the required shebang, are executable, and run directly
  with the expected output and exit status.
- Parsers are fed real fixture files (`passwd`, auth logs, CSV, `ss`/`ip`
  samples) and compared on structured output.
- Permission missions inspect `st_mode` for exact mode bits, SUID/SGID, and
  sticky bits — which is why the lab must be on a real local filesystem.
- Network missions bind local TCP sockets and require correct open/closed
  reporting without hanging.
- Backup missions inspect the produced tar archive, its contents, and retention
  behavior.
- The capstone runs a packaged tool as a subprocess and validates its JSON
  report schema and findings.

A check failure includes enough detail to debug (missing file, wrong mode,
unexpected output, timeout) without handing you the implementation.

---

## Safety notes

- **No root required.** Do not run the course with `sudo`.
- **Sandboxed fixtures only.** Missions create fake system files inside the
  lab; they do not edit `/etc/passwd`, `/etc/shadow`, or live unit files.
- **Audits are read-only** on the fixtures they are given.
- **Network checks are local.** The port checker connects to sockets started
  by the mission on `127.0.0.1`; it does not scan external hosts.
- **Reset is destructive only inside the lab.** `reset` removes a mission
  workspace and its progress entry.
- Reference solutions are teaching material. Run them in the lab, not as
  privileged production scripts.

---

## Troubleshooting

**`doctor` says the lab cannot store permission bits.**
The project folder is on a filesystem without Unix permissions (common on
CIFS/SMB mounts). Let the app fall back automatically, or set
`LINUXPLUS_LAB` to a directory on `ext4`, `xfs`, or `btrfs`.

**A permission mission fails even though `chmod` looked correct.**
Check `doctor` again. If the lab is on a network share, mode bits may not
persist. Re-run with `--lab ~/python-lab`.

**`ss`, `ip`, `tar`, or `systemctl` is reported missing.**
The core missions still run, but related examples are less realistic. Install
the matching package (`iproute2`, `tar`, `systemd`) if available. No mission
requires a running systemd instance.

**Progress looks stale or a workspace is corrupted.**
Reset that module and redo it:

```bash
python3 main.py reset 7 --yes
python3 main.py mission 7
```

**I want to inspect what the verifier ran.**
Read the mission definitions in `curriculum/missions/part1.py`–`part4.py`.
They are plain Python and intentionally readable.

---

## Project layout

```
main.py                         CLI, styling, pager, lab detection, progress
curriculum/
    __init__.py                 package exports
    syllabus.py                 ordered module metadata and exam mapping
    lessons/                    sixteen Markdown lessons
    missions/
        base.py                 Mission/Check types and shared helpers
        part1.py ... part4.py   mission briefs, fixtures, checkers, solutions
        __init__.py             mission registry
tests/
    test_missions.py            solution, lesson, and syllabus self-tests
progress.json                   your progress (generated)
```

Run the self-tests any time:

```bash
cd "/mnt/Main/code/vsc/python/Learning Program"
python3 -m unittest discover -s tests -v
```

Expected result: all tests pass, including the test that installs and verifies
every reference solution.

---

## Requirements

- Python **3.10 or newer** (tested on 3.13)
- Linux or another Unix-like system with standard tools: `sh`, `tar`
- Recommended: `git`, `ss`, `ip`, `systemctl`, `less`, `nano`
- A local filesystem with Unix permission support for the full path

No `pip install` step. No virtual environment required.
