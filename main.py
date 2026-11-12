#!/usr/bin/env python3
"""Linux+ Python Lab — learn Python by doing real Linux work.

Run with no arguments for the interactive menu, or use a subcommand:

    python3 main.py list
    python3 main.py show 3
    python3 main.py mission 3
    python3 main.py verify 3

No third-party packages are required.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import pydoc
import shutil
import stat
import sys
import tempfile
import textwrap
from datetime import datetime
from pathlib import Path

from curriculum import (
    MODULES,
    get_module,
    get_mission,
    install_solution,
    lesson_path,
    total_minutes,
)

PROGRAM_DIR = Path(__file__).resolve().parent
DEFAULT_LAB = PROGRAM_DIR / "workspace"
APP_VERSION = "1.0.0"

# Set by init_lab().
LAB: Path | None = None
LAB_NOTE = ""
PROGRESS_FILE: Path | None = None

USE_COLOR = (
    sys.stdout.isatty()
    and os.environ.get("NO_COLOR") is None
    and os.environ.get("TERM") not in (None, "dumb")
)


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------
def paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def bold(text: str) -> str:
    return paint(text, "1")


def dim(text: str) -> str:
    return paint(text, "2")


def green(text: str) -> str:
    return paint(text, "32")


def red(text: str) -> str:
    return paint(text, "31")


def yellow(text: str) -> str:
    return paint(text, "33")


def cyan(text: str) -> str:
    return paint(text, "36")


def rule(char: str = "=", width: int = 72) -> str:
    return char * width


def banner() -> None:
    print()
    print(cyan("+" + "-" * 70 + "+"))
    print(cyan("|") + bold("  LINUX+ PYTHON LAB".ljust(70)) + cyan("|"))
    print(cyan("|") + "  Learn Python by doing real Linux work".ljust(70) + cyan("|"))
    print(cyan("|") + "  Aligned with CompTIA Linux+ XK0-005".ljust(70) + cyan("|"))
    print(cyan("+" + "-" * 70 + "+"))
    lab = init_lab()
    print(f"Lab:      {lab}")
    if LAB_NOTE:
        print(dim("          " + LAB_NOTE))
    progress = load_progress()
    done = len(progress["completed"])
    print(f"Progress: {progress_bar(done, len(MODULES))}  {done}/{len(MODULES)} missions")
    print()


def progress_bar(done: int, total: int, width: int = 20) -> str:
    filled = int(width * done / total) if total else 0
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}]"


def render_markdown(markdown: str) -> str:
    """Turn the lesson markdown into clean, pager-friendly plain text."""
    out: list[str] = []
    in_code = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            in_code = not in_code
            if in_code:
                out.append("")
            else:
                out.append("")
            continue
        if in_code:
            out.append("    " + line if line else "")
            continue
        if line.startswith("# "):
            title = line[2:].strip()
            out.append("")
            out.append(title.upper())
            out.append("=" * min(len(title), 72))
        elif line.startswith("## "):
            title = line[3:].strip()
            out.append("")
            out.append(title)
            out.append("-" * min(len(title), 72))
        elif line.startswith("### "):
            out.append("")
            out.append(line[4:].strip())
        elif line.strip() in ("---", "***"):
            out.append("-" * 72)
        else:
            line = line.replace("**", "").replace("`", "")
            out.append(line)
    return "\n".join(out).strip() + "\n"


def page(text: str) -> None:
    """Show long text through less/pydoc when interactive, else print."""
    if sys.stdout.isatty() and shutil.which("less"):
        pydoc.pager(text)
    else:
        print(text, end="" if text.endswith("\n") else "\n")


def pause() -> None:
    if sys.stdin.isatty():
        try:
            input(dim("\nPress Enter to continue..."))
        except (EOFError, KeyboardInterrupt):
            pass


# ---------------------------------------------------------------------------
# Lab and progress
# ---------------------------------------------------------------------------
def permissions_supported(directory: Path) -> tuple[bool, str]:
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"cannot create {directory}: {exc}"
    probe = directory / f".perm-probe-{os.getpid()}"
    try:
        probe.write_text("probe", encoding="utf-8")
        probe.chmod(0o600)
        if stat.S_IMODE(probe.stat().st_mode) != 0o600:
            return False, "chmod does not stick (network share such as CIFS?)"
        probe.chmod(0o4755)
        if stat.S_IMODE(probe.stat().st_mode) != 0o4755:
            return False, "SUID/SGID bits are not stored on this filesystem"
        return True, ""
    except OSError as exc:
        return False, str(exc)
    finally:
        try:
            probe.unlink()
        except OSError:
            pass


def init_lab(override: str | None = None) -> Path:
    global LAB, LAB_NOTE, PROGRESS_FILE
    if LAB is not None and not override:
        return LAB

    if override:
        candidate = Path(override).expanduser().resolve()
        ok, reason = permissions_supported(candidate)
        LAB = candidate
        LAB_NOTE = "" if ok else f"warning: {reason}; permission missions may not verify"
    elif os.environ.get("LINUXPLUS_LAB"):
        candidate = Path(os.environ["LINUXPLUS_LAB"]).expanduser().resolve()
        ok, reason = permissions_supported(candidate)
        LAB = candidate
        LAB_NOTE = "" if ok else f"warning: {reason}; permission missions may not verify"
    else:
        ok, reason = permissions_supported(DEFAULT_LAB)
        if ok:
            LAB = DEFAULT_LAB
            LAB_NOTE = ""
        else:
            fallback = Path.home() / ".local/share/linuxplus-python-lab"
            ok2, reason2 = permissions_supported(fallback)
            if not ok2:
                fallback = Path(tempfile.gettempdir()) / "linuxplus-python-lab"
                ok3, reason3 = permissions_supported(fallback)
                if not ok3:
                    raise SystemExit(
                        f"Cannot find a usable lab directory.\n"
                        f"  {DEFAULT_LAB}: {reason}\n"
                        f"  {fallback}: {reason3}\n"
                        "Set LINUXPLUS_LAB to a local ext4/xfs/btrfs directory."
                    )
            LAB = fallback
            LAB_NOTE = (
                "project folder cannot store Unix permission bits; "
                f"using local disk instead ({reason})"
            )

    assert LAB is not None
    LAB.mkdir(parents=True, exist_ok=True)
    preferred = PROGRAM_DIR / "progress.json"
    try:
        preferred.touch(exist_ok=True)
        PROGRESS_FILE = preferred
    except OSError:
        PROGRESS_FILE = LAB / "progress.json"
    return LAB


def load_progress() -> dict:
    init_lab()
    assert PROGRESS_FILE is not None
    if not PROGRESS_FILE.is_file():
        return {"completed": {}, "attempts": {}}
    try:
        data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"completed": {}, "attempts": {}}
    if not isinstance(data, dict):
        return {"completed": {}, "attempts": {}}
    data.setdefault("completed", {})
    data.setdefault("attempts", {})
    return data


def save_progress(progress: dict) -> None:
    assert PROGRESS_FILE is not None
    try:
        PROGRESS_FILE.write_text(
            json.dumps(progress, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        print(yellow(f"warning: could not save progress: {exc}"))


def mark_complete(mission_id: str) -> None:
    progress = load_progress()
    progress["completed"][mission_id] = {
        "at": datetime.now().isoformat(timespec="seconds")
    }
    save_progress(progress)


def record_attempt(mission_id: str) -> None:
    progress = load_progress()
    progress["attempts"][mission_id] = progress["attempts"].get(mission_id, 0) + 1
    save_progress(progress)


def is_complete(module: dict) -> bool:
    return module["id"] in load_progress()["completed"]


def next_module() -> dict | None:
    for module in MODULES:
        if not is_complete(module):
            return module
    return None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def resolve_module(key: str) -> dict:
    module = get_module(key)
    if module is None:
        raise SystemExit(
            f"Unknown module {key!r}. Try: python3 main.py list"
        )
    return module


def cmd_list(_args: argparse.Namespace) -> int:
    progress = load_progress()
    current_part = ""
    for module in MODULES:
        if module["part"] != current_part:
            current_part = module["part"]
            print()
            print(bold(current_part))
            print(rule("-", 72))
        status = green("[x]") if module["id"] in progress["completed"] else "[ ]"
        print(
            f" {status} {module['num']:>2}. {module['title']}"
        )
        print(
            dim(
                f"        {module['domain']} · {module['minutes']} min"
            )
        )
    done = len(progress["completed"])
    print()
    print(
        f"{progress_bar(done, len(MODULES))} {done}/{len(MODULES)} complete"
        f" · estimated {total_minutes() // 60} h {total_minutes() % 60} m total"
    )
    print(dim("Next: python3 main.py next   |   Read: python3 main.py show 1"))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    module = resolve_module(args.module)
    path = lesson_path(module)
    if not path.is_file():
        print(red(f"Lesson file missing: {path}"))
        return 1
    print()
    print(bold(f"Module {module['num']}: {module['title']}"))
    print(dim(f"{module['part']} · {module['domain']} · ~{module['minutes']} min"))
    print()
    page(render_markdown(path.read_text(encoding="utf-8")))
    mission = get_mission(module["id"])
    if mission is not None:
        print()
        print(dim(f"Hands-on task: {mission.title}"))
        print(dim(f"Run: python3 main.py mission {module['num']}"))
    return 0


def cmd_mission(args: argparse.Namespace) -> int:
    module = resolve_module(args.module)
    mission = get_mission(module["id"])
    if mission is None:
        print(red("No mission registered for this module."))
        return 1
    mdir = mission.prepare(init_lab())
    print()
    print(bold(f"MISSION {mission.num:02d} — {mission.title}"))
    print(dim(f"{module['domain']} · workspace: {mdir}"))
    print(rule("-", 72))
    print(render_markdown(mission.brief))
    print(dim("Hint: run `python3 main.py hint N` only after a real attempt."))
    print()
    return 0


def cmd_hint(args: argparse.Namespace) -> int:
    module = resolve_module(args.module)
    mission = get_mission(module["id"])
    if mission is None:
        print(red("No mission registered for this module."))
        return 1
    print()
    print(bold(f"Hints for mission {mission.num:02d} — {mission.title}"))
    print(dim("Stop after the first hint that unblocks you; struggle is the lesson."))
    print()
    for index, hint in enumerate(mission.hints, start=1):
        print(bold(f"{index}. ") + textwrap.fill(hint, width=70, subsequent_indent="   "))
        print()
    return 0


def _print_check(check: object, verbose: bool) -> None:
    ok = getattr(check, "ok", False)
    name = getattr(check, "name", "check")
    detail = getattr(check, "detail", "")
    marker = green("[PASS]") if ok else red("[FAIL]")
    print(f"  {marker} {name}")
    if detail and (verbose or not ok):
        for line in str(detail).splitlines():
            print(dim(f"         {line}"))


def cmd_verify(args: argparse.Namespace) -> int:
    module = resolve_module(args.module)
    mission = get_mission(module["id"])
    if mission is None:
        print(red("No mission registered for this module."))
        return 1
    lab = init_lab()
    mdir = mission.prepare(lab)
    print()
    print(bold(f"Verifying mission {mission.num:02d} — {mission.title}"))
    print(dim(f"Workspace: {mdir}"))
    print(rule("-", 72))
    checks = mission.run_checks(lab)
    for check in checks:
        _print_check(check, verbose=args.verbose)
    passed = all(getattr(check, "ok", False) for check in checks) and bool(checks)
    print(rule("-", 72))
    if passed:
        mark_complete(mission.id)
        progress = load_progress()
        done = len(progress["completed"])
        print(green(f"PASS — mission {mission.num:02d} complete!"))
        print(f"{progress_bar(done, len(MODULES))} {done}/{len(MODULES)} missions")
        upcoming = next_module()
        if upcoming is not None:
            print(dim(f"Next up: module {upcoming['num']} — {upcoming['title']}"))
        else:
            print(green("All 16 missions complete. You built a real Linux toolkit."))
        return 0

    record_attempt(mission.id)
    print(red("NOT YET — fix the failures above and run verify again."))
    print(dim(f"Stuck? python3 main.py hint {module['num']}"))
    return 1


def cmd_solution(args: argparse.Namespace) -> int:
    module = resolve_module(args.module)
    mission = get_mission(module["id"])
    if mission is None:
        print(red("No mission registered for this module."))
        return 1
    if args.write:
        destination = init_lab() / "_reference" / mission.dir_name
        written = install_solution(mission, destination)
        print(bold("Reference solution written:"))
        for path in written:
            print(f"  {path}")
        print(dim("This is a separate copy; your mission workspace was not changed."))
        return 0

    print()
    print(bold(f"Reference solution — mission {mission.num:02d}"))
    print(dim("Read it after your own attempt; then reproduce it from memory."))
    print()
    chunks = []
    for name, content in mission.solution.items():
        chunks.append(rule("=", 72))
        chunks.append(f"FILE: {name}")
        chunks.append(rule("=", 72))
        chunks.append(content.rstrip())
        chunks.append("")
    page("\n".join(chunks) + "\n")
    print(dim(f"Install a copy with: python3 main.py solution {module['num']} --write"))
    return 0


def cmd_progress(_args: argparse.Namespace) -> int:
    progress = load_progress()
    completed = progress["completed"]
    attempts = progress["attempts"]
    done = len(completed)
    print()
    print(bold("Progress report"))
    print(rule("-", 72))
    print(f"{progress_bar(done, len(MODULES))} {done}/{len(MODULES)} missions")
    print()
    for module in MODULES:
        mission_id = module["id"]
        status = green("done") if mission_id in completed else dim("todo")
        tries = attempts.get(mission_id, 0)
        tries_text = f"{tries} attempt{'s' if tries != 1 else ''}" if tries else ""
        print(f"  {module['num']:>2}. {status:<12} {module['title']}")
        if tries_text:
            print(dim(f"      {tries_text}"))
    print()
    if done == len(MODULES):
        print(green("Every mission is complete."))
    else:
        upcoming = next_module()
        assert upcoming is not None
        print(f"Next: module {upcoming['num']} — {upcoming['title']}")
        print(dim(f"  python3 main.py mission {upcoming['num']}"))
    return 0


def cmd_next(_args: argparse.Namespace) -> int:
    module = next_module()
    if module is None:
        print(green("All missions complete — nothing left to verify."))
        return 0
    if sys.stdin.isatty():
        return module_menu(module)
    print(f"Next: module {module['num']} — {module['title']}")
    print(f"  python3 main.py mission {module['num']}")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    lab = init_lab()
    if args.module:
        module = resolve_module(args.module)
        mission = get_mission(module["id"])
        assert mission is not None
        target = lab / mission.dir_name
        if not args.yes:
            answer = input(
                f"Delete {target} and clear mission {module['num']} progress? [y/N] "
            ).strip().lower()
            if answer not in ("y", "yes"):
                print("Cancelled.")
                return 0
        shutil.rmtree(target, ignore_errors=True)
        progress = load_progress()
        progress["completed"].pop(module["id"], None)
        progress["attempts"].pop(module["id"], None)
        save_progress(progress)
        print(f"Reset mission {module['num']}. Run `python3 main.py mission {module['num']}` to recreate fixtures.")
        return 0

    if not args.yes:
        answer = input(
            "Delete ALL mission workspaces and progress? This cannot be undone. [y/N] "
        ).strip().lower()
        if answer not in ("y", "yes"):
            print("Cancelled.")
            return 0
    for module in MODULES:
        mission = get_mission(module["id"])
        if mission is not None:
            shutil.rmtree(lab / mission.dir_name, ignore_errors=True)
    shutil.rmtree(lab / "_reference", ignore_errors=True)
    save_progress({"completed": {}, "attempts": {}})
    print("All labs reset. Lessons are untouched.")
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    lab = init_lab()
    print()
    print(bold("Environment check"))
    print(rule("-", 72))
    checks: list[tuple[bool, str]] = []

    version = sys.version_info
    checks.append(
        (
            version >= (3, 10),
            f"Python {version.major}.{version.minor}.{version.micro} "
            + ("(3.10+ required)" if version < (3, 10) else "(ok)"),
        )
    )
    checks.append((True, f"Program: {PROGRAM_DIR}"))
    checks.append((True, f"Lab: {lab}"))
    if LAB_NOTE:
        checks.append((False, f"Lab note: {LAB_NOTE}"))
    ok, reason = permissions_supported(lab)
    checks.append(
        (
            ok,
            "Lab supports Unix permissions/SUID"
            + ("" if ok else f": {reason}"),
        )
    )
    checks.append((True, f"Progress file: {PROGRESS_FILE}"))

    modules = [
        "argparse",
        "configparser",
        "csv",
        "json",
        "logging",
        "os",
        "pathlib",
        "re",
        "shutil",
        "socket",
        "stat",
        "subprocess",
        "tarfile",
        "unittest",
    ]
    missing = []
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception:
            missing.append(name)
    checks.append(
        (
            not missing,
            "All required standard-library modules import"
            + (f" (missing: {', '.join(missing)})" if missing else ""),
        )
    )

    for tool in ("sh", "git", "tar", "ss", "ip", "systemctl", "less", "nano"):
        found = shutil.which(tool)
        checks.append(
            (
                found is not None,
                f"{tool}: {found}" if found else f"{tool}: not installed (optional)",
            )
        )

    try:
        usage = shutil.disk_usage(lab)
        checks.append(
            (
                usage.free > 200 * 1024 * 1024,
                f"Free space in lab: {usage.free / 1024**3:.1f} GiB",
            )
        )
    except OSError as exc:
        checks.append((False, f"Could not read disk usage: {exc}"))

    checks.append((len(MODULES) == 16, f"Curriculum modules: {len(MODULES)}"))
    missing_lessons = [
        module["lesson"] for module in MODULES if not lesson_path(module).is_file()
    ]
    checks.append(
        (
            not missing_lessons,
            "All lesson files present"
            + (f" (missing: {', '.join(missing_lessons)})" if missing_lessons else ""),
        )
    )

    hard_failures = 0
    for ok, message in checks:
        if message.startswith("Lab note:"):
            print(f"  {dim('[note]')} {message}")
            continue
        marker = green("[ok]") if ok else yellow("[!!]")
        if not ok and (
            "required" in message
            or "Lab supports" in message
            or "lesson files" in message
            or "standard-library" in message
        ):
            hard_failures += 1
        print(f"  {marker} {message}")

    print(rule("-", 72))
    if hard_failures:
        print(yellow("Some checks need attention. See the README troubleshooting section."))
        return 1
    print(green("Environment looks good. Start with: python3 main.py next"))
    return 0


# ---------------------------------------------------------------------------
# Interactive menus
# ---------------------------------------------------------------------------
def module_menu(module: dict) -> int:
    mission = get_mission(module["id"])
    if mission is None:
        print(red("No mission registered."))
        return 1
    while True:
        print()
        print(bold(f"Module {module['num']}: {module['title']}"))
        print(dim(f"{module['part']} · {module['domain']} · ~{module['minutes']} min"))
        status = green("complete") if is_complete(module) else yellow("not verified")
        print(f"Status: {status}")
        print()
        print("  [r] Read the lesson")
        print("  [m] Mission brief and workspace path")
        print("  [v] Verify the mission")
        print("  [h] Hints")
        print("  [s] Reference solution")
        print("  [b] Back")
        try:
            choice = input(bold("Choose> ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice in ("r", "read"):
            cmd_show(argparse.Namespace(module=str(module["num"])))
        elif choice in ("m", "mission", "brief"):
            cmd_mission(argparse.Namespace(module=str(module["num"])))
        elif choice in ("v", "verify"):
            passed = cmd_verify(
                argparse.Namespace(module=str(module["num"]), verbose=False)
            )
            if passed == 0 and is_complete(module):
                nxt = next_module()
                if nxt is not None:
                    try:
                        answer = input(
                            dim(f"Open next module {nxt['num']}? [Y/n] ")
                        ).strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        return 0
                    if answer in ("", "y", "yes"):
                        return module_menu(nxt)
        elif choice in ("h", "hint", "hints"):
            cmd_hint(argparse.Namespace(module=str(module["num"])))
        elif choice in ("s", "solution"):
            cmd_solution(
                argparse.Namespace(module=str(module["num"]), write=False)
            )
        elif choice in ("b", "back", "q", ""):
            return 0


def menu() -> int:
    init_lab()
    while True:
        banner()
        done = len(load_progress()["completed"])
        upcoming = next_module()
        if upcoming is not None:
            print(f"Next mission: module {upcoming['num']} — {upcoming['title']}")
        else:
            print(green("All missions complete. Review anything you like."))
        print()
        print("  1. Continue / next mission")
        print("  2. Browse lessons")
        print("  3. Mission board")
        print("  4. Progress report")
        print("  5. Reference solution")
        print("  6. How this works")
        print("  7. Environment check (doctor)")
        print("  q. Quit")
        try:
            choice = input(bold("Select> ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if choice in ("q", "quit", "exit"):
            return 0
        if choice in ("1", "c", "continue", "next"):
            if upcoming is None:
                cmd_progress(argparse.Namespace())
            else:
                module_menu(upcoming)
        elif choice == "2":
            cmd_list(argparse.Namespace())
            try:
                key = input(bold("\nModule number (Enter to go back): ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                continue
            if key:
                module = get_module(key)
                if module is None:
                    print(red("No such module."))
                else:
                    module_menu(module)
        elif choice == "3":
            cmd_list(argparse.Namespace())
            try:
                key = input(bold("\nMission number to open (Enter to go back): ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                continue
            if key:
                module = get_module(key)
                if module is None:
                    print(red("No such mission."))
                else:
                    cmd_mission(argparse.Namespace(module=str(module["num"])))
                    module_menu(module)
        elif choice in ("4", "p", "progress"):
            cmd_progress(argparse.Namespace())
            pause()
        elif choice == "5":
            try:
                key = input(bold("Mission number for its reference solution: ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                continue
            if key:
                module = get_module(key)
                if module is None:
                    print(red("No such mission."))
                else:
                    cmd_solution(argparse.Namespace(module=str(module["num"]), write=False))
                    pause()
        elif choice == "6":
            show_how_it_works()
            pause()
        elif choice == "7":
            cmd_doctor(argparse.Namespace())
            pause()
        elif choice:
            module = get_module(choice)
            if module is not None:
                module_menu(module)


def show_how_it_works() -> None:
    text = f"""\
{bold("How this lab works")}

Each of the {len(MODULES)} modules has three parts:

  1. A written lesson (concepts, commands, examples, common mistakes).
  2. A mission: a task you complete with your real editor, shell, and Python.
  3. A verifier that inspects the actual result — files, permissions,
     command output, exit codes — not a multiple-choice answer.

Recommended loop:

  python3 main.py show N        # read the lesson
  python3 main.py mission N     # read the task and find your workspace
  ... do the work in a terminal/editor ...
  python3 main.py verify N      # let the checker inspect the real result
  python3 main.py hint N        # only if you are genuinely stuck
  python3 main.py solution N    # compare after your attempt

Your lab is:

  {init_lab()}

All mission files live there. You can open a second terminal and work in it
with normal Linux tools: ls, chmod, grep, ss, systemctl, tar, less, vim/nano.
Nothing in the missions requires root.

Why not put the lab inside this program folder?
{("  " + LAB_NOTE) if LAB_NOTE else "  A local ext4/xfs/btrfs folder is used so permissions and SUID are real."}

Progress is stored in {PROGRESS_FILE}. It is plain JSON — back it up if you
want to move machines.

Commands:
  list, show N, mission N, verify N, hint N, solution N [--write],
  progress, next, reset [N], doctor
"""
    page(text)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="linuxplus-python-lab",
        description=(
            "Learn Python through CompTIA Linux+ style missions. "
            "Run with no arguments for the interactive menu."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 main.py                 interactive menu\n"
            "  python3 main.py list            see all 16 modules\n"
            "  python3 main.py show 4          read module 4's lesson\n"
            "  python3 main.py mission 4       show the hands-on task\n"
            "  python3 main.py verify 4        run the real checks\n"
            "  python3 main.py solution 4      view the reference solution\n"
            "  python3 main.py doctor          check your environment\n"
        ),
    )
    parser.add_argument(
        "--lab",
        metavar="DIR",
        help="override the lab workspace directory (default: auto-detected)",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {APP_VERSION}"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="list every module and its status")

    show = sub.add_parser("show", help="read a module's lesson")
    show.add_argument("module", help="module number or id (e.g. 3 or m03)")

    mission = sub.add_parser("mission", help="show a mission brief and workspace")
    mission.add_argument("module")

    verify = sub.add_parser("verify", help="verify a completed mission")
    verify.add_argument("module")
    verify.add_argument(
        "-v", "--verbose", action="store_true", help="show details for passing checks too"
    )

    hint = sub.add_parser("hint", help="show hints for a mission")
    hint.add_argument("module")

    solution = sub.add_parser("solution", help="show or install a reference solution")
    solution.add_argument("module")
    solution.add_argument(
        "--write",
        action="store_true",
        help="write a copy under <lab>/_reference/ instead of paging it",
    )

    sub.add_parser("progress", help="show a detailed progress report")
    sub.add_parser("next", help="open the next incomplete module")
    sub.add_parser("doctor", help="check Python, lab, tools, and files")

    reset = sub.add_parser("reset", help="delete a mission workspace and its progress")
    reset.add_argument("module", nargs="?", help="module number (omit to reset everything)")
    reset.add_argument("--yes", action="store_true", help="do not ask for confirmation")

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    init_lab(args.lab)

    commands = {
        "list": cmd_list,
        "show": cmd_show,
        "mission": cmd_mission,
        "verify": cmd_verify,
        "hint": cmd_hint,
        "solution": cmd_solution,
        "progress": cmd_progress,
        "next": cmd_next,
        "doctor": cmd_doctor,
        "reset": cmd_reset,
    }
    if args.command is None:
        if sys.stdin.isatty():
            return menu()
        parser.print_help()
        return 0
    return commands[args.command](args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
