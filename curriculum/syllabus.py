"""The ordered curriculum: lessons + the mission that proves each lesson."""
from __future__ import annotations

MODULES: list[dict] = [
    {
        "num": 1,
        "id": "m01",
        "part": "Part I — Python foundations",
        "title": "First contact: a real executable script",
        "lesson": "01_first_contact.md",
        "domain": "Linux+ 3.1 Scripting basics",
        "summary": "The interpreter, scripts vs. REPL, shebangs, chmod +x, main guards.",
        "minutes": 45,
    },
    {
        "num": 2,
        "id": "m02",
        "part": "Part I — Python foundations",
        "title": "Variables, types, and f-strings",
        "lesson": "02_variables_and_types.md",
        "domain": "Linux+ 1.1 System information",
        "summary": "Numbers, strings, bools, None, conversions, f-strings, platform/os.",
        "minutes": 60,
    },
    {
        "num": 3,
        "id": "m03",
        "part": "Part I — Python foundations",
        "title": "Decisions, comparisons, and exit codes",
        "lesson": "03_control_flow.md",
        "domain": "Linux+ 4.1 Storage troubleshooting",
        "summary": "if/elif/else, truthiness, comparison chains, sys.exit and shell status.",
        "minutes": 60,
    },
    {
        "num": 4,
        "id": "m04",
        "part": "Part I — Python foundations",
        "title": "Lists, dictionaries, and real /etc/passwd data",
        "lesson": "04_collections.md",
        "domain": "Linux+ 1.5 Users and groups",
        "summary": "Lists, dicts, tuples, sets, Counter, sorting, parsing record files.",
        "minutes": 90,
    },
    {
        "num": 5,
        "id": "m05",
        "part": "Part II — Working with Linux data",
        "title": "Loops, comprehensions, and Counter",
        "lesson": "05_loops_and_comprehensions.md",
        "domain": "Linux+ 2.2 Log analysis",
        "summary": "for/while, enumerate, zip, comprehensions, generators, log triage.",
        "minutes": 90,
    },
    {
        "num": 6,
        "id": "m06",
        "part": "Part II — Working with Linux data",
        "title": "Functions and argparse: a multi-command toolkit",
        "lesson": "06_functions_and_argparse.md",
        "domain": "Linux+ 3.1 Scripting / 3.3 Automation",
        "summary": "def, parameters, return values, scope, modules, argparse subcommands.",
        "minutes": 100,
    },
    {
        "num": 7,
        "id": "m07",
        "part": "Part II — Working with Linux data",
        "title": "Pathlib and file metadata: the janitor",
        "lesson": "07_files_and_pathlib.md",
        "domain": "Linux+ 1.4 Storage management",
        "summary": "Path objects, rglob, stat, mtime, deletion safety, dry-run design.",
        "minutes": 90,
    },
    {
        "num": 8,
        "id": "m08",
        "part": "Part II — Working with Linux data",
        "title": "Exceptions: read files without crashing",
        "lesson": "08_errors_and_exceptions.md",
        "domain": "Linux+ 4.3 Troubleshooting methodology",
        "summary": "try/except/else/finally, EAFP, custom errors, stderr, exit codes.",
        "minutes": 90,
    },
    {
        "num": 9,
        "id": "m09",
        "part": "Part II — Working with Linux data",
        "title": "Regex: parse ss and ip output",
        "lesson": "09_text_and_regex.md",
        "domain": "Linux+ 4.4 Network troubleshooting",
        "summary": "re syntax, groups, greedy vs. specific patterns, parsing command output.",
        "minutes": 120,
    },
    {
        "num": 10,
        "id": "m10",
        "part": "Part III — Talking to the system",
        "title": "subprocess: run commands and capture the truth",
        "lesson": "10_subprocess.md",
        "domain": "Linux+ 3.1 Scripting / 4.3 Troubleshooting",
        "summary": "argv lists, shell=False, capture_output, timeouts, return codes.",
        "minutes": 100,
    },
    {
        "num": 11,
        "id": "m11",
        "part": "Part III — Talking to the system",
        "title": "os.stat and bitmasks: permission audit",
        "lesson": "11_permissions_and_stat.md",
        "domain": "Linux+ 2.1 Security / file permissions",
        "summary": "Unix modes, SUID/SGID/sticky, bitwise tests, recursive audits.",
        "minutes": 110,
    },
    {
        "num": 12,
        "id": "m12",
        "part": "Part III — Talking to the system",
        "title": "Sockets: build a TCP port checker",
        "lesson": "12_sockets.md",
        "domain": "Linux+ 4.4 Network troubleshooting",
        "summary": "TCP connect, timeouts, context managers, listening sockets.",
        "minutes": 90,
    },
    {
        "num": 13,
        "id": "m13",
        "part": "Part III — Talking to the system",
        "title": "Config formats: systemd unit inspector",
        "lesson": "13_config_formats.md",
        "domain": "Linux+ 1.2 Services / systemd",
        "summary": "configparser, INI quirks, validation, JSON output, unit files.",
        "minutes": 100,
    },
    {
        "num": 14,
        "id": "m14",
        "part": "Part IV — Production habits",
        "title": "Logging, tarfile, and retention: a real backup tool",
        "lesson": "14_logging_and_backups.md",
        "domain": "Linux+ 1.4 Storage / 3.3 Automation",
        "summary": "logging, tarfile, timestamps, retention, dry-run, cron/systemd timers.",
        "minutes": 120,
    },
    {
        "num": 15,
        "id": "m15",
        "part": "Part IV — Production habits",
        "title": "Debugging and unittest: fix it, then prove it",
        "lesson": "15_debugging_and_testing.md",
        "domain": "Linux+ 4.5 Troubleshooting",
        "summary": "pdb, reading tracebacks, unittest, edge cases, mutation thinking.",
        "minutes": 120,
    },
    {
        "num": 16,
        "id": "m16",
        "part": "Part IV — Production habits",
        "title": "Capstone: package a Linux+ security audit kit",
        "lesson": "16_capstone.md",
        "domain": "Linux+ Capstone — all domains",
        "summary": "Packages, __main__, composition, JSON reports, read-only audits.",
        "minutes": 180,
    },
]

BY_NUM = {module["num"]: module for module in MODULES}
BY_ID = {module["id"]: module for module in MODULES}


def get_module(key: str | int) -> dict | None:
    if isinstance(key, int):
        return BY_NUM.get(key)
    key = str(key).strip().lower()
    if key.isdigit():
        return BY_NUM.get(int(key))
    return BY_ID.get(key)


def total_minutes() -> int:
    return sum(module["minutes"] for module in MODULES)
