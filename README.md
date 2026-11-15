# CompTIA Study Lab

A hands-on, multi-exam study platform for CompTIA certifications. It pairs
written lessons with real missions, then verifies the result by inspecting
files, permissions, command output, sockets, or archives — not by asking
multiple-choice questions.

- **Multiple exams** — switch between exams without losing progress
- **Save slots** — separate progress files for different learners or runs
- **Objectives inbox** — drop official CompTIA PDFs/text and extract them
- **Built-in Linux+ packs** — XK0-005 (16 modules) and XK0-006 (22 modules),
  about 59 study hours in total
- **Graphical lab** — Tkinter window with lessons, missions, a file editor,
  and bubblewrap-sandboxed terminals for real command execution
- **No third-party Python packages** — standard library only
- **Root-free** — every mission runs against sandbox fixtures

---

## Quick start

```bash
cd "/mnt/Main/code/vsc/python/Learning Program"
python3 main.py
```

With no arguments you get the interactive menu. Direct commands:

```bash
python3 main.py gui             # graphical lab with sandboxed terminals
python3 main.py doctor          # Python, tools, exam, save, lab, objectives
python3 main.py list            # modules in the active exam
python3 main.py exam list       # every discovered exam
python3 main.py save list       # every save slot
python3 main.py next            # next incomplete module
```

Daily workflow:

```bash
python3 main.py show 1
python3 main.py mission 1
# ... do the work in another terminal ...
python3 main.py verify 1
python3 main.py hint 1          # only after a real attempt
python3 main.py solution 1      # compare afterwards
```

---

## Graphical lab with sandboxed terminals

```bash
python3 main.py gui
python3 gui.py                  # same window, direct launch
python3 gui.py --module 3       # open a module immediately
python3 main.py gui --check     # Tkinter, display, and bubblewrap only
```

The GUI is optional. The CLI keeps working without Tkinter, a display, or
bubblewrap.

Requirements:

- Python with Tkinter (`python3-tk` on Debian/Ubuntu)
- `bubblewrap` (`bwrap`) for sandboxed terminals
- X11 or Wayland (`DISPLAY` or `WAYLAND_DISPLAY`)

`python3 main.py doctor` reports Tkinter and bubblewrap alongside the other
checks. If bubblewrap is missing, the GUI still opens; the Terminal tab
explains that sandboxed sessions are disabled and the Files tab still works.

### What is in the window

| Area | What it does |
| --- | --- |
| Exam and save selectors | Switch exams or save slots in place; progress updates immediately |
| Module tree | Every module grouped by part, with a `✓` for verified missions |
| Lesson | The full Markdown lesson, rendered with headings, tables, quotes, and code |
| Mission | Brief, revealed hints, **Verify mission**, and reference solutions |
| Terminal | One or more persistent, sandboxed shells for the current mission |
| Files | Edit workspace files directly, with Save/Reload/New/Delete |

**Verify mission** runs the same checks as `python3 main.py verify N`, against
the same files the sandbox edits. It marks the mission complete in the active
save on success and records an attempt on failure. Hints reveal one at a time.
Reference solutions open in a separate window and can be installed into a
`_reference/` folder without touching your own work.

Keyboard: `Ctrl-1`…`Ctrl-4` switch tabs, `F5` verifies, `Ctrl-S` saves the
file in the editor. In a terminal, press Enter to run the command in the entry
box, `Ctrl-C` to interrupt, and `Ctrl-D` to exit the shell.

### Terminal sandbox

Every terminal is a `bwrap --unshare-all` sandbox. The shell is real, `cd`
persists between commands, and commands inspect and change the mission
workspace for real.

| Host | Inside the session |
| --- | --- |
| `/usr`, `/etc`, `/opt`, `/sys` | mounted **read-only** |
| mission workspace | writable at **`/workspace`** |
| a private folder under the lab | `HOME=/home/student` |
| `/tmp`, `/run`, `/var` | private tmpfs |
| `/home`, `/root`, `/mnt`, `/media`, `/srv`, `/boot` | masked with empty tmpfs |
| capabilities | all dropped |
| network | isolated; loopback works; opt in per **new** session |

The project folder — including `saves/`, exam manifests, and source code — is
not mounted, so a command in the sandbox cannot modify the study platform or
your real home directory. If the platform happens to be installed under a
read-only system directory such as `/opt` or `/usr/local`, the GUI masks that
exact folder too. The sandbox runs as your unprivileged user; there is no
`sudo` and no root inside it.

The **Allow network (new sessions)** checkbox applies to sessions you start
after ticking it. Existing sessions keep the setting they started with. Most
missions need no network; enable it only for a lesson that genuinely needs DNS
or a remote host.

### Terminal limits

The terminal is deliberately **line-oriented**, not a full-screen terminal
emulator:

- Type commands in the entry box; output appears in the scrollback pane.
- `nano`, `vim`, `top`, and other full-screen programs are not usable. Use
  the **Files** tab to create and edit scripts, then run them in a terminal.
- Commands that prompt interactively still read from the PTY, but the GUI has
  no keystroke passthrough. Prefer non-interactive flags (`ssh-keygen -N ''`,
  `openssl ... -batch`, `git commit -m ...`).
- Closing a session ends its shell. **Restart** starts a fresh shell in the
  same workspace with the same network setting. When a shell exits, its tab
  stays visible and is marked `(ended)`.

Each session gets a private scratch home under
`<lab>/<exam-id>/_sandbox/`; delete that folder to reclaim space.

## Objectives inbox — put CompTIA PDFs here

```
/mnt/Main/code/vsc/python/Learning Program/exams/_inbox/
```

Drop any of these formats into that folder:

- `.pdf` (extracted with `pdftotext` from `poppler-utils`)
- `.docx` (extracted with the Python standard library)
- `.md`, `.txt`, `.rst`, `.json`

Suggested names:

```
security-plus-sy0-701.pdf
network-plus-n10-009.pdf
cysa-plus-cs0-003.pdf
linux-plus-xk0-005.pdf
```

Then turn a document into a selectable exam:

```bash
# 1. Create the exam folder and manifest
python3 main.py exam add security-plus-sy0-701 \
    --name "CompTIA Security+ (SY0-701)" --code SY0-701

# 2. Copy the objectives into that exam
python3 main.py exam attach security-plus-sy0-701 \
    exams/_inbox/security-plus-sy0-701.pdf

# 3. Extract readable text
python3 main.py exam scan security-plus-sy0-701

# 4. Read the objectives inside the app
python3 main.py exam objectives security-plus-sy0-701

# 5. Select the exam in the current save
python3 main.py exam use security-plus-sy0-701
```

A newly added exam is **objectives-only**: it is selectable, its documents are
readable, and the save slot remembers it, but it has no missions until a
curriculum pack is built for it. Linux+ ships with two complete packs. Once you
have dropped an objectives PDF, the extracted text under
`exams/<exam-id>/objectives/_text/` is what a curriculum pack is built from.

### Exam commands

| Command | Purpose |
| --- | --- |
| `exam list` | List every exam, its status, and progress in the active save |
| `exam use <id>` | Select an exam inside the current save |
| `exam info [id]` | Metadata, domains, objectives, module count, progress |
| `exam add <id> --name NAME` | Scaffold a new objectives-only exam |
| `exam attach <id> <file>` | Copy an objectives document into an exam |
| `exam scan [id]` | Extract text from the inbox and the exam's documents |
| `exam objectives [id]` | Print the readable objectives |

Exam IDs are derived from the folder name. Short prefixes work when unique:
`exam use security` resolves `security-plus-sy0-701` if only one exam matches.
Exam codes such as `SY0-701` also work.

---

## Save slots

Each save slot is an independent JSON progress file with its own active exam:

```bash
python3 main.py save list
python3 main.py save new alice
python3 main.py save use alice
python3 main.py save show
python3 main.py save copy alice backup
python3 main.py save delete backup --yes
```

- Switching saves changes both the active exam and all visible progress.
- Progress for every exam is stored inside the save, so switching exams inside
  one save never overwrites another exam's missions.
- Deleting the active save automatically switches to a remaining slot.
- The last save slot cannot be deleted.
- Save files live under `saves/` next to `main.py`. If that folder is not
  writable, they fall back to `<lab>/saves/`.

Example file (`saves/default.json`):

```json
{
  "kind": "comptia-study-lab-save",
  "version": 1,
  "name": "default",
  "active_exam": "linux-plus-xk0-005",
  "progress": {
    "linux-plus-xk0-005": {
      "completed": {"m01": {"at": "2026-11-13T12:00:00"}},
      "attempts": {"m02": 2}
    }
  }
}
```

The old single-course `progress.json` is imported automatically into the
`linux-plus-xk0-005` progress of the `default` save on first run.

---

## Included exams

| Exam | Code | Pack | Modules | Study time |
| --- | --- | --- | --- | --- |
| CompTIA Linux+ | XK0-005 | built-in | 16 | ~26 hours |
| CompTIA Linux+ | XK0-006 | built-in | 22 | ~39 hours |

Both packs live in the same save slot with independent progress:

```bash
python3 main.py exam use linux-plus-xk0-006
python3 main.py list
python3 main.py show 1
```

### CompTIA Linux+ (XK0-006) — 22 modules

The pack is built directly from the official XK0-006 objectives PDF and follows
its five domains:

| Domain | Weight | Modules | Focus |
| --- | --- | --- | --- |
| 1.0 System Management | 23% | 1–6 | boot/FHS, devices and initrd, storage/LVM/RAID, networking, shell and backups, virtualization |
| 2.0 Services and User Management | 20% | 7–11 | files and links, local accounts, processes and cron, packages and systemd, containers |
| 3.0 Security | 18% | 12–15 | AAA and logging, firewalls and NAT, OS/account hardening, crypto and compliance |
| 4.0 Automation, Orchestration, and Scripting | 17% | 16–19 | IaC and orchestration, shell scripting, Python administration, Git and responsible AI |
| 5.0 Troubleshooting | 22% | 20–22 | monitoring and performance, hardware/storage/OS triage, network and security triage |

Every module has an in-depth lesson and a build-verify mission: audit a
filesystem hierarchy, assemble LVM, parse an nftables ruleset, build a root CA,
write a hardened Dockerfile, create a reviewable Git history, compute an SLO
report, and triage a broken server from real evidence.

- Objective-to-module map:
  [`exams/linux-plus-xk0-006/OBJECTIVES.md`](exams/linux-plus-xk0-006/OBJECTIVES.md)
- Source objectives:
  `exams/linux-plus-xk0-006/objectives/CompTIA Linux+ XK0-006 Exam Objectives (5.0).pdf`
- Tests: `tests/test_xk0_006.py`

---

## Included exam: CompTIA Linux+ (XK0-005)

16 modules, four parts, ~26 hours. Every module has a lesson, a real mission,
and an automatic verifier.

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

- **Six weeks:** 2–3 modules per week. Pair 7–8, 11–12, and 13–14.
- **Three weeks:** one part per week; do the capstone on a weekend.
- **Weekend sprint:** modules 1–6 as a refresher, then 11, 14, and 16.
- **Exam-first:** modules 2, 4, 5, 9, 10, 11, and 13 before exam day.

---

## How a module works

1. **Read** the lesson (`show N`).
2. **Attempt** the mission in the exam workspace (`mission N`).
3. **Verify** (`verify N`). Each check reports `[PASS]` or `[FAIL]` with a
   concrete reason. Failed checks do not reveal the answer.
4. **Compare** with a reference solution after a real attempt, then use `next`.

The verifiers look at evidence:

- Scripts exist, have the required shebang, are executable, and run directly
  with the expected output and exit status.
- Parsers are fed fixture `passwd`, auth logs, CSV, and `ss`/`ip` samples.
- Permission missions inspect exact `st_mode` bits, SUID/SGID, and sticky bits.
- Network missions bind local TCP sockets and require correct open/closed
  reports without hanging.
- Backup missions inspect the produced tar archive and retention behavior.
- The capstone runs a packaged tool as a subprocess and validates its JSON
  report schema and findings.

### Where work lives

```
~/.local/share/linuxplus-python-lab/       # default lab on this machine
    linux-plus-xk0-005/
        01_first_contact/
        02_system_report/
        ...
        _reference/
        _sandbox/                          # private homes for GUI terminals
    linux-plus-xk0-006/
        xk101_boot_fhs/
        ...
        xk503_network_security_triage/
        _reference/
        _sandbox/
    security-plus-sy0-701/                 # added exams get their own tree
```

The app first tries `workspace/` in the project. Filesystems such as CIFS/SMB
may silently discard `chmod` and SUID bits, so the platform probes the folder
and falls back to local disk when needed. `doctor` explains the choice.

Override the lab or use a different local filesystem:

```bash
python3 main.py --lab ~/study-lab doctor
STUDY_LAB=/srv/study-lab python3 main.py mission 11
```

`LINUXPLUS_LAB` is also accepted for backwards compatibility.

Use `ext4`, `xfs`, or `btrfs` for permission-heavy missions.

---

## Layout

```
main.py                         CLI, menus, lab, saves, exam commands
gui.py                          Tkinter lab and sandboxed terminal UI
study/
    exams.py                    exam manifests, discovery, pack loading
    objectives.py               PDF/DOCX/TXT extraction and indexing
    saves.py                    independent save slots and progress
    sandbox.py                  bubblewrap command construction and checks
    terminal.py                 PTY-backed persistent shell sessions
curriculum/
    syllabus.py                 built-in Linux+ module metadata
    lessons/                    sixteen Markdown lessons
    missions/                   missions, fixtures, checkers, solutions
exams/
    _inbox/                     drop CompTIA objectives here
    linux-plus-xk0-005/
        exam.json               exam manifest
        objectives/             optional source objectives
    linux-plus-xk0-006/
        exam.json               manifest with five official domains
        OBJECTIVES.md           objective-to-module map
        objectives/             official XK0-006 PDF and extracted text
        pack/
            syllabus.py         22-module source of truth
            lessons/            22 in-depth Markdown lessons
            missions/           fixtures, checkers, hints, solutions
saves/
    default.json                your progress (generated)
    active                      active save pointer
tests/
    test_missions.py            every XK0-005 reference solution passes
    test_platform.py            exams, objectives, and save-slot tests
    test_xk0_006.py             XK0-006 syllabus, lessons, and solutions
    test_sandbox.py             bubblewrap policy, isolation, PTY, Ctrl-C
    test_gui.py                 ANSI stripping and a GUI smoke test
```

Run the self-tests:

```bash
python3 -m unittest discover -s tests -v
```

---

## Safety notes

- **No root required.** Do not run the course with `sudo`.
- **Sandboxed fixtures.** Missions create fake system files inside the exam
  workspace; they do not edit `/etc/passwd`, `/etc/shadow`, or live units.
- **Sandboxed terminals.** Every GUI command runs inside bubblewrap with a
  read-only system, a private home and `/tmp`, no capabilities, and only the
  mission workspace writable. The project folder, save slots, and real home
  directory are not mounted. Network access is opt-in per new session.
- **Read-only audits** on the fixtures they are given.
- **Local network checks.** The port checker connects to sockets started by
  the mission on `127.0.0.1`; it does not scan external hosts.
- **Reset is scoped.** `reset` removes workspaces and progress for the active
  exam in the active save only. Other exams and saves are untouched.
- **Objectives documents may be copyrighted.** They are ignored by git and
  stored only in your local exam folder.

---

## Troubleshooting

**The lab cannot store permission bits.**
Use the automatic local-disk fallback, or point `LINUXPLUS_LAB` at a local
`ext4`/`xfs`/`btrfs` directory.

**PDF text extraction is missing.**
Install `poppler-utils` (`pdftotext`). `doctor` reports whether it is present.
DOCX, Markdown, text, and JSON extraction work without it.

**An exam is objectives-only.**
That is expected until a curriculum pack is built. Use `exam objectives` to
read the extracted documents, or switch to a complete Linux+ pack with
`exam use linux-plus-xk0-005` or `exam use linux-plus-xk0-006`.

**I want a fresh start for one exam.**
Switch to the exam and run `reset --yes`. Other exams in the same save keep
their progress.

**I want a completely separate run.**
Use `save new <name>` and `save use <name>`.

**The GUI will not open, or the Terminal tab says bubblewrap is missing.**
Run `python3 main.py gui --check`. The GUI needs Tkinter (`python3-tk`), an
X11/Wayland display, and `bubblewrap`. The CLI does not. If `bwrap` is
installed but the sandbox fails to start, unprivileged user namespaces may be
disabled on the host; enable them (`kernel.unprivileged_userns_clone=1` on
some distributions) or keep using the CLI.

**A full-screen program does not work in the terminal tab.**
That is expected: the terminal is line-oriented. Use the Files tab to edit
scripts, and non-interactive command flags for tools that prompt.

**The terminal's network commands fail.**
Sessions are network-isolated by default. Tick **Allow network (new sessions)**
and start a new terminal for missions that need DNS or a remote host. Loopback
always works.

**Progress looks stale.**
Check `save list` and `exam list`; the banner always shows the active save and
active exam.
