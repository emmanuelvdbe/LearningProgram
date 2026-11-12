"""Part 2 — Working with Linux data (missions 5-9)."""
from __future__ import annotations

import os
import platform
import re
import shutil
import time
from pathlib import Path

from .base import (
    Check,
    Mission,
    fresh_dir,
    no_traceback,
    output,
    parse_json,
    run_script,
    write_file,
)
from .part1 import PASSWD_SAMPLE

# ---------------------------------------------------------------------------
# Mission 05 — Log triage
# ---------------------------------------------------------------------------
LOG_LINES = """\
Jan 12 03:14:15 web01 sshd[1234]: Accepted publickey for deb from 192.0.2.10 port 51234 ssh2
Jan 12 03:14:18 web01 sshd[1235]: Failed password for root from 203.0.113.7 port 40001 ssh2
Jan 12 03:14:20 web01 sshd[1236]: Failed password for invalid user admin from 198.51.100.22 port 40002 ssh2
Jan 12 03:15:01 web01 sshd[1237]: Accepted password for alice from 192.0.2.11 port 51235 ssh2
Jan 12 03:15:04 web01 sshd[1238]: Invalid user test from 203.0.113.7
Jan 12 03:15:07 web01 sshd[1239]: Failed password for invalid user oracle from 198.51.100.22 port 40003 ssh2
Jan 12 03:15:09 web01 sshd[1240]: Failed password for root from 203.0.113.7 port 40004 ssh2
Jan 12 03:15:12 web01 sshd[1241]: Accepted publickey for deb from 192.0.2.10 port 51236 ssh2
Jan 12 03:15:15 web01 sshd[1242]: Failed password for admin from 198.51.100.22 port 40005 ssh2
Jan 12 03:15:18 web01 sshd[1243]: Invalid user ftp from 203.0.113.9
Jan 12 03:15:21 web01 sshd[1244]: Failed password for invalid user postgres from 203.0.113.9 port 40006 ssh2
Jan 12 03:15:24 web01 sshd[1245]: Accepted password for bob from 192.0.2.12 port 51237 ssh2
Jan 12 03:15:27 web01 sshd[1246]: Failed password for root from 203.0.113.7 port 40007 ssh2
Jan 12 03:15:30 web01 sshd[1247]: Failed password for test from 198.51.100.22 port 40008 ssh2
Jan 12 03:15:33 web01 sshd[1248]: Accepted publickey for deb from 192.0.2.10 port 51238 ssh2
Jan 12 03:15:36 web01 sshd[1249]: Failed password for invalid user guest from 203.0.113.9 port 40009 ssh2
Jan 12 03:15:39 web01 sshd[1250]: Accepted password for carol from 192.0.2.13 port 51239 ssh2
Jan 12 03:15:42 web01 sshd[1251]: Failed password for root from 203.0.113.7 port 40010 ssh2
Jan 12 03:15:45 web01 sshd[1252]: Invalid user admin from 198.51.100.22
Jan 12 03:15:48 web01 sshd[1253]: Accepted publickey for alice from 192.0.2.11 port 51240 ssh2
"""


def setup_m05(mdir: Path) -> None:
    write_file(mdir / "auth.log", LOG_LINES)


M05_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Summarise SSH auth log noise as JSON.\"\"\"
import json
import re
import sys
from collections import Counter

IP_RE = re.compile(r"from (\\d{1,3}(?:\\.\\d{1,3}){3})")


def classify(line: str) -> str | None:
    if "Accepted " in line:
        return "accepted"
    if "Failed password" in line:
        return "failed"
    if "Invalid user" in line:
        return "invalid"
    return None


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: log_triage.py <auth.log> <report.json>", file=sys.stderr)
        return 2
    try:
        with open(sys.argv[1], encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError as exc:
        print(f"ERROR: cannot read log: {exc}", file=sys.stderr)
        return 2

    counts = Counter()
    bad_ips = Counter()
    for line in lines:
        kind = classify(line)
        if kind is None:
            continue
        counts[kind] += 1
        if kind in {"failed", "invalid"}:
            match = IP_RE.search(line)
            if match:
                bad_ips[match.group(1)] += 1

    top = sorted(bad_ips.items(), key=lambda item: (-item[1], item[0]))[:3]
    report = {
        "total_lines": len(lines),
        "failed": counts["failed"],
        "accepted": counts["accepted"],
        "invalid": counts["invalid"],
        "top_bad_ips": [[ip, count] for ip, count in top],
    }
    with open(sys.argv[2], "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"wrote {sys.argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""


def check_m05(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "log_triage.py"
    checks.append(Check("log_triage.py exists", script.is_file(), str(script)))
    if not script.is_file():
        return checks

    verify = fresh_dir(mdir / "_verify")
    fixture = write_file(verify / "auth.log", LOG_LINES)
    report = verify / "report.json"
    proc = run_script(script, fixture, report, cwd=mdir, timeout=10)
    checks.append(Check("exits 0", proc.returncode == 0, output(proc)))
    checks.append(
        Check("creates the output file", report.is_file(), f"missing {report}")
    )
    if not report.is_file():
        return checks

    try:
        data = __import__("json").loads(report.read_text(encoding="utf-8"))
    except Exception as exc:
        checks.append(Check("output is valid JSON", False, str(exc)))
        return checks
    checks.append(Check("output is valid JSON", True, ""))

    expected = {
        "total_lines": 20,
        "failed": 10,
        "accepted": 7,
        "invalid": 3,
    }
    for key, value in expected.items():
        checks.append(
            Check(
                f"{key} is correct",
                data.get(key) == value,
                f"got {data.get(key)!r}, expected {value}",
            )
        )
    checks.append(
        Check(
            "top_bad_ips is the correct sorted top 3",
            data.get("top_bad_ips")
            == [
                ["198.51.100.22", 5],
                ["203.0.113.7", 5],
                ["203.0.113.9", 3],
            ],
            f"got {data.get('top_bad_ips')!r}",
        )
    )
    return checks


M05 = Mission(
    id="m05",
    num=5,
    dir_name="05_log_triage",
    title="Loops, comprehensions, and Counter",
    domain="Linux+ 2.2 Log analysis / 4.3 Troubleshooting",
    brief="""\
MISSION 05 — Log triage

A sample SSH log is at 05_log_triage/auth.log. Create:

    05_log_triage/log_triage.py

Usage:
    python3 log_triage.py <auth.log> <report.json>

Classification rules (check in this order):
  1. line contains "Accepted "          -> accepted
  2. line contains "Failed password"     -> failed
  3. line contains "Invalid user"        -> invalid
  4. anything else                       -> ignored

Report JSON:
    {
      "total_lines": 20,
      "failed": 10,
      "accepted": 7,
      "invalid": 3,
      "top_bad_ips": [["198.51.100.22", 5], ["203.0.113.7", 5],
                      ["203.0.113.9", 3]]
    }

Rules:
  * total_lines counts every line in the file.
  * top_bad_ips = (ip, count) for failed + invalid events, sorted by
    count descending, then IP ascending, limited to 3.
  * Extract the IP after the word "from" (IPv4).
  * Write indented JSON to the output path; print nothing that is required.

Verify with:  python3 main.py verify 5
""",
    hints=[
        "Put the three checks in a classify(line) function that returns a string or None.",
        "Counter() is a dict subclass: counts[kind] += 1, and .most_common() exists.",
        "Sort explicitly for a stable tie-break: key=lambda item: (-item[1], item[0]).",
        "re.search(r'from (\\d+\\.\\d+\\.\\d+\\.\\d+)', line) gives you the IP.",
    ],
    solution={"log_triage.py": M05_SOLUTION},
    setup=setup_m05,
    check=check_m05,
)


# ---------------------------------------------------------------------------
# Mission 06 — syskit
# ---------------------------------------------------------------------------
M06_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"A tiny multi-command sysadmin toolkit.\"\"\"
import argparse
import platform
import shutil
import sys


def cmd_info(_args: argparse.Namespace) -> int:
    print(f"host={platform.node()}")
    print(f"kernel={platform.release()}")
    print(f"python={platform.python_version()}")
    return 0


def cmd_disk(args: argparse.Namespace) -> int:
    try:
        usage = shutil.disk_usage(args.path)
    except FileNotFoundError:
        print(f"ERROR: path not found: {args.path}", file=sys.stderr)
        return 2
    percent = usage.used / usage.total * 100
    print(f"path={args.path}")
    print(f"total={usage.total}")
    print(f"used={usage.used}")
    print(f"free={usage.free}")
    print(f"percent={percent:.1f}")
    return 0


def count_humans(path: str) -> int:
    count = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            fields = line.strip().split(":")
            if len(fields) != 7:
                continue
            try:
                uid = int(fields[2])
            except ValueError:
                continue
            if 1000 <= uid < 65534:
                count += 1
    return count


def cmd_users(args: argparse.Namespace) -> int:
    try:
        total = count_humans(args.file)
    except OSError as exc:
        print(f"ERROR: cannot read {args.file}: {exc}", file=sys.stderr)
        return 2
    print(total)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="syskit", description="Linux+ sysadmin toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    info = sub.add_parser("info", help="show host information")
    info.set_defaults(func=cmd_info)

    disk = sub.add_parser("disk", help="show filesystem usage")
    disk.add_argument("--path", default="/", help="filesystem path (default: /)")
    disk.set_defaults(func=cmd_disk)

    users = sub.add_parser("users", help="count human users in a passwd file")
    users.add_argument("file", help="path to a passwd-style file")
    users.set_defaults(func=cmd_users)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
"""


def check_m06(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "syskit.py"
    checks.append(Check("syskit.py exists", script.is_file(), str(script)))
    if not script.is_file():
        return checks

    info = run_script(script, "info", cwd=mdir, timeout=10)
    info_data = {}
    for line in info.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info_data[k.strip()] = v.strip()
    checks.append(
        Check(
            "info prints host and kernel",
            info.returncode == 0
            and info_data.get("host") == platform.node()
            and info_data.get("kernel") == platform.release(),
            output(info),
        )
    )

    disk = run_script(script, "disk", cwd=mdir, timeout=10)
    disk_data = {}
    for line in disk.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            disk_data[k.strip()] = v.strip()
    try:
        total = int(disk_data.get("total", ""))
        used = int(disk_data.get("used", ""))
        free = int(disk_data.get("free", ""))
        percent = float(disk_data.get("percent", ""))
        actual = shutil.disk_usage("/")
        ok = (
            disk.returncode == 0
            and disk_data.get("path") == "/"
            and total == actual.total
            and used == actual.used
            and free == actual.free
            and abs(percent - used / total * 100) <= 0.2
        )
        detail = output(disk)
    except (ValueError, ZeroDivisionError) as exc:
        ok = False
        detail = f"{exc}\n{output(disk)}"
    checks.append(Check("disk prints correct byte counts and percent", ok, detail))

    missing = run_script(script, "disk", "--path", "/definitely/not/here", cwd=mdir)
    checks.append(
        Check(
            "disk on a missing path exits 2 cleanly",
            missing.returncode == 2
            and "Traceback" not in missing.stderr
            and missing.stderr.strip() != "",
            output(missing),
        )
    )

    verify = fresh_dir(mdir / "_verify")
    fixture = write_file(verify / "passwd", PASSWD_SAMPLE)
    users = run_script(script, "users", fixture, cwd=mdir, timeout=10)
    checks.append(
        Check(
            "users prints the human-user count (4)",
            users.returncode == 0 and users.stdout.strip() == "4",
            output(users),
        )
    )

    missing_users = run_script(script, "users", verify / "nope", cwd=mdir)
    checks.append(
        Check(
            "users on a missing file exits 2 cleanly",
            missing_users.returncode == 2
            and "Traceback" not in missing_users.stderr
            and missing_users.stderr.strip() != "",
            output(missing_users),
        )
    )

    help_out = run_script(script, "--help", cwd=mdir, timeout=10)
    combined = help_out.stdout + help_out.stderr
    checks.append(
        Check(
            "--help lists info, disk, and users",
            help_out.returncode == 0
            and all(word in combined for word in ("info", "disk", "users")),
            output(help_out),
        )
    )
    return checks


M06 = Mission(
    id="m06",
    num=6,
    dir_name="06_syskit",
    title="Functions and argparse: a multi-command toolkit",
    domain="Linux+ 3.1 Scripting / 3.3 Automation",
    brief="""\
MISSION 06 — syskit

Create:

    06_syskit/syskit.py

One file, three subcommands, using argparse:

    python3 syskit.py info
        host=<platform.node()>
        kernel=<platform.release()>
        python=<platform.python_version()>
        exit 0

    python3 syskit.py disk [--path PATH]        # default PATH=/
        path=<PATH>
        total=<bytes>
        used=<bytes>
        free=<bytes>
        percent=<used/total*100, 1 decimal>
        exit 0; a missing path prints an error to stderr and exits 2

    python3 syskit.py users <passwd-file>
        prints ONLY the integer count of human users (UID 1000..65533)
        exit 0; a missing/unreadable file exits 2

Requirements:
  * Use argparse with real subparsers (dest="command", required=True).
  * Put each command in its own function, and have main() dispatch.
  * No tracebacks for expected errors (missing files, bad paths).
  * --help must list info, disk, and users.

Verify with:  python3 main.py verify 6
""",
    hints=[
        "parser.add_subparsers(dest='command', required=True) then sub.add_parser(...).",
        "Each subparser can call set_defaults(func=cmd_info) and main returns args.func(args).",
        "shutil.disk_usage raises FileNotFoundError for a missing path.",
        "Reuse the UID rule from mission 4; count only, do not print names.",
    ],
    solution={"syskit.py": M06_SOLUTION},
    check=check_m06,
)


# ---------------------------------------------------------------------------
# Mission 07 — File janitor
# ---------------------------------------------------------------------------
def setup_m07(mdir: Path) -> None:
    sandbox = mdir / "sandbox"
    if sandbox.exists():
        return
    (sandbox / "sub").mkdir(parents=True)
    now = time.time()
    for rel, age_days in (
        ("old.tmp", 10),
        ("ancient.tmp", 30),
        ("new.tmp", 0),
        ("keep.log", 10),
        ("sub/old2.tmp", 10),
        ("sub/keep.txt", 10),
    ):
        path = sandbox / rel
        path.write_text(f"fixture: {rel}\n", encoding="utf-8")
        stamp = now - age_days * 86400
        os.utime(path, (stamp, stamp))


M07_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Find (and optionally delete) old files under a directory.\"\"\"
import argparse
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="janitor")
    parser.add_argument("directory", help="directory to scan")
    parser.add_argument("--pattern", default="*.tmp", help="glob pattern")
    parser.add_argument("--days", type=float, default=7, help="minimum age in days")
    parser.add_argument("--apply", action="store_true", help="actually delete")
    args = parser.parse_args()

    root = Path(args.directory)
    if not root.is_dir():
        print(f"ERROR: directory not found: {root}", file=sys.stderr)
        return 2

    cutoff = time.time() - args.days * 86400
    matches = []
    for path in root.rglob(args.pattern):
        if path.is_file() and path.stat().st_mtime < cutoff:
            matches.append(path)

    for path in sorted(matches):
        rel = path.relative_to(root)
        if args.apply:
            path.unlink()
            print(f"DELETED: {rel}")
        else:
            print(f"WOULD DELETE: {rel}")

    if not matches:
        print("no matching files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""


def _make_janitor_fixture(root: Path) -> None:
    fresh_dir(root)
    (root / "sub").mkdir()
    now = time.time()
    for rel, age_days in (
        ("old.tmp", 10),
        ("ancient.tmp", 30),
        ("new.tmp", 0),
        ("keep.log", 10),
        ("sub/old2.tmp", 10),
        ("sub/keep.txt", 10),
    ):
        path = root / rel
        path.write_text(rel, encoding="utf-8")
        stamp = now - age_days * 86400
        os.utime(path, (stamp, stamp))


def check_m07(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "janitor.py"
    checks.append(Check("janitor.py exists", script.is_file(), str(script)))
    if not script.is_file():
        return checks

    verify = mdir / "_verify"
    sandbox = verify / "sandbox"
    _make_janitor_fixture(sandbox)

    dry = run_script(script, sandbox, "--days", "7", cwd=mdir, timeout=10)
    still_there = all(
        (sandbox / rel).exists()
        for rel in ("old.tmp", "ancient.tmp", "sub/old2.tmp", "new.tmp")
    )
    checks.append(
        Check(
            "dry run lists old .tmp files and deletes nothing",
            dry.returncode == 0
            and "old.tmp" in dry.stdout
            and "old2.tmp" in dry.stdout
            and "ancient.tmp" in dry.stdout
            and "new.tmp" not in dry.stdout
            and still_there,
            output(dry),
        )
    )

    custom = run_script(
        script, sandbox, "--days", "7", "--pattern", "*.log", cwd=mdir, timeout=10
    )
    checks.append(
        Check(
            "--pattern '*.log' finds only keep.log",
            custom.returncode == 0
            and "keep.log" in custom.stdout
            and "old.tmp" not in custom.stdout,
            output(custom),
        )
    )

    apply = run_script(
        script, sandbox, "--days", "7", "--apply", cwd=mdir, timeout=10
    )
    removed = not any(
        (sandbox / rel).exists()
        for rel in ("old.tmp", "ancient.tmp", "sub/old2.tmp")
    )
    kept = all(
        (sandbox / rel).exists()
        for rel in ("new.tmp", "keep.log", "sub/keep.txt")
    )
    checks.append(
        Check(
            "--apply deletes exactly the matching files",
            apply.returncode == 0 and removed and kept,
            f"removed={removed} kept={kept}\n{output(apply)}",
        )
    )

    missing = run_script(script, verify / "missing-dir", cwd=mdir, timeout=10)
    checks.append(
        Check(
            "missing directory exits 2 cleanly",
            missing.returncode == 2
            and "Traceback" not in missing.stderr
            and missing.stderr.strip() != "",
            output(missing),
        )
    )
    return checks


M07 = Mission(
    id="m07",
    num=7,
    dir_name="07_file_janitor",
    title="Pathlib and file metadata: the janitor",
    domain="Linux+ 1.4 Storage management",
    brief="""\
MISSION 07 — File janitor

Create:

    07_file_janitor/janitor.py

Usage:
    python3 janitor.py <dir> [--pattern GLOB] [--days N] [--apply]

Defaults: --pattern "*.tmp"  --days 7  (dry run unless --apply is given)

Behaviour:
  * Recursively find files under <dir> matching the glob pattern.
  * Only include files whose mtime is older than N days.
  * Dry run: print
        WOULD DELETE: <path relative to dir>
    for each match, oldest path order is fine; delete NOTHING.
  * --apply: delete each match and print
        DELETED: <path relative to dir>
  * If no files match, print "no matching files".
  * A missing directory prints an error to stderr and exits 2.

The sample sandbox at 07_file_janitor/sandbox/ has old/new files,
a nested directory, and a .log file to experiment with.

Verify with:  python3 main.py verify 7
""",
    hints=[
        "Path.rglob(pattern) does the recursive glob; Path.stat().st_mtime gives the timestamp.",
        "cutoff = time.time() - days * 86400; compare mtime < cutoff.",
        "path.relative_to(root) produces the clean path for your output line.",
        "Use --apply as a store_true flag; never delete in dry-run mode.",
    ],
    solution={"janitor.py": M07_SOLUTION},
    setup=setup_m07,
    check=check_m07,
)


# ---------------------------------------------------------------------------
# Mission 08 — Safe reader
# ---------------------------------------------------------------------------
def setup_m08(mdir: Path) -> None:
    fixtures = mdir / "fixtures"
    if not fixtures.exists():
        fixtures.mkdir(parents=True)
        write_file(
            fixtures / "good.csv",
            "host,port,role\nweb01,22,web\nweb02,443,web\n",
        )
        write_file(
            fixtures / "bad.csv",
            "host,port,role\nweb01,22,web\nweb02,443\n",
        )
        locked = write_file(fixtures / "locked.csv", "host,port,role\n")
        locked.chmod(0o000)


M08_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Read a host inventory CSV without ever dumping a traceback.\"\"\"
import csv
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: safe_read.py <file.csv>", file=sys.stderr)
        return 2
    path = sys.argv[1]
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            try:
                header = next(reader)
            except StopIteration:
                print(f"ERROR: malformed row 1: empty file", file=sys.stderr)
                return 4
            if header != ["host", "port", "role"]:
                print(
                    "ERROR: malformed row 1: expected header host,port,role",
                    file=sys.stderr,
                )
                return 4
            count = 0
            for line_no, row in enumerate(reader, start=2):
                if not row:
                    continue
                if len(row) != 3:
                    print(
                        f"ERROR: malformed row {line_no}: expected 3 fields, got {len(row)}",
                        file=sys.stderr,
                    )
                    return 4
                count += 1
    except FileNotFoundError:
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2
    except PermissionError:
        print(f"ERROR: permission denied: {path}", file=sys.stderr)
        return 3
    except OSError as exc:
        print(f"ERROR: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    print(f"OK: {count} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""


def check_m08(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "safe_read.py"
    checks.append(Check("safe_read.py exists", script.is_file(), str(script)))
    if not script.is_file():
        return checks

    verify = fresh_dir(mdir / "_verify")
    good = write_file(
        verify / "good.csv", "host,port,role\nweb01,22,web\nweb02,443,web\n"
    )
    bad = write_file(
        verify / "bad.csv", "host,port,role\nweb01,22,web\nweb02,443\n"
    )
    locked = write_file(verify / "locked.csv", "host,port,role\n")
    locked.chmod(0o000)

    ok = run_script(script, good, cwd=mdir, timeout=10)
    checks.append(
        Check(
            "valid file: exits 0 and prints OK: 2 records",
            ok.returncode == 0
            and "OK: 2 records" in ok.stdout
            and no_traceback(ok),
            output(ok),
        )
    )

    missing = run_script(script, verify / "missing.csv", cwd=mdir, timeout=10)
    checks.append(
        Check(
            "missing file: exits 2, says file not found, no traceback",
            missing.returncode == 2
            and "file not found" in missing.stderr.lower()
            and no_traceback(missing),
            output(missing),
        )
    )

    malformed = run_script(script, bad, cwd=mdir, timeout=10)
    checks.append(
        Check(
            "malformed CSV: exits 4 and names row 3 / 2 fields",
            malformed.returncode == 4
            and "row 3" in malformed.stderr
            and "got 2" in malformed.stderr
            and no_traceback(malformed),
            output(malformed),
        )
    )

    if os.geteuid() == 0:
        checks.append(
            Check(
                "permission denied: skipped (running as root)",
                True,
                "Root bypasses file permissions, so this case cannot be tested.",
            )
        )
    elif not os.access(locked, os.R_OK):
        denied = run_script(script, locked, cwd=mdir, timeout=10)
        checks.append(
            Check(
                "permission denied: exits 3, says permission denied, no traceback",
                denied.returncode == 3
                and "permission denied" in denied.stderr.lower()
                and no_traceback(denied),
                output(denied),
            )
        )
    else:
        checks.append(
            Check(
                "permission denied: could not create an unreadable file",
                False,
                "This filesystem does not enforce Unix permissions; move the lab.",
            )
        )

    empty = write_file(verify / "empty.csv", "")
    empty_proc = run_script(script, empty, cwd=mdir, timeout=10)
    checks.append(
        Check(
            "empty file is handled without a traceback",
            empty_proc.returncode == 4 and no_traceback(empty_proc),
            output(empty_proc),
        )
    )
    return checks


M08 = Mission(
    id="m08",
    num=8,
    dir_name="08_safe_reader",
    title="Exceptions: read files without crashing",
    domain="Linux+ 4.3 Troubleshooting methodology",
    brief="""\
MISSION 08 — Safe reader

Create:

    08_safe_reader/safe_read.py

Usage:
    python3 safe_read.py <file.csv>

The CSV header must be exactly:  host,port,role

Behaviour and exit codes:
  * Valid file with N data rows:
        stdout: OK: N records        exit 0
  * File does not exist:
        stderr: ERROR: file not found: <path>        exit 2
  * Permission denied:
        stderr: ERROR: permission denied: <path>     exit 3
  * Any malformed row (wrong field count, including a bad header):
        stderr: ERROR: malformed row <line number>: expected 3 fields, got <n>
        exit 4
  * An empty file is malformed (row 1) and exits 4.
  * A traceback is always a failure. Catch expected OSErrors explicitly.

Sample fixtures (one unreadable) are in 08_safe_reader/fixtures/.

Verify with:  python3 main.py verify 8
""",
    hints=[
        "Catch FileNotFoundError and PermissionError separately, before OSError.",
        "csv.reader(fh) yields lists; enumerate(reader, start=2) numbers data rows.",
        "The header is line 1; the first data row is line 2.",
        "Use sys.exit(code) or return an int from main().",
    ],
    solution={"safe_read.py": M08_SOLUTION},
    setup=setup_m08,
    check=check_m08,
)


# ---------------------------------------------------------------------------
# Mission 09 — Network parser
# ---------------------------------------------------------------------------
SS_SAMPLE = """\
Netid State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process
udp   UNCONN 0      0      0.0.0.0:68         0.0.0.0:*     users:((\"dhclient\",pid=1234,fd=6))
tcp   LISTEN 0      128    0.0.0.0:22         0.0.0.0:*     users:((\"sshd\",pid=567,fd=3))
tcp   LISTEN 0      128    [::]:22            [::]:*        users:((\"sshd\",pid=567,fd=4))
tcp   LISTEN 0      128    127.0.0.1:631      0.0.0.0:*     users:((\"cupsd\",pid=890,fd=7))
tcp   ESTAB  0      0      192.0.2.10:22      192.0.2.20:54321 users:((\"sshd\",pid=567,fd=5))
udp   UNCONN 0      0      [::]:546           [::]:*        users:((\"dhclient\",pid=1234,fd=9))
tcp   LISTEN 0      4096   0.0.0.0:111        0.0.0.0:*     users:((\"rpcbind\",pid=500,fd=4))
"""

IP_SAMPLE = """\
1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever preferred_lft forever
1: lo    inet6 ::1/128 scope host \\       valid_lft forever preferred_lft forever
2: eth0    inet 192.168.1.10/24 brd 192.168.1.255 scope global dynamic eth0\\       valid_lft 86390sec preferred_lft 86390sec
2: eth0    inet6 fe80::1c2b:3aff:fe4d:5e6f/64 scope link \\       valid_lft forever preferred_lft forever
3: wlan0    inet 10.0.0.5/16 brd 10.0.255.255 scope global wlan0\\       valid_lft forever preferred_lft forever
"""


def setup_m09(mdir: Path) -> None:
    fixtures = mdir / "fixtures"
    if not fixtures.exists():
        write_file(fixtures / "ss.txt", SS_SAMPLE)
        write_file(fixtures / "ip_addr.txt", IP_SAMPLE)


M09_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Parse saved `ss -tuln` and `ip -o addr show` output as JSON.\"\"\"
import json
import re
import sys

SS_RE = re.compile(
    r"^(tcp|udp)\\s+(LISTEN|UNCONN)\\s+\\d+\\s+\\d+\\s+(\\S+):(\\d+)\\s+\\S+\\s*(.*)$"
)
PROC_RE = re.compile(r'users:\\(\\(\"([^\"]+)\"')
IP_RE = re.compile(
    r"^\\d+:\\s+(\\S+)\\s+(inet6?)\\s+([0-9a-fA-F:.]+)/(\\d+)\\s"
)


def parse_ss(path: str) -> list[dict]:
    sockets = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            match = SS_RE.match(line.rstrip("\\n"))
            if not match:
                continue
            proto, _state, address, port, rest = match.groups()
            proc = PROC_RE.search(rest)
            sockets.append(
                {
                    "proto": proto,
                    "local_address": address,
                    "port": int(port),
                    "process": proc.group(1) if proc else "",
                }
            )
    sockets.sort(key=lambda s: (s["proto"], s["port"], s["local_address"]))
    return sockets


def parse_ip(path: str) -> list[dict]:
    addresses = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            match = IP_RE.match(line)
            if not match:
                continue
            iface, family, address, prefix = match.groups()
            addresses.append(
                {
                    "iface": iface,
                    "family": family,
                    "address": address,
                    "prefix": int(prefix),
                }
            )
    addresses.sort(key=lambda a: (a["iface"], a["family"], a["address"]))
    return addresses


def main() -> int:
    scope = {"ss": parse_ss, "ip": parse_ip}
    if len(sys.argv) != 3 or sys.argv[1] not in scope:
        print("usage: netparse.py {ss|ip} <saved-output-file>", file=sys.stderr)
        return 2
    try:
        data = scope[sys.argv[1]](sys.argv[2])
    except OSError as exc:
        print(f"ERROR: cannot read {sys.argv[2]}: {exc}", file=sys.stderr)
        return 2
    json.dump(data, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""


def check_m09(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "netparse.py"
    checks.append(Check("netparse.py exists", script.is_file(), str(script)))
    if not script.is_file():
        return checks

    verify = fresh_dir(mdir / "_verify")
    ss_file = write_file(verify / "ss.txt", SS_SAMPLE)
    ip_file = write_file(verify / "ip.txt", IP_SAMPLE)

    ss_proc = run_script(script, "ss", ss_file, cwd=mdir, timeout=10)
    ss_data, ss_err = parse_json(ss_proc)
    expected_ss = [
        {"proto": "tcp", "local_address": "0.0.0.0", "port": 22, "process": "sshd"},
        {"proto": "tcp", "local_address": "[::]", "port": 22, "process": "sshd"},
        {"proto": "tcp", "local_address": "0.0.0.0", "port": 111, "process": "rpcbind"},
        {"proto": "tcp", "local_address": "127.0.0.1", "port": 631, "process": "cupsd"},
        {"proto": "udp", "local_address": "0.0.0.0", "port": 68, "process": "dhclient"},
        {"proto": "udp", "local_address": "[::]", "port": 546, "process": "dhclient"},
    ]
    checks.append(
        Check(
            "ss mode: exits 0 and emits valid JSON",
            ss_proc.returncode == 0 and ss_data is not None,
            output(ss_proc) if ss_data is None else "",
        )
    )
    checks.append(
        Check(
            "ss mode: finds exactly the listening sockets, sorted",
            ss_data == expected_ss,
            ss_err or f"got {ss_data!r}",
        )
    )

    ip_proc = run_script(script, "ip", ip_file, cwd=mdir, timeout=10)
    ip_data, ip_err = parse_json(ip_proc)
    expected_ip = [
        {"iface": "eth0", "family": "inet", "address": "192.168.1.10", "prefix": 24},
        {
            "iface": "eth0",
            "family": "inet6",
            "address": "fe80::1c2b:3aff:fe4d:5e6f",
            "prefix": 64,
        },
        {"iface": "lo", "family": "inet", "address": "127.0.0.1", "prefix": 8},
        {"iface": "lo", "family": "inet6", "address": "::1", "prefix": 128},
        {"iface": "wlan0", "family": "inet", "address": "10.0.0.5", "prefix": 16},
    ]
    checks.append(
        Check(
            "ip mode: exits 0 and emits valid JSON",
            ip_proc.returncode == 0 and ip_data is not None,
            output(ip_proc) if ip_data is None else "",
        )
    )
    checks.append(
        Check(
            "ip mode: parses all five addresses with prefixes",
            ip_data == expected_ip,
            ip_err or f"got {ip_data!r}",
        )
    )

    bad = run_script(script, "ss", verify / "missing.txt", cwd=mdir, timeout=10)
    checks.append(
        Check(
            "missing file exits 2 cleanly",
            bad.returncode == 2
            and "Traceback" not in bad.stderr
            and bad.stderr.strip() != "",
            output(bad),
        )
    )

    usage = run_script(script, "bogus", ss_file, cwd=mdir, timeout=10)
    checks.append(
        Check(
            "unknown mode exits 2",
            usage.returncode == 2,
            output(usage),
        )
    )
    return checks


M09 = Mission(
    id="m09",
    num=9,
    dir_name="09_netparse",
    title="Regex: parse ss and ip output",
    domain="Linux+ 4.4 Network troubleshooting",
    brief="""\
MISSION 09 — Network parser

Create:

    09_netparse/netparse.py

Usage:
    python3 netparse.py ss <saved-ss-output>
    python3 netparse.py ip <saved-ip-output>

SS MODE parses `ss -tuln`-style lines. Keep only LISTEN and UNCONN sockets.
Print a JSON array, sorted by (proto, port, local_address):
    {"proto": "tcp", "local_address": "0.0.0.0", "port": 22,
     "process": "sshd"}
Use "" when the process name is unavailable. Ignore ESTAB and other states.

IP MODE parses `ip -o addr show`-style lines into:
    {"iface": "eth0", "family": "inet", "address": "192.168.1.10",
     "prefix": 24}
family is "inet" or "inet6". Sort by (iface, family, address).

Both modes exit 0; a missing file or unknown mode exits 2 with stderr.
Samples are in 09_netparse/fixtures/.

Verify with:  python3 main.py verify 9
""",
    hints=[
        "Addresses can be 0.0.0.0, 127.0.0.1, or [::]; capture them as \\S+ and split off the port.",
        "ss columns are fixed-ish: state, recv-q, send-q, local, peer, process. A regex with named groups is clearest.",
        "Process: users:((\"sshd\",pid=...)). Match the quoted name after users:((.",
        "ip output: '2: eth0    inet 192.168.1.10/24 brd ...' — capture iface, family, address, prefix.",
    ],
    solution={"netparse.py": M09_SOLUTION},
    setup=setup_m09,
    check=check_m09,
)


MISSIONS = [M05, M06, M07, M08, M09]
