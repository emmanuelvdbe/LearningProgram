"""Part 3 — Talking to the Linux system (missions 10-13)."""
from __future__ import annotations

import json
import os
import socket
import stat
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

# ---------------------------------------------------------------------------
# Mission 10 — Healthcheck runner
# ---------------------------------------------------------------------------
M10_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Run a JSON list of commands and produce a machine-readable report.\"\"\"
import argparse
import json
import subprocess
import sys
import time


def run_one(spec: dict) -> dict:
    name = spec.get("name", "unnamed")
    cmd = spec.get("cmd", [])
    expect = int(spec.get("expect", 0))
    timeout = float(spec.get("timeout", 5))

    started = time.perf_counter()
    returncode = None
    stdout = ""
    stderr = ""
    timed_out = False
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        returncode = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        stderr += f"\\n[timed out after {timeout}s]"
    except FileNotFoundError as exc:
        stderr = f"command not found: {exc}"
    except OSError as exc:
        stderr = f"could not run command: {exc}"

    duration_ms = int((time.perf_counter() - started) * 1000)
    ok = (not timed_out) and returncode == expect
    return {
        "name": name,
        "returncode": returncode,
        "ok": ok,
        "timed_out": timed_out,
        "stdout": stdout,
        "stderr": stderr,
        "duration_ms": duration_ms,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="healthcheck")
    parser.add_argument("checks", help="JSON file with a list of checks")
    parser.add_argument("--out", default="report.json", help="report path")
    args = parser.parse_args()

    try:
        with open(args.checks, encoding="utf-8") as fh:
            specs = json.load(fh)
    except FileNotFoundError:
        print(f"ERROR: checks file not found: {args.checks}", file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read checks: {exc}", file=sys.stderr)
        return 2

    if not isinstance(specs, list):
        print("ERROR: checks file must contain a JSON list", file=sys.stderr)
        return 2

    results = [run_one(spec) for spec in specs]
    passed = sum(1 for r in results if r["ok"])
    failed = len(results) - passed
    report = {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": results,
    }
    try:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
    except OSError as exc:
        print(f"ERROR: cannot write report: {exc}", file=sys.stderr)
        return 2
    print(f"{passed} passed, {failed} failed -> {args.out}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
"""


def check_m10(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "healthcheck.py"
    checks.append(Check("healthcheck.py exists", script.is_file(), str(script)))
    if not script.is_file():
        return checks

    verify = fresh_dir(mdir / "_verify")
    checks_file = write_file(
        verify / "checks.json",
        json.dumps(
            [
                {
                    "name": "ok",
                    "cmd": ["python3", "-c", "import sys; sys.exit(0)"],
                    "expect": 0,
                    "timeout": 5,
                },
                {
                    "name": "bad",
                    "cmd": ["python3", "-c", "import sys; sys.exit(3)"],
                    "expect": 0,
                    "timeout": 5,
                },
                {"name": "echo", "cmd": ["sh", "-c", "echo linux"], "timeout": 5},
                {
                    "name": "missing",
                    "cmd": ["definitely-not-a-real-command-xyz"],
                    "timeout": 5,
                },
                {
                    "name": "slow",
                    "cmd": ["python3", "-c", "import time; time.sleep(3)"],
                    "timeout": 0.5,
                },
            ]
        ),
    )
    report = verify / "report.json"
    proc = run_script(script, checks_file, "--out", report, cwd=mdir, timeout=30)
    checks.append(
        Check(
            "mixed batch exits 1 (some checks fail)",
            proc.returncode == 1 and no_traceback(proc),
            output(proc),
        )
    )
    checks.append(
        Check("writes the report file", report.is_file(), f"missing {report}")
    )
    if not report.is_file():
        return checks

    try:
        data = json.loads(report.read_text(encoding="utf-8"))
        by_name = {item["name"]: item for item in data["checks"]}
    except Exception as exc:
        checks.append(Check("report is valid JSON with checks", False, str(exc)))
        return checks
    checks.append(Check("report is valid JSON with checks", True, ""))

    checks.append(
        Check(
            "summary counts are 2 passed / 3 failed",
            data.get("passed") == 2
            and data.get("failed") == 3
            and data.get("ok") is False,
            f"passed={data.get('passed')} failed={data.get('failed')} ok={data.get('ok')}",
        )
    )
    checks.append(
        Check(
            "successful check is marked ok",
            by_name.get("ok", {}).get("ok") is True
            and by_name.get("ok", {}).get("returncode") == 0,
            f"{by_name.get('ok')}",
        )
    )
    checks.append(
        Check(
            "non-zero exit is failure with the real return code",
            by_name.get("bad", {}).get("ok") is False
            and by_name.get("bad", {}).get("returncode") == 3,
            f"{by_name.get('bad')}",
        )
    )
    checks.append(
        Check(
            "stdout is captured",
            "linux" in by_name.get("echo", {}).get("stdout", ""),
            f"{by_name.get('echo')}",
        )
    )
    checks.append(
        Check(
            "missing command is handled (returncode null, no crash)",
            by_name.get("missing", {}).get("ok") is False
            and by_name.get("missing", {}).get("returncode") is None
            and by_name.get("missing", {}).get("stderr", "").strip() != "",
            f"{by_name.get('missing')}",
        )
    )
    checks.append(
        Check(
            "timeout is detected and reported",
            by_name.get("slow", {}).get("ok") is False
            and by_name.get("slow", {}).get("timed_out") is True,
            f"{by_name.get('slow')}",
        )
    )
    checks.append(
        Check(
            "duration_ms is recorded for every check",
            all(
                isinstance(item.get("duration_ms"), int) and item["duration_ms"] >= 0
                for item in data["checks"]
            ),
            f"{[item.get('duration_ms') for item in data['checks']]}",
        )
    )

    good_file = write_file(
        verify / "good.json",
        json.dumps(
            [{"name": "ok", "cmd": ["python3", "-c", "raise SystemExit(0)"], "expect": 0}]
        ),
    )
    good_report = verify / "good-report.json"
    good = run_script(script, good_file, "--out", good_report, cwd=mdir, timeout=15)
    good_data = {}
    if good_report.is_file():
        good_data = json.loads(good_report.read_text(encoding="utf-8"))
    checks.append(
        Check(
            "all-passing batch exits 0 with ok=true",
            good.returncode == 0 and good_data.get("ok") is True,
            output(good),
        )
    )

    missing = run_script(script, verify / "nope.json", cwd=mdir, timeout=10)
    checks.append(
        Check(
            "missing checks file exits 2 cleanly",
            missing.returncode == 2
            and "Traceback" not in missing.stderr
            and missing.stderr.strip() != "",
            output(missing),
        )
    )
    return checks


M10 = Mission(
    id="m10",
    num=10,
    dir_name="10_healthcheck",
    title="subprocess: run commands and capture the truth",
    domain="Linux+ 3.1 Scripting / 4.3 Troubleshooting",
    brief="""\
MISSION 10 — Healthcheck runner

Create:

    10_healthcheck/healthcheck.py

Usage:
    python3 healthcheck.py <checks.json> [--out report.json]

The input is a JSON list of checks:
    [{"name": "ssh", "cmd": ["systemctl", "is-active", "ssh"],
      "expect": 0, "timeout": 5}, ...]

For every check run the command with subprocess.run(..., shell=False,
capture_output=True, text=True, timeout=...). Produce:

    {
      "ok": false,
      "passed": 2,
      "failed": 3,
      "checks": [
        {"name": "ssh", "returncode": 0, "ok": true,
         "timed_out": false, "stdout": "...", "stderr": "...",
         "duration_ms": 12}
      ]
    }

Rules:
  * ok = (not timed_out) and returncode == expect (expect defaults to 0).
  * A missing command is a failure: returncode null, stderr explains it.
  * A timeout is a failure with timed_out true.
  * Exit 0 only if every check passed; otherwise exit 1.
  * Missing/unreadable checks file exits 2 with a clean stderr message.

This is the core pattern behind Ansible-style modules and monitoring agents.

Verify with:  python3 main.py verify 10
""",
    hints=[
        "subprocess.run(cmd, capture_output=True, text=True, timeout=timeout) returns CompletedProcess.",
        "Catch subprocess.TimeoutExpired and FileNotFoundError around each command, not around the whole loop.",
        "time.perf_counter() before/after gives a monotonic duration in seconds.",
        "Never use shell=True with data from a file; pass the argv list directly.",
    ],
    solution={"healthcheck.py": M10_SOLUTION},
    check=check_m10,
)


# ---------------------------------------------------------------------------
# Mission 11 — Permission audit
# ---------------------------------------------------------------------------
M11_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Audit a tree for dangerous Unix permission bits.\"\"\"
import argparse
import json
import os
import stat
import sys


def scan(root: str) -> dict:
    findings = {
        "world_writable": [],
        "suid": [],
        "sgid": [],
        "unreadable": [],
    }
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                info = os.lstat(path)
            except OSError:
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            mode = stat.S_IMODE(info.st_mode)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            entry = {"path": rel, "mode": f"{mode:04o}"}
            if mode & stat.S_IWOTH:
                findings["world_writable"].append(entry)
            if mode & stat.S_ISUID:
                findings["suid"].append(entry)
            if mode & stat.S_ISGID:
                findings["sgid"].append(entry)
            if not os.access(path, os.R_OK):
                findings["unreadable"].append(entry)

    for values in findings.values():
        values.sort(key=lambda entry: entry["path"])
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(prog="audit_perms")
    parser.add_argument("directory", help="tree to audit")
    args = parser.parse_args()
    if not os.path.isdir(args.directory):
        print(f"ERROR: directory not found: {args.directory}", file=sys.stderr)
        return 2
    json.dump(scan(args.directory), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""


def _chmod_fixture(path: Path, mode: int) -> None:
    path.write_text(f"fixture {path.name}\n", encoding="utf-8")
    path.chmod(mode)


def check_m11(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "audit_perms.py"
    checks.append(Check("audit_perms.py exists", script.is_file(), str(script)))
    if not script.is_file():
        return checks

    verify = fresh_dir(mdir / "_verify")
    tree = verify / "tree"
    (tree / "sub").mkdir(parents=True)
    _chmod_fixture(tree / "world.txt", 0o666)
    _chmod_fixture(tree / "ww_exec.sh", 0o777)
    _chmod_fixture(tree / "suid.bin", 0o4755)
    _chmod_fixture(tree / "sgid.bin", 0o2755)
    _chmod_fixture(tree / "locked.txt", 0o000)
    _chmod_fixture(tree / "normal.txt", 0o644)
    _chmod_fixture(tree / "sub" / "nested.txt", 0o666)

    if stat.S_IMODE((tree / "world.txt").stat().st_mode) != 0o666:
        return checks + [
            Check(
                "filesystem stores Unix permission bits",
                False,
                "chmod did not stick. Move the lab (LINUXPLUS_LAB) to ext4/xfs/btrfs.",
            )
        ]

    proc = run_script(script, tree, cwd=mdir, timeout=15)
    checks.append(Check("exits 0 on a valid tree", proc.returncode == 0, output(proc)))
    data, error = parse_json(proc)
    if data is None:
        checks.append(Check("prints valid JSON", False, error))
        return checks
    checks.append(Check("prints valid JSON", True, ""))

    checks.append(
        Check(
            "world_writable findings are exact, sorted, with modes",
            data.get("world_writable")
            == [
                {"path": "sub/nested.txt", "mode": "0666"},
                {"path": "world.txt", "mode": "0666"},
                {"path": "ww_exec.sh", "mode": "0777"},
            ],
            f"got {data.get('world_writable')!r}",
        )
    )
    checks.append(
        Check(
            "SUID finding is exact",
            data.get("suid") == [{"path": "suid.bin", "mode": "4755"}],
            f"got {data.get('suid')!r}",
        )
    )
    checks.append(
        Check(
            "SGID finding is exact",
            data.get("sgid") == [{"path": "sgid.bin", "mode": "2755"}],
            f"got {data.get('sgid')!r}",
        )
    )
    if os.geteuid() == 0:
        checks.append(
            Check(
                "unreadable findings: skipped (running as root)",
                True,
                "Root can read everything, so the unreadable check is empty.",
            )
        )
    else:
        checks.append(
            Check(
                "unreadable finding is exact",
                data.get("unreadable")
                == [{"path": "locked.txt", "mode": "0000"}],
                f"got {data.get('unreadable')!r}",
            )
        )

    missing = run_script(script, verify / "nope", cwd=mdir, timeout=10)
    checks.append(
        Check(
            "missing directory exits 2 cleanly",
            missing.returncode == 2 and no_traceback(missing),
            output(missing),
        )
    )
    return checks


M11 = Mission(
    id="m11",
    num=11,
    dir_name="11_permission_audit",
    title="os.stat and bitmasks: permission audit",
    domain="Linux+ 2.1 Security / file permissions",
    brief="""\
MISSION 11 — Permission audit

Create:

    11_permission_audit/audit_perms.py

Usage:
    python3 audit_perms.py <directory>

Recursively scan regular files (skip directories and symlinks) and print JSON:

    {
      "world_writable": [{"path": "sub/nested.txt", "mode": "0666"}],
      "suid":           [{"path": "suid.bin", "mode": "4755"}],
      "sgid":           [{"path": "sgid.bin", "mode": "2755"}],
      "unreadable":     [{"path": "locked.txt", "mode": "0000"}]
    }

Rules:
  * "path" is relative to the scanned directory, using / separators.
  * "mode" is four octal digits including special bits (0666, 4755, 0000).
  * world_writable: mode & 0o002
  * suid:           mode & 0o4000      sgid: mode & 0o2000
  * unreadable: not os.access(path, os.R_OK)
  * Sort every list by path.
  * A missing directory exits 2 with an error on stderr.

This is the logic behind `find / -perm -0002` and most hardening audits.

Verify with:  python3 main.py verify 11
""",
    hints=[
        "os.walk(root) yields (dirpath, dirnames, filenames); build os.path.join(dirpath, name).",
        "Use os.lstat + stat.S_ISREG to skip symlinks and directories.",
        "mode = stat.S_IMODE(info.st_mode) strips the file-type bits; format with f'{mode:04o}'.",
        "Bitwise tests: mode & stat.S_IWOTH, mode & stat.S_ISUID, mode & stat.S_ISGID.",
        "os.path.relpath(path, root).replace(os.sep, '/') gives stable relative paths.",
    ],
    solution={"audit_perms.py": M11_SOLUTION},
    check=check_m11,
)


# ---------------------------------------------------------------------------
# Mission 12 — Port checker
# ---------------------------------------------------------------------------
M12_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Check TCP ports and report OPEN/CLOSED; exit non-zero if any are closed.\"\"\"
import argparse
import socket
import sys


def check_port(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(prog="portcheck")
    parser.add_argument("host", help="hostname or IP")
    parser.add_argument("ports", nargs="+", type=int, help="TCP ports")
    parser.add_argument("--timeout", type=float, default=1.0, help="seconds")
    args = parser.parse_args()

    for port in args.ports:
        if not 1 <= port <= 65535:
            parser.error(f"port out of range: {port}")

    all_open = True
    for port in args.ports:
        is_open = check_port(args.host, port, args.timeout)
        print(f"{'OPEN' if is_open else 'CLOSED'} {port}")
        all_open = all_open and is_open
    return 0 if all_open else 1


if __name__ == "__main__":
    sys.exit(main())
"""


def check_m12(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "portcheck.py"
    checks.append(Check("portcheck.py exists", script.is_file(), str(script)))
    if not script.is_file():
        return checks

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind(("127.0.0.1", 0))
        server.listen(8)
        open_port = server.getsockname()[1]

        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
        probe.close()
        probe = None

        mixed = run_script(
            script, "127.0.0.1", open_port, closed_port, cwd=mdir, timeout=15
        )
        checks.append(
            Check(
                "mixed ports: exits 1, reports OPEN and CLOSED",
                mixed.returncode == 1
                and f"OPEN {open_port}" in mixed.stdout
                and f"CLOSED {closed_port}" in mixed.stdout,
                output(mixed),
            )
        )

        only_open = run_script(script, "127.0.0.1", open_port, cwd=mdir, timeout=15)
        checks.append(
            Check(
                "open port only: exits 0",
                only_open.returncode == 0
                and f"OPEN {open_port}" in only_open.stdout,
                output(only_open),
            )
        )

        bad = run_script(script, "127.0.0.1", "not-a-port", cwd=mdir, timeout=10)
        checks.append(
            Check(
                "invalid port exits 2 via argparse",
                bad.returncode == 2 and no_traceback(bad),
                output(bad),
            )
        )

        timeout_proc = run_script(
            script, "192.0.2.1", "9", "--timeout", "0.2", cwd=mdir, timeout=10
        )
        checks.append(
            Check(
                "unreachable address becomes CLOSED without hanging",
                timeout_proc.returncode == 1
                and "CLOSED 9" in timeout_proc.stdout,
                output(timeout_proc),
            )
        )
    finally:
        server.close()
        if probe is not None:
            probe.close()
    return checks


M12 = Mission(
    id="m12",
    num=12,
    dir_name="12_portcheck",
    title="Sockets: build a TCP port checker",
    domain="Linux+ 4.4 Network troubleshooting",
    brief="""\
MISSION 12 — Port checker

Create:

    12_portcheck/portcheck.py

Usage:
    python3 portcheck.py <host> <port> [port ...] [--timeout SECONDS]

Behaviour:
  * Try a TCP connection to each port (socket.create_connection).
  * Print one line per port, in argument order:
        OPEN 22
        CLOSED 8080
  * Exit 0 if every port is open, otherwise exit 1.
  * Invalid ports (non-numeric or outside 1..65535) exit 2.
  * --timeout defaults to 1.0 seconds and must actually be used.

Important: close connections with a context manager, and treat refused
connections / timeouts as CLOSED rather than crashing. This is the same
pattern used by health checks and monitoring probes.

Verify with:  python3 main.py verify 12
""",
    hints=[
        "socket.create_connection((host, port), timeout=timeout) raises OSError on failure.",
        "A `with socket.create_connection(...)` block closes the socket automatically.",
        "Check every result, not just the first: all_open = all_open and is_open.",
        "argparse type=int gives you a clean exit 2 for non-numeric ports.",
    ],
    solution={"portcheck.py": M12_SOLUTION},
    check=check_m12,
)


# ---------------------------------------------------------------------------
# Mission 13 — systemd unit inspector
# ---------------------------------------------------------------------------
M13_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Validate and summarise a systemd .service unit file.\"\"\"
import argparse
import configparser
import json
import sys
from pathlib import Path

ALLOWED_RESTART = {"no", "on-success", "on-failure", "always"}


def inspect(path: Path) -> dict:
    parser = configparser.ConfigParser(
        interpolation=None, allow_no_value=True, strict=False
    )
    with path.open(encoding="utf-8") as fh:
        parser.read_file(fh)

    errors: list[str] = []
    if not parser.has_section("Unit") or not parser.get(
        "Unit", "Description", fallback=""
    ).strip():
        errors.append("Missing [Unit] Description")

    exec_start = parser.get("Service", "ExecStart", fallback="").strip()
    if not parser.has_section("Service") or not exec_start:
        errors.append("Missing [Service] ExecStart")

    restart = parser.get("Service", "Restart", fallback="").strip()
    if restart and restart not in ALLOWED_RESTART:
        errors.append(
            f"Invalid Restart value: {restart} (allowed: {', '.join(sorted(ALLOWED_RESTART))})"
        )

    wanted_by = parser.get("Install", "WantedBy", fallback="").split()
    name = path.name[: -len(".service")] if path.name.endswith(".service") else path.stem
    return {
        "valid": not errors,
        "errors": errors,
        "name": name,
        "description": parser.get("Unit", "Description", fallback="").strip() or None,
        "exec_start": exec_start or None,
        "user": parser.get("Service", "User", fallback="").strip() or None,
        "restart": restart or None,
        "wanted_by": wanted_by,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="unit_inspect")
    parser.add_argument("unit", help="path to a .service file")
    args = parser.parse_args()
    path = Path(args.unit)
    try:
        report = inspect(path)
    except FileNotFoundError:
        print(f"ERROR: unit file not found: {path}", file=sys.stderr)
        return 2
    except (OSError, configparser.Error) as exc:
        print(f"ERROR: cannot parse {path}: {exc}", file=sys.stderr)
        return 1
    json.dump(report, sys.stdout, indent=2)
    print()
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
"""


VALID_UNIT = """\
[Unit]
Description=Nightly backup

[Service]
Type=simple
User=backup
ExecStart=/usr/local/bin/backup.py /srv /var/backups
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""

MISSING_EXEC_UNIT = """\
[Unit]
Description=Broken service

[Service]
Type=simple
User=root
"""

BAD_RESTART_UNIT = """\
[Unit]
Description=Bad restart policy

[Service]
Type=simple
ExecStart=/usr/bin/true
Restart=sometimes

[Install]
WantedBy=multi-user.target
"""


def check_m13(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "unit_inspect.py"
    checks.append(Check("unit_inspect.py exists", script.is_file(), str(script)))
    if not script.is_file():
        return checks

    verify = fresh_dir(mdir / "_verify")
    valid = write_file(verify / "backup.service", VALID_UNIT)
    missing = write_file(verify / "missing.service", MISSING_EXEC_UNIT)
    bad_restart = write_file(verify / "bad.service", BAD_RESTART_UNIT)

    proc = run_script(script, valid, cwd=mdir, timeout=10)
    data, error = parse_json(proc)
    checks.append(
        Check(
            "valid unit: exits 0 and prints JSON",
            proc.returncode == 0 and data is not None,
            output(proc) if data is None else error,
        )
    )
    if isinstance(data, dict):
        expected = {
            "valid": True,
            "errors": [],
            "name": "backup",
            "description": "Nightly backup",
            "exec_start": "/usr/local/bin/backup.py /srv /var/backups",
            "user": "backup",
            "restart": "on-failure",
            "wanted_by": ["multi-user.target"],
        }
        for key, value in expected.items():
            checks.append(
                Check(
                    f"valid unit: {key} is correct",
                    data.get(key) == value,
                    f"got {data.get(key)!r}, expected {value!r}",
                )
            )
    else:
        checks.append(Check("valid unit: JSON object", False, "not an object"))

    missing_proc = run_script(script, missing, cwd=mdir, timeout=10)
    missing_data, _ = parse_json(missing_proc)
    checks.append(
        Check(
            "missing ExecStart: exits 1 and reports the error",
            missing_proc.returncode == 1
            and isinstance(missing_data, dict)
            and missing_data.get("valid") is False
            and any("ExecStart" in e for e in missing_data.get("errors", [])),
            output(missing_proc),
        )
    )

    restart_proc = run_script(script, bad_restart, cwd=mdir, timeout=10)
    restart_data, _ = parse_json(restart_proc)
    checks.append(
        Check(
            "bad Restart: exits 1 and reports the error",
            restart_proc.returncode == 1
            and isinstance(restart_data, dict)
            and any("Restart" in e for e in restart_data.get("errors", [])),
            output(restart_proc),
        )
    )

    absent = run_script(script, verify / "nope.service", cwd=mdir, timeout=10)
    checks.append(
        Check(
            "missing file exits 2 cleanly",
            absent.returncode == 2 and no_traceback(absent),
            output(absent),
        )
    )
    return checks


M13 = Mission(
    id="m13",
    num=13,
    dir_name="13_unit_inspector",
    title="Config formats: systemd unit inspector",
    domain="Linux+ 1.2 Services / systemd",
    brief="""\
MISSION 13 — systemd unit inspector

Create:

    13_unit_inspector/unit_inspect.py

Usage:
    python3 unit_inspect.py <unit.service>

Parse the INI-style unit with configparser (interpolation=None,
allow_no_value=True) and print JSON:

    {
      "valid": true,
      "errors": [],
      "name": "backup",
      "description": "Nightly backup",
      "exec_start": "/usr/local/bin/backup.py /srv /var/backups",
      "user": "backup",
      "restart": "on-failure",
      "wanted_by": ["multi-user.target"]
    }

Validation:
  * [Unit] must have a non-empty Description.
  * [Service] must have a non-empty ExecStart.
  * Restart, if present, must be one of:
        no, on-success, on-failure, always
  * wanted_by = [Install] WantedBy split on whitespace ([] if absent).
  * Missing optional values are null, not "".

Exit codes: 0 valid, 1 invalid unit, 2 file not found/unreadable.
Errors must name the offending key (ExecStart / Restart).

Verify with:  python3 main.py verify 13
""",
    hints=[
        "configparser lowercases keys internally; cp.get('Service', 'ExecStart', fallback='') still works.",
        "Set interpolation=None or a literal % in ExecStart will raise InterpolationSyntaxError.",
        "name = path.name.removesuffix('.service') (Python 3.9+).",
        "Collect errors in a list; valid is simply `not errors`.",
    ],
    solution={"unit_inspect.py": M13_SOLUTION},
    check=check_m13,
)


MISSIONS = [M10, M11, M12, M13]
