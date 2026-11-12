"""Part 4 — Production habits and the capstone (missions 14-16)."""
from __future__ import annotations

import json
import os
import stat
import tarfile
import time
from pathlib import Path

from .base import (
    Check,
    Mission,
    fresh_dir,
    no_traceback,
    output,
    parse_json,
    run_command,
    run_script,
    write_file,
)

# ---------------------------------------------------------------------------
# Mission 14 — Backup tool
# ---------------------------------------------------------------------------
M14_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Create timestamped .tar.gz backups and enforce a retention count.\"\"\"
import argparse
import logging
import sys
import tarfile
from datetime import datetime
from pathlib import Path


def make_logger(path: Path) -> logging.Logger:
    logger = logging.getLogger("linuxplus.backup")
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def main() -> int:
    parser = argparse.ArgumentParser(prog="backup")
    parser.add_argument("source", help="directory to archive")
    parser.add_argument("destination", help="directory for archives")
    parser.add_argument("--keep", type=int, default=5, help="archives to retain")
    parser.add_argument("--dry-run", action="store_true", help="show, do not write")
    parser.add_argument("--log", help="log file (default: <destination>/backup.log)")
    args = parser.parse_args()

    source = Path(args.source)
    destination = Path(args.destination)
    if not source.is_dir():
        print(f"ERROR: source directory not found: {source}", file=sys.stderr)
        return 2
    if args.keep < 1:
        print("ERROR: --keep must be at least 1", file=sys.stderr)
        return 2
    destination.mkdir(parents=True, exist_ok=True)
    log_path = Path(args.log) if args.log else destination / "backup.log"
    logger = make_logger(log_path)

    files = [path for path in sorted(source.rglob("*")) if path.is_file()]
    name = f"backup-{datetime.now():%Y%m%d-%H%M%S}.tar.gz"
    archive = destination / name

    if args.dry_run:
        print(f"WOULD ARCHIVE {len(files)} files from {source} to {archive}")
        return 0

    try:
        with tarfile.open(archive, "w:gz") as tar:
            for path in files:
                tar.add(path, arcname=str(path.relative_to(source)))
    except OSError as exc:
        print(f"ERROR: backup failed: {exc}", file=sys.stderr)
        return 1

    size = archive.stat().st_size
    logger.info("archived %d files to %s (%d bytes)", len(files), name, size)
    print(f"ARCHIVED {name} ({len(files)} files, {size} bytes)")

    archives = sorted(destination.glob("backup-*.tar.gz"), key=lambda p: p.name)
    while len(archives) > args.keep:
        old = archives.pop(0)
        try:
            old.unlink()
            logger.info("removed old archive %s (retention=%d)", old.name, args.keep)
        except OSError as exc:
            logger.error("could not remove %s: %s", old.name, exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""


def check_m14(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "backup.py"
    checks.append(Check("backup.py exists", script.is_file(), str(script)))
    if not script.is_file():
        return checks

    verify = fresh_dir(mdir / "_verify")
    source = verify / "src"
    (source / "sub").mkdir(parents=True)
    (source / "a.txt").write_text("v1", encoding="utf-8")
    (source / "sub" / "b.txt").write_text("bee", encoding="utf-8")
    dest = verify / "dest"

    first = run_script(script, source, dest, cwd=mdir, timeout=30)
    archives = sorted(dest.glob("backup-*.tar.gz"))
    checks.append(
        Check(
            "creates a timestamped archive",
            first.returncode == 0 and len(archives) == 1,
            output(first),
        )
    )
    if len(archives) != 1:
        return checks

    names = []
    with tarfile.open(archives[0], "r:gz") as tar:
        names = [name.lstrip("./") for name in tar.getnames()]
    checks.append(
        Check(
            "archive contains source files at relative paths",
            "a.txt" in names and "sub/b.txt" in names,
            f"members={names}",
        )
    )

    time.sleep(1.05)
    (source / "a.txt").write_text("v2", encoding="utf-8")
    second = run_script(script, source, dest, "--keep", "2", cwd=mdir, timeout=30)
    time.sleep(1.05)
    (source / "a.txt").write_text("v3", encoding="utf-8")
    third = run_script(script, source, dest, "--keep", "2", cwd=mdir, timeout=30)

    archives = sorted(dest.glob("backup-*.tar.gz"), key=lambda p: p.name)
    checks.append(
        Check(
            "retention keeps exactly --keep archives",
            second.returncode == 0 and third.returncode == 0 and len(archives) == 2,
            f"count={len(archives)}\n{output(second)}\n{output(third)}",
        )
    )

    contents = set()
    if len(archives) == 2:
        for archive in archives:
            with tarfile.open(archive, "r:gz") as tar:
                member = tar.extractfile("a.txt")
                if member is not None:
                    contents.add(member.read().decode("utf-8").strip())
    checks.append(
        Check(
            "retention removed the oldest backup, newest data is present",
            contents == {"v2", "v3"},
            f"a.txt contents in surviving archives: {sorted(contents)}",
        )
    )

    log = dest / "backup.log"
    log_text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    checks.append(
        Check(
            "writes INFO lines to the log file",
            log.is_file()
            and log_text.count("INFO") >= 3
            and "archived" in log_text.lower(),
            log_text[-500:] if log_text else "missing backup.log",
        )
    )

    before = len(list(dest.glob("backup-*.tar.gz")))
    dry = run_script(script, source, dest, "--dry-run", cwd=mdir, timeout=20)
    after = len(list(dest.glob("backup-*.tar.gz")))
    checks.append(
        Check(
            "--dry-run creates nothing and says WOULD",
            dry.returncode == 0
            and before == after
            and "WOULD" in dry.stdout.upper(),
            output(dry),
        )
    )

    missing = run_script(script, verify / "nope", dest, cwd=mdir, timeout=10)
    checks.append(
        Check(
            "missing source exits 2 cleanly",
            missing.returncode == 2
            and "Traceback" not in missing.stderr
            and missing.stderr.strip() != "",
            output(missing),
        )
    )
    return checks


M14 = Mission(
    id="m14",
    num=14,
    dir_name="14_backup_tool",
    title="Logging, tarfile, and retention: a real backup tool",
    domain="Linux+ 1.4 Storage / 3.3 Automation",
    brief="""\
MISSION 14 — Backup tool

Create:

    14_backup_tool/backup.py

Usage:
    python3 backup.py <source-dir> <dest-dir> [--keep N] [--dry-run] [--log FILE]

Behaviour:
  * Archive every regular file under <source-dir> into
        <dest-dir>/backup-YYYYmmdd-HHMMSS.tar.gz
    preserving paths relative to the source directory.
  * Use the tarfile module with "w:gz".
  * After a successful backup, keep only the newest N archives (default 5)
    matching backup-*.tar.gz; delete older ones.
  * Append an INFO line to <dest-dir>/backup.log (or --log FILE) using the
    logging module. It must include the archive name and file count.
  * --dry-run prints what would happen and creates nothing (no archive, no log).
  * A missing source directory exits 2 with an error on stderr.
  * Print ARCHIVED <name> (<n> files, <bytes> bytes) on success.

This is the “real tool” version of mission 7: idempotent, logged, bounded.

Verify with:  python3 main.py verify 14
""",
    hints=[
        "Path.rglob('*') + is_file() gives every file; arcname=str(path.relative_to(source)).",
        "tarfile.open(archive, 'w:gz') as tar: tar.add(path, arcname=rel).",
        "Name the archive with datetime.now().strftime('%Y%m%d-%H%M%S').",
        "Retention: sorted(dest.glob('backup-*.tar.gz'))[-keep:] are the keepers.",
        "logging.FileHandler(log_path) + Formatter('%(asctime)s %(levelname)s %(message)s').",
    ],
    solution={"backup.py": M14_SOLUTION},
    check=check_m14,
)


# ---------------------------------------------------------------------------
# Mission 15 — Debug + tests
# ---------------------------------------------------------------------------
BUGGY_NETMASK = """\
\"\"\"Convert between CIDR prefixes and dotted-quad netmasks.

This file contains two deliberate bugs. Fix them, then write a test suite.
\"\"\"


def prefix_to_mask(prefix: int) -> str:
    \"\"\"Return the netmask for a CIDR prefix, e.g. 24 -> '255.255.255.0'.\"\"\"
    if isinstance(prefix, bool) or not isinstance(prefix, int):
        raise ValueError(f"prefix must be an int, got {type(prefix).__name__}")
    if not 0 <= prefix <= 32:
        raise ValueError(f"prefix out of range: {prefix}")
    mask = (0xFFFFFFFF << (31 - prefix)) & 0xFFFFFFFF
    return ".".join(str((mask >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def mask_to_prefix(mask: str) -> int:
    \"\"\"Return the CIDR prefix for a dotted-quad netmask, e.g. '255.255.255.0' -> 24.\"\"\"
    parts = mask.split(".")
    if len(parts) != 4:
        raise ValueError(f"not a dotted-quad mask: {mask!r}")
    try:
        octets = [int(part) for part in parts]
    except ValueError:
        raise ValueError(f"not a dotted-quad mask: {mask!r}") from None
    if any(not 0 <= octet <= 255 for octet in octets):
        raise ValueError(f"octet out of range: {mask!r}")
    bits = "".join(f"{octet:08b}" for octet in octets)
    if "01" in bits:
        raise ValueError(f"mask is not contiguous: {mask!r}")
    return bits.count("0")
"""


def setup_m15(mdir: Path) -> None:
    target = mdir / "netmask.py"
    if not target.exists():
        write_file(target, BUGGY_NETMASK)


M15_SOLUTION_NETMASK = """\
\"\"\"Convert between CIDR prefixes and dotted-quad netmasks.\"\"\"


def prefix_to_mask(prefix: int) -> str:
    \"\"\"Return the netmask for a CIDR prefix, e.g. 24 -> '255.255.255.0'.\"\"\"
    if isinstance(prefix, bool) or not isinstance(prefix, int):
        raise ValueError(f"prefix must be an int, got {type(prefix).__name__}")
    if not 0 <= prefix <= 32:
        raise ValueError(f"prefix out of range: {prefix}")
    mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    return ".".join(str((mask >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def mask_to_prefix(mask: str) -> int:
    \"\"\"Return the CIDR prefix for a dotted-quad netmask, e.g. '255.255.255.0' -> 24.\"\"\"
    parts = mask.split(".")
    if len(parts) != 4:
        raise ValueError(f"not a dotted-quad mask: {mask!r}")
    try:
        octets = [int(part) for part in parts]
    except ValueError:
        raise ValueError(f"not a dotted-quad mask: {mask!r}") from None
    if any(not 0 <= octet <= 255 for octet in octets):
        raise ValueError(f"octet out of range: {mask!r}")
    bits = "".join(f"{octet:08b}" for octet in octets)
    if "01" in bits:
        raise ValueError(f"mask is not contiguous: {mask!r}")
    return bits.count("1")
"""

M15_SOLUTION_TESTS = """\
import unittest

from netmask import mask_to_prefix, prefix_to_mask


class TestPrefixToMask(unittest.TestCase):
    def test_common_prefixes(self):
        self.assertEqual(prefix_to_mask(0), "0.0.0.0")
        self.assertEqual(prefix_to_mask(8), "255.0.0.0")
        self.assertEqual(prefix_to_mask(16), "255.255.0.0")
        self.assertEqual(prefix_to_mask(24), "255.255.255.0")

    def test_boundaries(self):
        self.assertEqual(prefix_to_mask(32), "255.255.255.255")
        self.assertEqual(prefix_to_mask(25), "255.255.255.128")

    def test_invalid_prefix(self):
        for bad in (-1, 33):
            with self.assertRaises(ValueError):
                prefix_to_mask(bad)


class TestMaskToPrefix(unittest.TestCase):
    def test_round_trip(self):
        for prefix in (0, 1, 8, 16, 24, 25, 30, 32):
            self.assertEqual(mask_to_prefix(prefix_to_mask(prefix)), prefix)

    def test_invalid_masks(self):
        for bad in ("255.255.255.1", "300.1.1.1", "255.255.255", "abc"):
            with self.assertRaises(ValueError):
                mask_to_prefix(bad)


if __name__ == "__main__":
    unittest.main()
"""


def _load_netmask(path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("learner_netmask", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_m15(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    module_path = mdir / "netmask.py"
    test_path = mdir / "test_netmask.py"
    checks.append(Check("netmask.py exists", module_path.is_file(), str(module_path)))
    checks.append(
        Check("test_netmask.py exists", test_path.is_file(), str(test_path))
    )
    if not module_path.is_file() or not test_path.is_file():
        return checks

    try:
        module = _load_netmask(module_path)
    except Exception as exc:
        checks.append(Check("netmask.py imports cleanly", False, str(exc)))
        return checks
    checks.append(Check("netmask.py imports cleanly", True, ""))

    expected_masks = {
        0: "0.0.0.0",
        8: "255.0.0.0",
        16: "255.255.0.0",
        24: "255.255.255.0",
        25: "255.255.255.128",
        30: "255.255.255.252",
        32: "255.255.255.255",
    }
    failures = []
    for prefix, expected in expected_masks.items():
        try:
            actual = module.prefix_to_mask(prefix)
        except Exception as exc:
            actual = f"raised {exc!r}"
        if actual != expected:
            failures.append(f"/{prefix}: got {actual!r}, expected {expected!r}")
    checks.append(
        Check(
            "prefix_to_mask handles /0 through /32",
            not failures,
            "\n".join(failures),
        )
    )

    round_trip_failures = []
    for prefix in expected_masks:
        try:
            actual = module.mask_to_prefix(expected_masks[prefix])
        except Exception as exc:
            actual = f"raised {exc!r}"
        if actual != prefix:
            round_trip_failures.append(
                f"{expected_masks[prefix]}: got {actual!r}, expected {prefix}"
            )
    checks.append(
        Check(
            "mask_to_prefix is the inverse conversion",
            not round_trip_failures,
            "\n".join(round_trip_failures),
        )
    )

    invalid_failures = []
    for bad in (-1, 33):
        try:
            module.prefix_to_mask(bad)
            invalid_failures.append(f"prefix_to_mask({bad}) did not raise")
        except ValueError:
            pass
        except Exception as exc:
            invalid_failures.append(f"prefix_to_mask({bad}) raised {exc!r}")
    for bad in ("255.255.255.1", "300.1.1.1", "255.255.255", "abc"):
        try:
            module.mask_to_prefix(bad)
            invalid_failures.append(f"mask_to_prefix({bad!r}) did not raise")
        except ValueError:
            pass
        except Exception as exc:
            invalid_failures.append(f"mask_to_prefix({bad!r}) raised {exc!r}")
    checks.append(
        Check(
            "invalid inputs raise ValueError",
            not invalid_failures,
            "\n".join(invalid_failures),
        )
    )

    suite = run_command(
        ["python3", "-m", "unittest", "-q", "test_netmask.py"],
        cwd=mdir,
        timeout=30,
    )
    combined = suite.stdout + suite.stderr
    import re

    ran = re.search(r"Ran (\d+) tests?", combined)
    count = int(ran.group(1)) if ran else 0
    checks.append(
        Check(
            "your test suite passes with at least 4 tests",
            suite.returncode == 0 and count >= 4,
            f"rc={suite.returncode}, tests={count}\n{combined[-800:]}",
        )
    )

    mutant = fresh_dir(mdir / "_mutation")
    try:
        write_file(mutant / "test_netmask.py", test_path.read_text(encoding="utf-8"))
        write_file(mutant / "netmask.py", BUGGY_NETMASK)
        killed = run_command(
            ["python3", "-m", "unittest", "-q", "test_netmask.py"],
            cwd=mutant,
            timeout=30,
        )
        checks.append(
            Check(
                "your tests actually catch the original bug (mutation check)",
                killed.returncode != 0,
                "The suite passed against the buggy implementation. "
                "Add assertions that fail when '/' shifts are off by one.",
            )
        )
    finally:
        import shutil

        shutil.rmtree(mutant, ignore_errors=True)
    return checks


M15 = Mission(
    id="m15",
    num=15,
    dir_name="15_debug_and_test",
    title="Debugging and unittest: fix it, then prove it",
    domain="Linux+ 4.5 Troubleshooting / 3.2 Version control concepts",
    brief="""\
MISSION 15 — Debug and test

A buggy module is provided at 15_debug_and_test/netmask.py. It converts
between CIDR prefixes and dotted-quad netmasks, and it has TWO bugs.

Your job:
  1. Find and fix both bugs. Useful commands:
         python3 -i -c "import netmask; print(netmask.prefix_to_mask(24))"
         python3 -m pdb netmask.py
  2. Write 15_debug_and_test/test_netmask.py using unittest, with at least
     FOUR test methods covering:
         prefix_to_mask(0|8|16|24|25|32)
         the inverse mask_to_prefix(...)
         invalid prefixes (-1, 33) raise ValueError
         invalid/non-contiguous masks ("255.255.255.1", "abc") raise ValueError
  3. Run: python3 -m unittest -q test_netmask.py

The verifier additionally re-runs YOUR tests against the ORIGINAL buggy
module. If your tests still pass there, they are not protecting anything.

Verify with:  python3 main.py verify 15
""",
    hints=[
        "Check /24 first: 255.255.255.0. Then check /0 and /32 — the boundary is where it breaks.",
        "The shift should be (32 - prefix), not (31 - prefix).",
        "For mask_to_prefix, count the 1 bits, not the 0 bits.",
        "A good test suite fails on the original file. That is the point of the mutation check.",
    ],
    solution={
        "netmask.py": M15_SOLUTION_NETMASK,
        "test_netmask.py": M15_SOLUTION_TESTS,
    },
    setup=setup_m15,
    check=check_m15,
)


# ---------------------------------------------------------------------------
# Mission 16 — Capstone audit kit
# ---------------------------------------------------------------------------
AUDITKIT_INIT = """\
\"\"\"linuxplus audit kit: a small, read-only Linux security audit.\"\"\"

__version__ = "1.0.0"
"""

AUDITKIT_CORE = """\
\"\"\"Core audit logic. Everything here is read-only.\"\"\"
from __future__ import annotations

import configparser
import os
import stat
from datetime import datetime, timezone
from pathlib import Path


def parse_passwd(path: Path) -> list[dict]:
    users: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return users
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split(":")
        if len(fields) != 7:
            continue
        try:
            uid = int(fields[2])
        except ValueError:
            continue
        users.append({"name": fields[0], "password": fields[1], "uid": uid})
    return users


def scan_permissions(root: Path) -> dict:
    world_writable: list[str] = []
    suid: list[str] = []
    etc = root / "etc"
    if not etc.is_dir():
        return {"world_writable": [], "suid": []}
    for path in sorted(etc.rglob("*")):
        try:
            info = path.lstat()
        except OSError:
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        mode = stat.S_IMODE(info.st_mode)
        rel = path.relative_to(root).as_posix()
        if mode & stat.S_IWOTH:
            world_writable.append(rel)
        if mode & stat.S_ISUID:
            suid.append(rel)
    return {
        "world_writable": sorted(world_writable),
        "suid": sorted(suid),
    }


def inspect_unit(path: Path) -> dict:
    parser = configparser.ConfigParser(
        interpolation=None, allow_no_value=True, strict=False
    )
    errors: list[str] = []
    user = None
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            parser.read_file(fh)
        if not parser.has_section("Service"):
            errors.append("missing [Service] section")
        else:
            if not parser.get("Service", "ExecStart", fallback="").strip():
                errors.append("missing ExecStart")
            user = parser.get("Service", "User", fallback="").strip() or None
    except (OSError, configparser.Error) as exc:
        errors.append(f"unreadable unit: {exc}")
    return {
        "name": path.name,
        "valid": not errors,
        "errors": errors,
        "user": user,
    }


def scan_services(root: Path) -> dict:
    directory = root / "etc/systemd/system"
    paths = sorted(directory.glob("*.service")) if directory.is_dir() else []
    units = [inspect_unit(path) for path in paths]
    valid = sorted(unit["name"] for unit in units if unit["valid"])
    invalid = sorted(unit["name"] for unit in units if not unit["valid"])
    running_as_root = sorted(
        unit["name"]
        for unit in units
        if unit["valid"] and (unit["user"] is None or unit["user"] == "root")
    )
    return {
        "count": len(units),
        "valid": valid,
        "invalid": invalid,
        "running_as_root": running_as_root,
    }


def audit(root: Path) -> dict:
    users = parse_passwd(root / "etc/passwd")
    uid0 = sorted(user["name"] for user in users if user["uid"] == 0)
    uid0_nonroot = [name for name in uid0 if name != "root"]
    no_password = sorted(user["name"] for user in users if user["password"] == "")
    human_count = sum(1 for user in users if 1000 <= user["uid"] < 65534)
    permissions = scan_permissions(root)
    services = scan_services(root)
    risk_score = (
        len(uid0_nonroot)
        + len(no_password)
        + len(permissions["world_writable"])
        + len(permissions["suid"])
        + len(services["running_as_root"])
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": str(root),
        "users": {
            "uid0": uid0,
            "uid0_nonroot": uid0_nonroot,
            "no_password": no_password,
            "human_count": human_count,
        },
        "permissions": permissions,
        "services": services,
        "risk_score": risk_score,
    }
"""

AUDITKIT_MAIN = """\
\"\"\"CLI entry point: python3 -m auditkit --root DIR --out FILE.\"\"\"
import argparse
import json
import sys
from pathlib import Path

from .core import audit


def main() -> int:
    parser = argparse.ArgumentParser(prog="auditkit")
    parser.add_argument("--root", default="/", help="filesystem root to audit")
    parser.add_argument("--out", default="audit-report.json", help="report path")
    args = parser.parse_args()
    root = Path(args.root)
    if not root.is_dir():
        print(f"ERROR: root not found: {root}", file=sys.stderr)
        return 2
    report = audit(root)
    try:
        Path(args.out).write_text(
            json.dumps(report, indent=2) + "\\n", encoding="utf-8"
        )
    except OSError as exc:
        print(f"ERROR: cannot write report: {exc}", file=sys.stderr)
        return 2
    print(f"risk_score={report['risk_score']} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""


def _make_audit_fixture(root: Path) -> None:
    fresh_dir(root)
    etc = root / "etc"
    units = etc / "systemd/system"
    units.mkdir(parents=True)
    write_file(
        etc / "passwd",
        "root:x:0:0:root:/root:/bin/bash\n"
        "toor::0:0:toor:/root:/bin/bash\n"
        "svc:x:998:998:svc:/var/lib/svc:/usr/sbin/nologin\n"
        "deb:x:1000:1000:deb:/home/deb:/bin/bash\n"
        "alice:x:1001:1001:alice:/home/alice:/bin/bash\n",
    )
    write_file(
        units / "backup.service",
        "[Unit]\nDescription=Backup\n[Service]\nExecStart=/usr/bin/true\nUser=backup\n",
    )
    write_file(
        units / "web.service",
        "[Unit]\nDescription=Web\n[Service]\nExecStart=/usr/bin/true\n",
    )
    write_file(
        units / "evil.service",
        "[Unit]\nDescription=Evil\n[Service]\nUser=root\n",
    )
    for rel, mode in (
        ("world.txt", 0o666),
        ("suid.bin", 0o4755),
        ("normal.txt", 0o644),
    ):
        path = etc / rel
        path.write_text(rel, encoding="utf-8")
        path.chmod(mode)


def setup_m16(mdir: Path) -> None:
    sample = mdir / "sample_root"
    if not sample.exists():
        _make_audit_fixture(sample)


def check_m16(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    package = mdir / "auditkit"
    checks.append(
        Check(
            "auditkit/__init__.py exists",
            (package / "__init__.py").is_file(),
            str(package / "__init__.py"),
        )
    )
    checks.append(
        Check(
            "auditkit/__main__.py exists",
            (package / "__main__.py").is_file(),
            str(package / "__main__.py"),
        )
    )
    if not (package / "__init__.py").is_file() or not (package / "__main__.py").is_file():
        return checks

    help_proc = run_command(
        ["python3", "-m", "auditkit", "--help"], cwd=mdir, timeout=15
    )
    checks.append(
        Check(
            "python3 -m auditkit --help works and documents --root",
            help_proc.returncode == 0 and "--root" in (help_proc.stdout + help_proc.stderr),
            output(help_proc),
        )
    )

    verify = fresh_dir(mdir / "_verify")
    fixture = verify / "root"
    _make_audit_fixture(fixture)
    report = verify / "report.json"
    proc = run_command(
        [
            "python3",
            "-m",
            "auditkit",
            "--root",
            str(fixture),
            "--out",
            str(report),
        ],
        cwd=mdir,
        timeout=30,
    )
    checks.append(
        Check(
            "audit runs and exits 0",
            proc.returncode == 0 and no_traceback(proc),
            output(proc),
        )
    )
    checks.append(
        Check("report file is created", report.is_file(), f"missing {report}")
    )
    if not report.is_file():
        return checks
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except Exception as exc:
        checks.append(Check("report is valid JSON", False, str(exc)))
        return checks
    checks.append(Check("report is valid JSON", True, ""))

    checks.append(
        Check(
            "generated_at timestamp is present",
            isinstance(data.get("generated_at"), str) and data["generated_at"] != "",
            f"got {data.get('generated_at')!r}",
        )
    )
    checks.append(
        Check(
            "users: uid0 and uid0_nonroot are correct",
            data.get("users", {}).get("uid0") == ["root", "toor"]
            and data.get("users", {}).get("uid0_nonroot") == ["toor"],
            f"got {data.get('users')!r}",
        )
    )
    checks.append(
        Check(
            "users: empty password and human count are correct",
            data.get("users", {}).get("no_password") == ["toor"]
            and data.get("users", {}).get("human_count") == 2,
            f"got {data.get('users')!r}",
        )
    )
    checks.append(
        Check(
            "permissions: world-writable and SUID paths are correct",
            data.get("permissions")
            == {"world_writable": ["etc/world.txt"], "suid": ["etc/suid.bin"]},
            f"got {data.get('permissions')!r}",
        )
    )
    checks.append(
        Check(
            "services: count, valid, invalid, and root services are correct",
            data.get("services")
            == {
                "count": 3,
                "valid": ["backup.service", "web.service"],
                "invalid": ["evil.service"],
                "running_as_root": ["web.service"],
            },
            f"got {data.get('services')!r}",
        )
    )
    checks.append(
        Check(
            "risk_score is the documented sum (5)",
            data.get("risk_score") == 5,
            f"got {data.get('risk_score')!r}",
        )
    )

    missing = run_command(
        ["python3", "-m", "auditkit", "--root", str(verify / "nope")],
        cwd=mdir,
        timeout=15,
    )
    checks.append(
        Check(
            "missing root exits 2 cleanly",
            missing.returncode == 2 and no_traceback(missing),
            output(missing),
        )
    )
    return checks


M16 = Mission(
    id="m16",
    num=16,
    dir_name="16_audit_kit",
    title="Capstone: package a Linux+ security audit kit",
    domain="Linux+ Capstone — all domains",
    brief="""\
MISSION 16 — Capstone audit kit

Build an importable package, not just a script:

    16_audit_kit/auditkit/__init__.py
    16_audit_kit/auditkit/__main__.py
    16_audit_kit/auditkit/core.py        (recommended)

Run it as:
    python3 -m auditkit --root <fixture-root> --out report.json

A fixture tree is provided at 16_audit_kit/sample_root/. Its layout:
    etc/passwd
    etc/systemd/system/*.service
    etc/* files with different permission bits

The report must contain:
    {
      "generated_at": "ISO-8601 UTC timestamp",
      "root": "<the root you audited>",
      "users": {
        "uid0": ["root", "toor"],          # sorted
        "uid0_nonroot": ["toor"],          # uid 0 but not root
        "no_password": ["toor"],           # empty password field
        "human_count": 2                   # uid 1000..65533
      },
      "permissions": {
        "world_writable": ["etc/world.txt"],   # rel to root, sorted
        "suid": ["etc/suid.bin"]
      },
      "services": {
        "count": 3,
        "valid": ["backup.service", "web.service"],
        "invalid": ["evil.service"],
        "running_as_root": ["web.service"]     # valid + no User= or User=root
      },
      "risk_score": 5
    }

Services are invalid when [Service] or ExecStart is missing.
risk_score = len(uid0_nonroot) + len(no_password)
           + len(permissions.world_writable) + len(permissions.suid)
           + len(services.running_as_root)

Exit 0 on success, 2 for a missing root or unwritable report. Never modify
the audited tree. --help must document --root.

Verify with:  python3 main.py verify 16
""",
    hints=[
        "Split the work into core.py functions: parse_passwd, scan_permissions, scan_services, audit.",
        "__main__.py only parses args and calls audit(); that keeps it testable.",
        "configparser with interpolation=None handles unit files; missing ExecStart is the invalid signal.",
        "Path.relative_to(root).as_posix() keeps report paths stable across platforms.",
        "Add the five risk components in one expression and store it in the report.",
    ],
    solution={
        "auditkit/__init__.py": AUDITKIT_INIT,
        "auditkit/core.py": AUDITKIT_CORE,
        "auditkit/__main__.py": AUDITKIT_MAIN,
    },
    setup=setup_m16,
    check=check_m16,
)


MISSIONS = [M14, M15, M16]
