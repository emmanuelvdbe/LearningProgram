"""Part 1 — Python foundations in a Linux context (missions 1-4)."""
from __future__ import annotations

import getpass
import json
import os
import platform
import shutil
import stat
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

PASSWD_SAMPLE = """\
root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
bin:x:2:2:bin:/bin:/usr/sbin/nologin
sys:x:3:3:sys:/dev:/usr/sbin/nologin
sync:x:4:65534:sync:/bin:/bin/sync
deb:x:1000:1000:Deb:/home/deb:/bin/bash
alice:x:1001:1001:Alice:/home/alice:/bin/zsh
bob:x:1002:1002:Bob:/home/bob:/bin/bash
carol:x:1000:1000:Carol:/home/carol:/bin/bash
nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin
"""


# ---------------------------------------------------------------------------
# Mission 01 — First contact
# ---------------------------------------------------------------------------
M01_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"First lab: prove that Python and the kernel agree about this machine.\"\"\"
import getpass
import platform


def main() -> None:
    print(f"Hello, {getpass.getuser()}!")
    print(f"Python {platform.python_version()} on {platform.node()}")


if __name__ == "__main__":
    main()
"""


def check_m01(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "hello_sys.py"
    checks.append(Check("hello_sys.py exists", script.is_file(), str(script)))
    if not script.is_file():
        return checks

    text = script.read_text(encoding="utf-8", errors="replace")
    first = text.splitlines()[0].strip() if text.splitlines() else ""
    checks.append(
        Check(
            "shebang is #!/usr/bin/env python3",
            first == "#!/usr/bin/env python3",
            f"first line: {first!r}",
        )
    )
    mode = stat.S_IMODE(script.stat().st_mode)
    checks.append(
        Check(
            "file is executable (chmod +x)",
            bool(mode & 0o111),
            f"mode {mode:04o}",
        )
    )

    proc = run_script(script, cwd=mdir, timeout=10)
    expected_user = f"Hello, {getpass.getuser()}!"
    expected_py = f"Python {platform.python_version()} on {platform.node()}"
    checks.append(
        Check(
            "runs and greets the current user",
            proc.returncode == 0 and expected_user in proc.stdout,
            output(proc),
        )
    )
    checks.append(
        Check(
            "prints Python version and hostname",
            proc.returncode == 0 and expected_py in proc.stdout,
            f"expected: {expected_py}\n{output(proc)}",
        )
    )
    checks.append(
        Check(
            "uses an if __name__ == \"__main__\" guard",
            "__name__" in text and "__main__" in text,
            "Keep the script importable: put the work in main().",
        )
    )

    if mode & 0o111:
        direct = run_script(script, cwd=mdir, timeout=10, direct=True)
        checks.append(
            Check(
                "runs directly as ./hello_sys.py",
                direct.returncode == 0,
                output(direct),
            )
        )
    else:
        checks.append(
            Check(
                "runs directly as ./hello_sys.py",
                False,
                "The kernel cannot execute it without the +x bit.",
            )
        )
    return checks


M01 = Mission(
    id="m01",
    num=1,
    dir_name="01_first_contact",
    title="First contact: a real executable script",
    domain="Linux+ 3.1 Scripting basics",
    brief="""\
MISSION 01 — First contact

Create this file in your lab:

    01_first_contact/hello_sys.py

It must:

  1. Start with exactly this shebang line:
         #!/usr/bin/env python3
  2. Print two lines (values come from Python, not hard-coded):
         Hello, <current username>!
         Python <python version> on <hostname>
     Example:
         Hello, deb!
         Python 3.13.5 on lab01
  3. Be executable, then run it directly as ./hello_sys.py
  4. Put the work in main() and guard it with:
         if __name__ == "__main__":
             main()

Useful tools: getpass.getuser(), platform.python_version(),
platform.node(), chmod +x, ls -l, ./hello_sys.py

Verify with:  python3 main.py verify 1
""",
    hints=[
        "Three modules do all the work: getpass, platform, and the shebang.",
        "chmod +x hello_sys.py is what turns a text file into a program.",
        "Compare: python3 hello_sys.py  (always works) vs ./hello_sys.py (needs +x).",
    ],
    solution={"hello_sys.py": M01_SOLUTION},
    check=check_m01,
)


# ---------------------------------------------------------------------------
# Mission 02 — System report
# ---------------------------------------------------------------------------
M02_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Print a small, parseable report about this Linux system.\"\"\"
import os
import platform
import shutil


def main() -> None:
    usage = shutil.disk_usage("/")
    load1, load5, load15 = os.getloadavg()
    print(f"hostname={platform.node()}")
    print(f"kernel={platform.release()}")
    print(f"python={platform.python_version()}")
    print(f"cpus={os.cpu_count()}")
    print(f"loadavg={load1:.2f},{load5:.2f},{load15:.2f}")
    print(f"root_free_gib={usage.free / 1024**3:.1f}")


if __name__ == "__main__":
    main()
"""


def check_m02(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "system_report.py"
    checks.append(Check("system_report.py exists", script.is_file(), str(script)))
    if not script.is_file():
        return checks

    proc = run_script(script, cwd=mdir, timeout=10)
    checks.append(Check("script exits 0", proc.returncode == 0, output(proc)))
    if proc.returncode != 0:
        return checks

    data: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()

    required = {"hostname", "kernel", "python", "cpus", "loadavg", "root_free_gib"}
    checks.append(
        Check(
            "all six key=value lines are present",
            required <= data.keys(),
            f"missing: {sorted(required - data.keys())}",
        )
    )
    checks.append(
        Check(
            "hostname matches this machine",
            data.get("hostname") == platform.node(),
            f"got {data.get('hostname')!r}, expected {platform.node()!r}",
        )
    )
    checks.append(
        Check(
            "kernel release matches os.uname()",
            data.get("kernel") == platform.release(),
            f"got {data.get('kernel')!r}, expected {platform.release()!r}",
        )
    )
    checks.append(
        Check(
            "Python version matches the running interpreter",
            data.get("python") == platform.python_version(),
            f"got {data.get('python')!r}, expected {platform.python_version()!r}",
        )
    )
    try:
        cpus = int(data.get("cpus", ""))
        cpu_ok = cpus == os.cpu_count()
        cpu_detail = f"got {cpus}, expected {os.cpu_count()}"
    except ValueError:
        cpu_ok = False
        cpu_detail = f"not an integer: {data.get('cpus')!r}"
    checks.append(Check("cpus is an int equal to os.cpu_count()", cpu_ok, cpu_detail))

    try:
        parts = [float(p) for p in data.get("loadavg", "").split(",")]
        load_ok = len(parts) == 3
        load_detail = f"parsed {parts}"
    except ValueError:
        load_ok = False
        load_detail = f"not three numbers: {data.get('loadavg')!r}"
    checks.append(Check("loadavg has three numbers", load_ok, load_detail))

    try:
        free_gib = float(data.get("root_free_gib", ""))
        actual = shutil.disk_usage("/").free / 1024**3
        free_ok = abs(free_gib - actual) <= 2.0
        free_detail = f"got {free_gib} GiB, actual {actual:.1f} GiB"
    except ValueError:
        free_ok = False
        free_detail = f"not a float: {data.get('root_free_gib')!r}"
    checks.append(Check("root_free_gib is close to the real value", free_ok, free_detail))

    source = script.read_text(encoding="utf-8", errors="replace")
    checks.append(
        Check(
            "uses an f-string",
            'f"' in source or "f'" in source,
            "Use f\"...{value}...\" formatting; it is the idiomatic modern style.",
        )
    )
    return checks


M02 = Mission(
    id="m02",
    num=2,
    dir_name="02_system_report",
    title="Variables, types, and f-strings",
    domain="Linux+ 1.1 System information",
    brief="""\
MISSION 02 — System report

Create:

    02_system_report/system_report.py

It must print exactly these six lines, one key=value pair per line:

    hostname=<hostname>
    kernel=<kernel release>
    python=<python version>
    cpus=<integer CPU count>
    loadavg=<1min>,<5min>,<15min>          e.g. 0.12,0.34,0.56
    root_free_gib=<free GiB on /, 1 decimal>   e.g. 214.3

Rules:
  * Values must come from Python, not typed-in constants.
  * cpus must be an int (use int() or os.cpu_count()).
  * root_free_gib uses shutil.disk_usage("/").free and must be within 2 GiB.
  * Use f-strings for every line.

This is the "health snapshot" pattern you will reuse in monitoring scripts.

Verify with:  python3 main.py verify 2
""",
    hints=[
        "platform.node(), platform.release(), platform.python_version(), os.cpu_count().",
        "os.getloadavg() returns three floats; unpack it: a, b, c = os.getloadavg().",
        "1 GiB = 1024**3 bytes. Format with {value:.1f}.",
    ],
    solution={"system_report.py": M02_SOLUTION},
    check=check_m02,
)


# ---------------------------------------------------------------------------
# Mission 03 — Disk guard
# ---------------------------------------------------------------------------
M03_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Exit-code driven disk guard: 0 OK, 1 alert, 2 usage error.\"\"\"
import shutil
import sys


def main() -> int:
    if len(sys.argv) > 2:
        print("usage: disk_guard.py [threshold]", file=sys.stderr)
        return 2

    try:
        threshold = float(sys.argv[1]) if len(sys.argv) == 2 else 90.0
    except ValueError:
        print("usage: disk_guard.py [threshold]", file=sys.stderr)
        return 2

    usage = shutil.disk_usage("/")
    percent = usage.used / usage.total * 100
    if percent >= threshold:
        print(f"CRITICAL: / is {percent:.1f}% used (threshold {threshold:g}%)")
        return 1
    print(f"OK: / is {percent:.1f}% used (threshold {threshold:g}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""


def check_m03(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "disk_guard.py"
    checks.append(Check("disk_guard.py exists", script.is_file(), str(script)))
    if not script.is_file():
        return checks

    high = run_script(script, "101", cwd=mdir, timeout=10)
    checks.append(
        Check(
            "threshold 101 exits 0 with OK",
            high.returncode == 0
            and "OK" in high.stdout
            and "%" in high.stdout,
            output(high),
        )
    )

    low = run_script(script, "0", cwd=mdir, timeout=10)
    checks.append(
        Check(
            "threshold 0 exits 1 with CRITICAL",
            low.returncode == 1
            and "CRITICAL" in low.stdout
            and "threshold 0" in low.stdout,
            output(low),
        )
    )

    bad = run_script(script, "not-a-number", cwd=mdir, timeout=10)
    checks.append(
        Check(
            "invalid threshold exits 2 with a usage message on stderr",
            bad.returncode == 2
            and "usage" in bad.stderr.lower()
            and "Traceback" not in bad.stderr,
            output(bad),
        )
    )

    default = run_script(script, cwd=mdir, timeout=10)
    checks.append(
        Check(
            "default threshold works (exit 0 or 1)",
            default.returncode in (0, 1) and "%" in default.stdout,
            output(default),
        )
    )
    return checks


M03 = Mission(
    id="m03",
    num=3,
    dir_name="03_disk_guard",
    title="Decisions, comparisons, and exit codes",
    domain="Linux+ 4.1 Storage troubleshooting",
    brief="""\
MISSION 03 — Disk guard

Create:

    03_disk_guard/disk_guard.py

Usage:

    python3 disk_guard.py [threshold]

Behaviour:
  * threshold is a percentage number; default 90.
  * Compute used% for / with shutil.disk_usage("/").
  * If used% >= threshold:
        print CRITICAL: / is XX.X% used (threshold YY%)
        exit status 1
  * Otherwise:
        print OK: / is XX.X% used (threshold YY%)
        exit status 0
  * If the argument is not a number (or there are too many arguments):
        print a usage line to STDERR
        exit status 2

Exit codes matter: cron, systemd, and monitoring tools judge a script by its
status, not by how pretty the output is.

Verify with:  python3 main.py verify 3
""",
    hints=[
        "sys.argv[0] is the script name; sys.argv[1] is the first argument.",
        "float() raises ValueError for bad input; catch it and return 2.",
        "sys.exit(main()) makes the return value the process exit status.",
    ],
    solution={"disk_guard.py": M03_SOLUTION},
    check=check_m03,
)


# ---------------------------------------------------------------------------
# Mission 04 — passwd report
# ---------------------------------------------------------------------------
M04_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Summarise an /etc/passwd-style file as JSON.\"\"\"
import json
import sys
from collections import Counter


def parse_passwd(lines: list[str]) -> list[dict[str, str]]:
    users = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split(":")
        if len(fields) != 7:
            continue
        name, _pw, uid, gid, _gecos, home, shell = fields
        users.append(
            {
                "name": name,
                "uid": int(uid),
                "gid": gid,
                "home": home,
                "shell": shell,
            }
        )
    return users


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: passwd_report.py <passwd-file>", file=sys.stderr)
        return 2
    try:
        with open(sys.argv[1], encoding="utf-8") as fh:
            users = parse_passwd(fh.readlines())
    except OSError as exc:
        print(f"ERROR: cannot read {sys.argv[1]}: {exc}", file=sys.stderr)
        return 2

    human = sorted(u["name"] for u in users if 1000 <= u["uid"] < 65534)
    uids = Counter(u["uid"] for u in users)
    duplicates = sorted(uid for uid, count in uids.items() if count > 1)
    shells = Counter(u["shell"] for u in users)

    report = {
        "total": len(users),
        "human_users": human,
        "shells": dict(sorted(shells.items())),
        "duplicate_uids": duplicates,
    }
    json.dump(report, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""


def _m04_expected() -> dict[str, object]:
    return {
        "total": 10,
        "human_users": ["alice", "bob", "carol", "deb"],
        "shells": {
            "/bin/bash": 4,
            "/bin/sync": 1,
            "/bin/zsh": 1,
            "/usr/sbin/nologin": 4,
        },
        "duplicate_uids": [1000],
    }


def check_m04(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "passwd_report.py"
    checks.append(Check("passwd_report.py exists", script.is_file(), str(script)))
    if not script.is_file():
        return checks

    verify = fresh_dir(mdir / "_verify")
    fixture = write_file(verify / "passwd", PASSWD_SAMPLE)
    proc = run_script(script, fixture, cwd=mdir, timeout=10)
    checks.append(Check("exits 0 on a valid file", proc.returncode == 0, output(proc)))
    if proc.returncode != 0:
        return checks

    data, error = parse_json(proc)
    if data is None:
        checks.append(Check("prints valid JSON", False, error))
        return checks
    checks.append(Check("prints valid JSON", True, ""))

    expected = _m04_expected()
    if not isinstance(data, dict):
        checks.append(Check("JSON is an object", False, f"got {type(data).__name__}"))
        return checks
    checks.append(
        Check(
            "total is correct",
            data.get("total") == expected["total"],
            f"got {data.get('total')!r}, expected {expected['total']}",
        )
    )
    checks.append(
        Check(
            "human_users is correct and sorted",
            data.get("human_users") == expected["human_users"],
            f"got {data.get('human_users')!r}, expected {expected['human_users']}",
        )
    )
    checks.append(
        Check(
            "shells counts are correct",
            data.get("shells") == expected["shells"],
            f"got {data.get('shells')!r}",
        )
    )
    checks.append(
        Check(
            "duplicate_uids is correct",
            data.get("duplicate_uids") == expected["duplicate_uids"],
            f"got {data.get('duplicate_uids')!r}",
        )
    )

    real = run_script(script, "/etc/passwd", cwd=mdir, timeout=10)
    checks.append(
        Check(
            "also works on the real /etc/passwd",
            real.returncode == 0 and no_traceback(real),
            output(real),
        )
    )
    return checks


M04 = Mission(
    id="m04",
    num=4,
    dir_name="04_passwd_report",
    title="Lists, dictionaries, and real /etc/passwd data",
    domain="Linux+ 1.5 Users and groups",
    brief="""\
MISSION 04 — passwd report

Create:

    04_passwd_report/passwd_report.py

It reads any /etc/passwd-style file and prints a JSON report to stdout:

    python3 passwd_report.py <passwd-file>

Required JSON shape:
    {
      "total": 10,
      "human_users": ["alice", "bob", "carol", "deb"],
      "shells": {"/bin/bash": 4, "/bin/sync": 1, "/bin/zsh": 1,
                 "/usr/sbin/nologin": 4},
      "duplicate_uids": [1000]
    }

Rules:
  * A line has 7 colon-separated fields: name:password:uid:gid:gecos:home:shell
  * Skip blank lines and lines starting with #.
  * total = all valid records.
  * human_users = names whose UID is 1000..65533, sorted alphabetically.
  * shells = {shell: count}, sorted by shell name.
  * duplicate_uids = UIDs used by more than one account, sorted.
  * Print indented JSON (json.dump(..., indent=2)).

A sample file is provided at 04_passwd_report/passwd.sample.

Verify with:  python3 main.py verify 4
""",
    hints=[
        "line.split(':') gives exactly the seven fields; unpack them.",
        "Convert uid to int BEFORE comparing it with 1000.",
        "collections.Counter does the shell tally and duplicate detection in one line each.",
        "sorted(dict.items()) gives deterministic output for humans and JSON.",
    ],
    solution={"passwd_report.py": M04_SOLUTION},
    check=check_m04,
)


MISSIONS = [M01, M02, M03, M04]
