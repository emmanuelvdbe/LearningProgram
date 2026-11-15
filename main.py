#!/usr/bin/env python3
"""CompTIA Study Lab — hands-on exam preparation with multiple save slots.

Run with no arguments for the interactive menu, or use a subcommand:

    python3 main.py list
    python3 main.py exam list
    python3 main.py save list
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

from study import (
    EXAMS_DIR,
    INBOX_DIR,
    Exam,
    attach_objective,
    clean_text,
    create_exam,
    get_exam,
    load_exams,
    read_objective_text,
    resolve_exam,
    scan_objectives,
    saves,
)
from study import saves as savefiles

PROGRAM_DIR = Path(__file__).resolve().parent
DEFAULT_LAB = PROGRAM_DIR / "workspace"
APP_VERSION = "2.0.0"

# Set by init_lab() / init_state().
LAB: Path | None = None
LAB_NOTE = ""
SAVE_DIR: Path | None = None
SAVE: dict | None = None
SAVE_NAME = ""
EXAMS: list[Exam] = []
ACTIVE_EXAM: Exam | None = None

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
    init_state()
    assert ACTIVE_EXAM is not None
    print()
    print(cyan("+" + "-" * 70 + "+"))
    print(cyan("|") + bold("  COMPTIA STUDY LAB".ljust(70)) + cyan("|"))
    print(cyan("|") + "  Learn by doing real, verifiable work".ljust(70) + cyan("|"))
    print(cyan("|") + f"  {ACTIVE_EXAM.name}".ljust(70) + cyan("|"))
    print(cyan("+" + "-" * 70 + "+"))
    lab = init_lab()
    print(f"Exam:     {ACTIVE_EXAM.name} ({ACTIVE_EXAM.code or ACTIVE_EXAM.id})")
    print(f"Save:     {SAVE_NAME}   ·   Lab: {lab}")
    if LAB_NOTE:
        print(dim("          " + LAB_NOTE))
    modules = current_modules()
    if modules:
        progress = load_progress()
        done = len(progress["completed"])
        print(
            f"Progress: {progress_bar(done, len(modules))}  "
            f"{done}/{len(modules)} missions"
        )
    else:
        count = len(ACTIVE_EXAM.objective_files())
        print(
            yellow("No curriculum pack yet")
            + f" · {count} objectives document"
            + ("s" if count != 1 else "")
            + " found"
        )
        print(dim(f"          Drop objectives in {INBOX_DIR}"))
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
    global LAB, LAB_NOTE
    if LAB is not None and not override:
        return LAB

    if override:
        candidate = Path(override).expanduser().resolve()
        ok, reason = permissions_supported(candidate)
        LAB = candidate
        LAB_NOTE = "" if ok else f"warning: {reason}; permission missions may not verify"
    elif os.environ.get("STUDY_LAB") or os.environ.get("LINUXPLUS_LAB"):
        candidate = Path(
            os.environ.get("STUDY_LAB") or os.environ["LINUXPLUS_LAB"]
        ).expanduser().resolve()
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
    return LAB


# ---------------------------------------------------------------------------
# Exams, save slots, and progress
# ---------------------------------------------------------------------------
def refresh_exams() -> list[Exam]:
    global EXAMS
    EXAMS = load_exams()
    return EXAMS


def default_exam() -> Exam:
    refresh_exams()
    for exam in EXAMS:
        if exam.id == "linux-plus-xk0-005":
            return exam
    if not EXAMS:
        raise SystemExit(
            f"No exams found. Add a manifest under {EXAMS_DIR}/<exam-id>/exam.json."
        )
    return EXAMS[0]


def save_directory() -> Path:
    init_lab()
    assert LAB is not None
    preferred = PROGRAM_DIR / "saves"
    fallback = LAB / "saves"
    return saves.ensure_directory(preferred, fallback)


def _migrate_legacy_progress() -> None:
    """Import the old single-course progress.json into the Linux+ save."""
    assert SAVE is not None
    if "progress.json" in SAVE.get("migrations", []):
        return
    legacy = PROGRAM_DIR / "progress.json"
    if not legacy.is_file():
        return
    try:
        old = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        old = {}
    if not isinstance(old, dict):
        old = {}
    completed = old.get("completed") if isinstance(old.get("completed"), dict) else {}
    attempts = old.get("attempts") if isinstance(old.get("attempts"), dict) else {}
    if completed or attempts:
        target = savefiles.exam_progress(SAVE, "linux-plus-xk0-005")
        if not target["completed"] and not target["attempts"]:
            target["completed"] = completed
            target["attempts"] = attempts
    SAVE.setdefault("migrations", []).append("progress.json")
    if SAVE_DIR is not None:
        savefiles.write_save(SAVE_DIR, SAVE_NAME, SAVE)


def _migrate_legacy_lab() -> None:
    """Move pre-2.0 mission folders under the Linux+ exam namespace."""
    if LAB is None:
        return
    target = LAB / "linux-plus-xk0-005"
    names: list[str] = []
    try:
        from curriculum.missions import MISSIONS

        names = [mission.dir_name for mission in MISSIONS]
    except ImportError:
        names = []
    if not names:
        return
    names.append("_reference")
    for name in names:
        source = LAB / name
        destination = target / name
        if source.is_dir() and not destination.exists():
            target.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(source), str(destination))
            except OSError:
                pass


def init_state() -> None:
    """Load exams and the active save slot (idempotent)."""
    global SAVE_DIR, SAVE, SAVE_NAME, ACTIVE_EXAM
    if SAVE is not None and ACTIVE_EXAM is not None:
        return

    init_lab()
    refresh_exams()
    SAVE_DIR = save_directory()
    SAVE_NAME = savefiles.active_name(SAVE_DIR)
    SAVE = savefiles.load_save(SAVE_DIR, SAVE_NAME)
    _migrate_legacy_progress()

    selected = SAVE.get("active_exam", "")
    exam = get_exam(selected, EXAMS) if selected else None
    if exam is None:
        exam = default_exam()
        SAVE["active_exam"] = exam.id
        savefiles.write_save(SAVE_DIR, SAVE_NAME, SAVE)
    ACTIVE_EXAM = exam
    _migrate_legacy_lab()


def current_modules() -> list[dict]:
    init_state()
    assert ACTIVE_EXAM is not None
    return ACTIVE_EXAM.modules()


def current_mission(key: str | int):
    init_state()
    assert ACTIVE_EXAM is not None
    return ACTIVE_EXAM.get_mission(key)


def current_lesson_path(module: dict) -> Path:
    init_state()
    assert ACTIVE_EXAM is not None
    return ACTIVE_EXAM.lesson_path(module)


def exam_lab() -> Path:
    """Workspace root for the active exam."""
    init_state()
    assert ACTIVE_EXAM is not None
    root = init_lab() / ACTIVE_EXAM.id
    root.mkdir(parents=True, exist_ok=True)
    return root


def load_progress() -> dict:
    init_state()
    assert SAVE is not None and ACTIVE_EXAM is not None
    return savefiles.exam_progress(SAVE, ACTIVE_EXAM.id)


def save_progress(progress: dict) -> None:
    init_state()
    assert SAVE is not None and ACTIVE_EXAM is not None and SAVE_DIR is not None
    SAVE["progress"][ACTIVE_EXAM.id] = progress
    try:
        savefiles.write_save(SAVE_DIR, SAVE_NAME, SAVE)
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
    for module in current_modules():
        if not is_complete(module):
            return module
    return None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def resolve_module(key: str) -> dict:
    init_state()
    assert ACTIVE_EXAM is not None
    module = ACTIVE_EXAM.get_module(key)
    if module is None:
        if not ACTIVE_EXAM.has_curriculum:
            raise SystemExit(
                f"{ACTIVE_EXAM.name} has no curriculum pack yet.\n"
                f"  Objectives: {ACTIVE_EXAM.objectives_dir}\n"
                f"  Build or attach a pack, or switch exams with: "
                f"python3 main.py exam use <id>"
            )
        raise SystemExit(
            f"Unknown module {key!r} for {ACTIVE_EXAM.short_name}. "
            "Try: python3 main.py list"
        )
    return module


def cmd_list(_args: argparse.Namespace) -> int:
    init_state()
    assert ACTIVE_EXAM is not None
    progress = load_progress()
    modules = current_modules()

    print()
    print(bold(f"{ACTIVE_EXAM.name}"))
    print(dim(
        f"Exam {ACTIVE_EXAM.code or ACTIVE_EXAM.id} · save {SAVE_NAME} · "
        f"{ACTIVE_EXAM.summary()}"
    ))
    if not modules:
        print()
        print(yellow("No curriculum pack has been built for this exam yet."))
        print(f"Objectives folder: {ACTIVE_EXAM.objectives_dir}")
        files = ACTIVE_EXAM.objective_files()
        if files:
            print("Documents found:")
            for path in files:
                print(f"  - {path.name}")
        else:
            print(f"Drop the official objectives in: {INBOX_DIR}")
        print()
        print("Next steps:")
        print("  python3 main.py exam scan          # extract readable text")
        print("  python3 main.py exam objectives    # read them here")
        print("  python3 main.py exam list          # switch to a ready exam")
        return 0

    current_part = ""
    for module in modules:
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
    total = len(modules)
    minutes = ACTIVE_EXAM.total_minutes()
    print()
    print(
        f"{progress_bar(done, total)} {done}/{total} complete"
        f" · estimated {minutes // 60} h {minutes % 60} m total"
    )
    print(dim("Next: python3 main.py next   |   Read: python3 main.py show 1"))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    module = resolve_module(args.module)
    path = current_lesson_path(module)
    if not path.is_file():
        print(red(f"Lesson file missing: {path}"))
        return 1
    print()
    print(bold(f"Module {module['num']}: {module['title']}"))
    print(dim(f"{module['part']} · {module['domain']} · ~{module['minutes']} min"))
    print()
    page(render_markdown(path.read_text(encoding="utf-8")))
    mission = current_mission(module["id"])
    if mission is not None:
        print()
        print(dim(f"Hands-on task: {mission.title}"))
        print(dim(f"Run: python3 main.py mission {module['num']}"))
    return 0


def cmd_mission(args: argparse.Namespace) -> int:
    module = resolve_module(args.module)
    mission = current_mission(module["id"])
    if mission is None:
        print(red("No mission registered for this module."))
        return 1
    mdir = mission.prepare(exam_lab())
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
    mission = current_mission(module["id"])
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
    mission = current_mission(module["id"])
    if mission is None:
        print(red("No mission registered for this module."))
        return 1
    lab = exam_lab()
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
        total = len(current_modules())
        done = len(progress["completed"])
        print(green(f"PASS — mission {mission.num:02d} complete!"))
        print(f"{progress_bar(done, total)} {done}/{total} missions")
        upcoming = next_module()
        if upcoming is not None:
            print(dim(f"Next up: module {upcoming['num']} — {upcoming['title']}"))
        else:
            print(green(f"All {total} missions complete. You built a real toolkit."))
        return 0

    record_attempt(mission.id)
    print(red("NOT YET — fix the failures above and run verify again."))
    print(dim(f"Stuck? python3 main.py hint {module['num']}"))
    return 1


def cmd_solution(args: argparse.Namespace) -> int:
    module = resolve_module(args.module)
    mission = current_mission(module["id"])
    if mission is None:
        print(red("No mission registered for this module."))
        return 1
    if args.write:
        destination = exam_lab() / "_reference" / mission.dir_name
        written = ACTIVE_EXAM.install_solution(mission, destination)
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
    init_state()
    assert ACTIVE_EXAM is not None
    modules = current_modules()
    progress = load_progress()
    completed = progress["completed"]
    attempts = progress["attempts"]
    done = len(completed)
    print()
    print(bold("Progress report"))
    print(dim(f"{ACTIVE_EXAM.name} · save {SAVE_NAME}"))
    print(rule("-", 72))
    if not modules:
        print(yellow("This exam has no curriculum pack yet."))
        print(f"Objectives: {ACTIVE_EXAM.objectives_dir}")
        return 0
    print(f"{progress_bar(done, len(modules))} {done}/{len(modules)} missions")
    print()
    for module in modules:
        mission_id = module["id"]
        status = green("done") if mission_id in completed else dim("todo")
        tries = attempts.get(mission_id, 0)
        tries_text = f"{tries} attempt{'s' if tries != 1 else ''}" if tries else ""
        print(f"  {module['num']:>2}. {status:<12} {module['title']}")
        if tries_text:
            print(dim(f"      {tries_text}"))
    print()
    if done == len(modules):
        print(green("Every mission is complete."))
    else:
        upcoming = next_module()
        assert upcoming is not None
        print(f"Next: module {upcoming['num']} — {upcoming['title']}")
        print(dim(f"  python3 main.py mission {upcoming['num']}"))
    return 0


def cmd_next(_args: argparse.Namespace) -> int:
    init_state()
    if not current_modules():
        assert ACTIVE_EXAM is not None
        print(yellow(f"{ACTIVE_EXAM.name} has no curriculum pack yet."))
        print(f"Objectives: {ACTIVE_EXAM.objectives_dir}")
        print("Try: python3 main.py exam objectives")
        print("Or switch exams: python3 main.py exam use linux-plus-xk0-005")
        return 0
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
    lab = exam_lab()
    if args.module:
        module = resolve_module(args.module)
        mission = current_mission(module["id"])
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
            f"Delete ALL {ACTIVE_EXAM.short_name} workspaces and progress in this save? "
            "This cannot be undone. [y/N] "
        ).strip().lower()
        if answer not in ("y", "yes"):
            print("Cancelled.")
            return 0
    for module in current_modules():
        mission = current_mission(module["id"])
        if mission is not None:
            shutil.rmtree(lab / mission.dir_name, ignore_errors=True)
    shutil.rmtree(lab / "_reference", ignore_errors=True)
    save_progress({"completed": {}, "attempts": {}})
    print(f"{ACTIVE_EXAM.short_name} labs reset. Lessons and other exams are untouched.")
    return 0


def _resolve_exam_arg(key: str | None) -> Exam:
    init_state()
    if not key:
        assert ACTIVE_EXAM is not None
        return ACTIVE_EXAM
    try:
        return resolve_exam(key, EXAMS)
    except ValueError as exc:
        raise SystemExit(str(exc))


def _activate_exam(exam: Exam) -> None:
    global ACTIVE_EXAM
    assert SAVE is not None and SAVE_DIR is not None
    ACTIVE_EXAM = exam
    SAVE["active_exam"] = exam.id
    savefiles.write_save(SAVE_DIR, SAVE_NAME, SAVE)


def _activate_save(name: str) -> None:
    global SAVE, SAVE_NAME, ACTIVE_EXAM
    init_state()
    assert SAVE_DIR is not None
    name = savefiles.normalize_name(name)
    path = savefiles.save_path(SAVE_DIR, name)
    if not path.is_file():
        raise FileNotFoundError(f"Save {name!r} does not exist.")
    data = savefiles.load_save(SAVE_DIR, name)
    savefiles.set_active_name(SAVE_DIR, name)
    SAVE = data
    SAVE_NAME = name
    selected = data.get("active_exam", "")
    exam = get_exam(selected, EXAMS) if selected else None
    if exam is None:
        exam = default_exam()
        data["active_exam"] = exam.id
        savefiles.write_save(SAVE_DIR, name, data)
    ACTIVE_EXAM = exam


def cmd_exam(args: argparse.Namespace) -> int:
    action = args.exam_action
    if action == "list":
        return _exam_list()
    if action == "use":
        exam = _resolve_exam_arg(args.exam_id)
        _activate_exam(exam)
        print(green(f"Active exam: {exam.name}"))
        print(f"  Save: {SAVE_NAME}")
        print(f"  Curriculum: {exam.summary()}")
        print(f"  Workspace: {exam_lab()}")
        if not exam.has_curriculum:
            print(dim(f"  Objectives: {exam.objectives_dir}"))
        return 0
    if action == "info":
        exam = _resolve_exam_arg(args.exam_id)
        return _exam_info(exam)
    if action == "add":
        try:
            exam = create_exam(
                args.exam_id,
                args.name,
                code=args.code or "",
                description=args.description or "",
                short_name=args.short_name or "",
            )
        except (ValueError, FileExistsError) as exc:
            print(red(str(exc)))
            return 1
        refresh_exams()
        print(green(f"Created exam: {exam.name}"))
        print(f"  Manifest: {exam.manifest_path}")
        print(f"  Objectives: {exam.objectives_dir}")
        print()
        print("Next:")
        print(f"  python3 main.py exam attach {exam.id} path/to/objectives.pdf")
        print(f"  python3 main.py exam scan {exam.id}")
        if args.use:
            _activate_exam(exam)
            print(green(f"Active exam is now {exam.short_name}."))
        return 0
    if action == "attach":
        exam = _resolve_exam_arg(args.exam_id)
        try:
            destination = attach_objective(exam, Path(args.source))
        except (OSError, FileNotFoundError) as exc:
            print(red(str(exc)))
            return 1
        print(green(f"Attached to {exam.short_name}: {destination}"))
        print(dim(f"Now run: python3 main.py exam scan {exam.id}"))
        return 0
    if action == "scan":
        exam = _resolve_exam_arg(args.exam_id)
        return _exam_scan(exam)
    if action == "objectives":
        exam = _resolve_exam_arg(args.exam_id)
        return _exam_objectives(exam)
    print(red(f"Unknown exam action: {action}"))
    return 1


def _exam_list() -> int:
    init_state()
    assert SAVE is not None
    print()
    print(bold("Available exams"))
    print(dim(f"Save slot: {SAVE_NAME} · {SAVE_DIR}"))
    print(rule("-", 72))
    for exam in EXAMS:
        marker = green("*") if ACTIVE_EXAM and exam.id == ACTIVE_EXAM.id else " "
        modules = exam.modules()
        if modules:
            done = savefiles.completed_count(SAVE, exam.id)
            status = f"{done}/{len(modules)} missions in this save"
        else:
            count = len(exam.objective_files())
            status = (
                f"objectives only · {count} document"
                + ("s" if count != 1 else "")
            )
        print(f" {marker} {exam.id}")
        print(f"   {exam.name} [{exam.code or 'no code'}]")
        print(dim(f"   {status}"))
    print()
    print(dim("Use: python3 main.py exam use <id>"))
    print(dim("Add: python3 main.py exam add <id> --name \"CompTIA ...\""))
    return 0


def _exam_info(exam: Exam) -> int:
    print()
    print(bold(exam.name))
    print(rule("-", 72))
    print(f"ID:          {exam.id}")
    print(f"Code:        {exam.code or '(none)'}")
    print(f"Status:      {exam.status}")
    print(f"Curriculum:  {exam.curriculum or 'not built yet'}")
    print(f"Description: {exam.description}")
    print(f"Folder:      {exam.path}")
    print(f"Objectives:  {exam.objectives_dir}")
    modules = exam.modules()
    if modules:
        minutes = exam.total_minutes()
        print(f"Modules:     {len(modules)} · {minutes // 60} h {minutes % 60} m")
        if SAVE is not None:
            done = savefiles.completed_count(SAVE, exam.id)
            print(f"Progress:    {done}/{len(modules)} in save {SAVE_NAME}")
    else:
        print("Modules:     none yet")
    files = exam.objective_files()
    print(f"Documents:   {len(files)}")
    for path in files:
        try:
            size = path.stat().st_size
            print(f"  - {path.relative_to(exam.path)} ({size:,} bytes)")
        except OSError:
            print(f"  - {path.name}")
    if exam.domains:
        print("Domains:")
        for domain in exam.domains:
            print(f"  - {domain}")
    return 0


def _exam_scan(exam: Exam) -> int:
    print()
    print(bold(f"Scanning objectives — {exam.name}"))
    print(rule("-", 72))
    total = 0
    failures = 0
    for directory, label in ((INBOX_DIR, "inbox"), (exam.objectives_dir, "exam")):
        if not directory.is_dir():
            continue
        results = scan_objectives(directory)
        if results:
            print(f"{label}: {directory}")
        for result in results:
            total += 1
            source = result.source.name
            if result.status == "extracted":
                print(green(f"  [ok]   {source}") + dim(f" · {result.chars:,} chars"))
            else:
                failures += 1
                print(yellow(f"  [warn] {source}") + f" · {result.status}")
                if result.error:
                    print(dim(f"         {result.error}"))
    print(rule("-", 72))
    if total == 0:
        print(yellow("No objective documents found."))
        print(f"Drop PDF/DOCX/TXT files in: {INBOX_DIR}")
        return 0
    print(f"Scanned {total} document{'s' if total != 1 else ''} · {failures} warning"
          + ("s" if failures != 1 else ""))
    print(f"Extracted text: {exam.objectives_dir / '_text'}")
    print(dim("Read with: python3 main.py exam objectives"))
    return 0


def _exam_objectives(exam: Exam) -> int:
    chunks = read_objective_text(exam.objectives_dir)
    if not chunks:
        files = exam.objective_files()
        print(yellow(f"No readable objectives found for {exam.short_name}."))
        print(f"Objectives folder: {exam.objectives_dir}")
        if files:
            print("Documents present:")
            for path in files:
                print(f"  - {path.name}")
            print("Run: python3 main.py exam scan")
            print("PDF extraction needs pdftotext (poppler-utils).")
        else:
            print(f"Drop the official objectives in: {INBOX_DIR}")
            print("Then: python3 main.py exam attach <exam-id> <file>")
        return 0

    print()
    print(bold(f"Objectives — {exam.name}"))
    print(rule("=", 72))
    output: list[str] = []
    for name, text in chunks:
        output.append("")
        output.append(bold(name))
        output.append(rule("-", 72))
        output.append(clean_text(text))
        output.append("")
    page("\n".join(output) + "\n")
    return 0


def cmd_save(args: argparse.Namespace) -> int:
    action = args.save_action
    if action == "list":
        return _save_list()
    if action == "new":
        try:
            data = savefiles.create_save(SAVE_DIR, args.name, ACTIVE_EXAM.id)
        except (ValueError, FileExistsError, OSError) as exc:
            print(red(str(exc)))
            return 1
        print(green(f"Created save slot: {data['name']}"))
        print(f"  Path: {savefiles.save_path(SAVE_DIR, data['name'])}")
        print(f"  Active exam: {ACTIVE_EXAM.name}")
        print(dim(f"Switch with: python3 main.py save use {data['name']}"))
        return 0
    if action == "use":
        try:
            _activate_save(args.name)
        except (ValueError, FileNotFoundError, OSError) as exc:
            print(red(str(exc)))
            return 1
        print(green(f"Active save: {SAVE_NAME}"))
        print(f"  Exam: {ACTIVE_EXAM.name} ({ACTIVE_EXAM.summary()})")
        return 0
    if action == "show":
        name = args.name or SAVE_NAME
        try:
            data = savefiles.load_save(SAVE_DIR, name)
        except (ValueError, OSError) as exc:
            print(red(str(exc)))
            return 1
        return _save_info(data)
    if action == "delete":
        names = savefiles.list_save_names(SAVE_DIR)
        if len(names) <= 1:
            print(red("Cannot delete the only save slot."))
            return 1
        name = savefiles.normalize_name(args.name)
        if name not in names:
            print(red(f"Save {name!r} does not exist."))
            return 1
        if not args.yes:
            answer = input(f"Delete save {name!r}? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                print("Cancelled.")
                return 0
        was_active = name == SAVE_NAME
        savefiles.delete_save(SAVE_DIR, name)
        print(green(f"Deleted save: {name}"))
        if was_active:
            _activate_save(savefiles.active_name(SAVE_DIR))
            print(f"Active save is now: {SAVE_NAME}")
        return 0
    if action == "copy":
        try:
            data = savefiles.copy_save(SAVE_DIR, args.source, args.destination)
        except (ValueError, FileExistsError, FileNotFoundError, OSError) as exc:
            print(red(str(exc)))
            return 1
        print(green(f"Copied save to: {data['name']}"))
        return 0
    print(red(f"Unknown save action: {action}"))
    return 1


def _save_list() -> int:
    init_state()
    names = savefiles.list_save_names(SAVE_DIR)
    print()
    print(bold("Save slots"))
    print(dim(str(SAVE_DIR)))
    print(rule("-", 72))
    if not names:
        print(yellow("No save slots yet."))
        return 0
    for name in names:
        data = savefiles.load_save(SAVE_DIR, name)
        marker = green("*") if name == SAVE_NAME else " "
        exam = get_exam(data.get("active_exam", ""), EXAMS)
        exam_name = exam.name if exam else "(no exam selected)"
        done = savefiles.total_completed(data)
        print(f" {marker} {name:<20} {data.get('updated', '')}")
        print(dim(f"   Exam: {exam_name} · {done} completed module(s)"))
    print()
    print(dim("Use: python3 main.py save use <name>"))
    print(dim("New: python3 main.py save new <name>"))
    return 0


def _save_info(data: dict) -> int:
    print()
    print(bold(f"Save slot: {data.get('name', SAVE_NAME)}"))
    print(rule("-", 72))
    print(f"Path:     {savefiles.save_path(SAVE_DIR, data.get('name', SAVE_NAME))}")
    print(f"Created:  {data.get('created', '')}")
    print(f"Updated:  {data.get('updated', '')}")
    exam = get_exam(data.get("active_exam", ""), EXAMS)
    print(f"Active:   {exam.name if exam else '(none)'}")
    print()
    progress = data.get("progress", {})
    if not progress:
        print(dim("No progress recorded yet."))
        return 0
    for exam_id, entry in sorted(progress.items()):
        completed = entry.get("completed", {}) if isinstance(entry, dict) else {}
        attempts = entry.get("attempts", {}) if isinstance(entry, dict) else {}
        known = get_exam(exam_id, EXAMS)
        label = known.name if known else exam_id
        print(f"  {label}: {len(completed)} completed, {len(attempts)} attempted")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    """Launch the graphical lab, or report its prerequisites."""
    try:
        import gui
    except Exception as exc:  # pragma: no cover - environment dependent
        print(red(f"Could not import the GUI: {exc}"))
        print(dim("The command-line interface still works: python3 main.py list"))
        return 1
    if getattr(args, "check", False):
        return gui.check()
    return gui.launch(module_key=getattr(args, "module", None))


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
    assert ACTIVE_EXAM is not None and SAVE_DIR is not None
    checks.append((True, f"Exam: {ACTIVE_EXAM.name} ({ACTIVE_EXAM.id})"))
    checks.append((True, f"Exam workspace: {exam_lab()}"))
    checks.append(
        (
            True,
            f"Save: {SAVE_NAME} ({savefiles.save_path(SAVE_DIR, SAVE_NAME)})",
        )
    )
    checks.append((len(EXAMS) > 0, f"Exams discovered: {len(EXAMS)}"))
    checks.append((True, f"Objectives inbox: {INBOX_DIR}"))

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

    checks.append((True, f"Save slots: {len(savefiles.list_save_names(SAVE_DIR))}"))

    exam_modules = current_modules()
    if ACTIVE_EXAM.has_curriculum:
        checks.append(
            (
                bool(exam_modules),
                f"Curriculum modules for {ACTIVE_EXAM.short_name}: {len(exam_modules)}",
            )
        )
        missing_lessons = [
            module["lesson"]
            for module in exam_modules
            if not current_lesson_path(module).is_file()
        ]
        checks.append(
            (
                not missing_lessons,
                "All lesson files present"
                + (f" (missing: {', '.join(missing_lessons)})" if missing_lessons else ""),
            )
        )
    else:
        checks.append(
            (
                True,
                f"Curriculum modules for {ACTIVE_EXAM.short_name}: 0 "
                "(objectives-only exam)",
            )
        )
        checks.append(
            (
                True,
                f"Objectives documents: {len(ACTIVE_EXAM.objective_files())}",
            )
        )

    checks.append(
        (
            shutil.which("pdftotext") is not None,
            "pdftotext: " + (shutil.which("pdftotext") or "not installed (needed for PDF objectives)"),
        )
    )

    try:
        import tkinter  # noqa: F401

        tkinter_note = "available (optional GUI)"
    except Exception as exc:  # pragma: no cover - environment dependent
        tkinter_note = f"not available (GUI disabled: {exc})"
    checks.append((True, f"tkinter: {tkinter_note}"))

    bwrap = shutil.which("bwrap")
    checks.append(
        (
            bwrap is not None,
            f"bwrap: {bwrap} (sandboxed GUI terminals)"
            if bwrap
            else "bwrap: not installed (sandboxed GUI terminals disabled)",
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
    mission = current_mission(module["id"])
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
    init_state()
    while True:
        banner()
        modules = current_modules()
        upcoming = next_module()
        if not modules:
            print(yellow("No curriculum pack yet for this exam."))
            print(dim("Option 9 reads the objectives you have attached."))
        elif upcoming is not None:
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
        print("  8. Switch exam")
        print("  9. Save slots / read objectives")
        print("  q. Quit")
        try:
            choice = input(bold("Select> ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if choice in ("q", "quit", "exit"):
            return 0
        if choice in ("1", "c", "continue", "next"):
            if not modules:
                _exam_objectives(ACTIVE_EXAM)
                pause()
            elif upcoming is None:
                cmd_progress(argparse.Namespace())
            else:
                module_menu(upcoming)
        elif choice == "2":
            if not _require_modules():
                pause()
                continue
            cmd_list(argparse.Namespace())
            try:
                key = input(bold("\nModule number (Enter to go back): ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                continue
            if key:
                module = ACTIVE_EXAM.get_module(key)
                if module is None:
                    print(red("No such module."))
                else:
                    module_menu(module)
        elif choice == "3":
            if not _require_modules():
                pause()
                continue
            cmd_list(argparse.Namespace())
            try:
                key = input(bold("\nMission number to open (Enter to go back): ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                continue
            if key:
                module = ACTIVE_EXAM.get_module(key)
                if module is None:
                    print(red("No such mission."))
                else:
                    cmd_mission(argparse.Namespace(module=str(module["num"])))
                    module_menu(module)
        elif choice in ("4", "p", "progress"):
            cmd_progress(argparse.Namespace())
            pause()
        elif choice == "5":
            if not _require_modules():
                pause()
                continue
            try:
                key = input(bold("Mission number for its reference solution: ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                continue
            if key:
                module = ACTIVE_EXAM.get_module(key)
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
        elif choice == "8":
            _exam_list()
            try:
                key = input(bold("\nExam id or code (Enter to go back): ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                continue
            if key:
                try:
                    exam = resolve_exam(key, EXAMS)
                except ValueError as exc:
                    print(red(str(exc)))
                else:
                    _activate_exam(exam)
                    print(green(f"Active exam: {exam.name}"))
                pause()
        elif choice == "9":
            _save_list()
            print()
            print("  [number] switch to that save")
            print("  [n] new save   [d] delete save   [o] read objectives")
            try:
                action = input(bold("Save> ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                continue
            if action in ("o", "objectives"):
                _exam_objectives(ACTIVE_EXAM)
                pause()
            elif action in ("n", "new"):
                try:
                    name = input(bold("New save name: ")).strip()
                    data = savefiles.create_save(SAVE_DIR, name, ACTIVE_EXAM.id)
                except (ValueError, FileExistsError, OSError) as exc:
                    print(red(str(exc)))
                else:
                    print(green(f"Created save {data['name']}. Switch to it with save use."))
                pause()
            elif action in ("d", "delete"):
                try:
                    name = input(bold("Save name to delete: ")).strip()
                    names = savefiles.list_save_names(SAVE_DIR)
                    if len(names) <= 1:
                        print(red("Cannot delete the only save slot."))
                    else:
                        name = savefiles.normalize_name(name)
                        answer = input(f"Delete save {name!r}? [y/N] ").strip().lower()
                        if answer in ("y", "yes"):
                            was_active = name == SAVE_NAME
                            savefiles.delete_save(SAVE_DIR, name)
                            print(green(f"Deleted save: {name}"))
                            if was_active:
                                _activate_save(savefiles.active_name(SAVE_DIR))
                                print(f"Active save is now: {SAVE_NAME}")
                except (ValueError, OSError) as exc:
                    print(red(str(exc)))
                pause()
            elif action:
                try:
                    _activate_save(action)
                except (ValueError, FileNotFoundError, OSError) as exc:
                    print(red(str(exc)))
                else:
                    print(green(f"Active save: {SAVE_NAME}"))
                pause()
        elif choice:
            module = ACTIVE_EXAM.get_module(choice)
            if module is not None:
                module_menu(module)


def _require_modules() -> bool:
    if current_modules():
        return True
    assert ACTIVE_EXAM is not None
    print(yellow(f"{ACTIVE_EXAM.name} has no curriculum pack yet."))
    print("Use option 8 to switch exams, or option 9 to read its objectives.")
    return False


def show_how_it_works() -> None:
    init_state()
    modules = current_modules()
    module_line = (
        f"Each of the {len(modules)} modules has three parts:"
        if modules
        else "This exam is objectives-only until a curriculum pack is built."
    )
    text = f"""\
{bold("How this study platform works")}

{module_line}

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

Exams and saves:

  python3 main.py exam list         # every exam the platform can see
  python3 main.py exam use <id>     # switch exam inside this save
  python3 main.py save list         # independent progress files
  python3 main.py save new <name>   # another learner / another run

  Save slot: {SAVE_NAME}
  Active exam: {ACTIVE_EXAM.name}
  Exam workspace: {exam_lab()}

All mission files live under the exam workspace. You can open a second
terminal and work in it with normal Linux tools: ls, chmod, grep, ss,
systemctl, tar, less, vim/nano. Nothing in the missions requires root.

Why not put the lab inside this program folder?
{("  " + LAB_NOTE) if LAB_NOTE else "  A local ext4/xfs/btrfs folder is used so permissions and SUID are real."}

Objectives inbox: {INBOX_DIR}
Drop CompTIA objective PDFs there, then:
  python3 main.py exam add <id> --name "CompTIA ..."
  python3 main.py exam attach <id> <file>
  python3 main.py exam scan <id>
  python3 main.py exam objectives <id>

Save files are plain JSON under {SAVE_DIR}. Back them up to move machines.

Commands:
  list, show N, mission N, verify N, hint N, solution N [--write],
  progress, next, reset [N], doctor,
  exam list|use|info|add|attach|scan|objectives,
  save list|new|use|show|delete|copy
"""
    page(text)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="comptia-study-lab",
        description=(
            "Hands-on CompTIA exam preparation with multiple exams and save slots. "
            "Run with no arguments for the interactive menu."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 main.py                 interactive menu\n"
            "  python3 main.py list            see the active exam's modules\n"
            "  python3 main.py exam list       see every exam\n"
            "  python3 main.py save list       see save slots\n"
            "  python3 main.py show 4          read module 4's lesson\n"
            "  python3 main.py mission 4       show the hands-on task\n"
            "  python3 main.py verify 4        run the real checks\n"
            "  python3 main.py gui             graphical lab with sandboxed terminals\n"
            "  python3 main.py exam scan       extract objectives text\n"
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
        help="write a copy under <lab>/<exam>/_reference/ instead of paging it",
    )

    sub.add_parser("progress", help="show a detailed progress report")
    sub.add_parser("next", help="open the next incomplete module")
    sub.add_parser("doctor", help="check Python, lab, tools, exams, and saves")

    gui = sub.add_parser(
        "gui", help="open the graphical lab with sandboxed terminals"
    )
    gui.add_argument(
        "--module", help="module number or id to open (default: next incomplete)"
    )
    gui.add_argument(
        "--check",
        action="store_true",
        help="check Tkinter, display, and bubblewrap, then exit",
    )

    reset = sub.add_parser("reset", help="delete a mission workspace and its progress")
    reset.add_argument("module", nargs="?", help="module number (omit to reset the exam)")
    reset.add_argument("--yes", action="store_true", help="do not ask for confirmation")

    exam = sub.add_parser("exam", help="list, add, inspect, or switch exams")
    exam_sub = exam.add_subparsers(dest="exam_action", required=True)
    exam_sub.add_parser("list", help="list every discovered exam")
    for name, help_text in (
        ("use", "make an exam active in the current save"),
        ("info", "show exam metadata, objectives, and progress"),
        ("scan", "extract text from objectives documents"),
        ("objectives", "read the active or named exam's objectives"),
    ):
        action = exam_sub.add_parser(name, help=help_text)
        action.add_argument("exam_id", nargs="?", help="exam id or code (default: active)")

    add = exam_sub.add_parser("add", help="scaffold a new objectives-only exam")
    add.add_argument("exam_id", help="folder-safe id, e.g. security-plus-sy0-701")
    add.add_argument("--name", required=True, help='full name, e.g. "CompTIA Security+ (SY0-701)"')
    add.add_argument("--code", default="", help="exam code, e.g. SY0-701")
    add.add_argument("--short-name", default="", help="short label, e.g. Security+")
    add.add_argument("--description", default="", help="one-line description")
    add.add_argument("--use", action="store_true", help="switch to the new exam immediately")

    attach = exam_sub.add_parser("attach", help="copy an objectives document into an exam")
    attach.add_argument("exam_id", help="exam id or code")
    attach.add_argument("source", help="path to the PDF/DOCX/TXT/MD file")

    save = sub.add_parser("save", help="manage independent progress save slots")
    save_sub = save.add_subparsers(dest="save_action", required=True)
    save_sub.add_parser("list", help="list save slots")
    new = save_sub.add_parser("new", help="create a save slot")
    new.add_argument("name")
    use = save_sub.add_parser("use", help="switch the active save slot")
    use.add_argument("name")
    show = save_sub.add_parser("show", help="show one save slot's contents")
    show.add_argument("name", nargs="?", help="save name (default: active)")
    delete = save_sub.add_parser("delete", help="delete a save slot")
    delete.add_argument("name")
    delete.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    copy = save_sub.add_parser("copy", help="copy a save slot")
    copy.add_argument("source")
    copy.add_argument("destination")

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    init_lab(args.lab)
    init_state()

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
        "gui": cmd_gui,
        "reset": cmd_reset,
        "exam": cmd_exam,
        "save": cmd_save,
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
