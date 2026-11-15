"""XK0-006 Domain 2 — Services and User Management (missions 7-11)."""
from __future__ import annotations

import os
import stat
import time
from pathlib import Path

from .base import (
    Check,
    Mission,
    has_keys,
    output,
    run_command,
    run_script,
    script_json,
    text_contains,
    write_file,
)


# ---------------------------------------------------------------------------
# Mission 07 — Files, links, and filesystem metadata
# ---------------------------------------------------------------------------
def setup_m07(mdir: Path) -> None:
    write_file(mdir / "data/releases/v1/config.ini", "version=1\n")
    write_file(mdir / "data/releases/v2/config.ini", "version=2\n")
    write_file(mdir / "data/releases/v2/app.jar", "jar\n")
    write_file(mdir / "data/small.txt", "small\n")
    # A sparse file larger than 1 MiB without writing megabytes to disk.
    big = mdir / "data/big.bin"
    big.parent.mkdir(parents=True, exist_ok=True)
    with big.open("wb") as handle:
        handle.seek(2 * 1024 * 1024 - 1)
        handle.write(b"\0")
    write_file(mdir / "devices/ls-l.txt", (
        "brw-rw---- 1 root disk 8, 0 Nov 14 10:00 /dev/sda\n"
        "crw-rw-rw- 1 root root 1, 3 Nov 14 10:00 /dev/null\n"
        "crw--w---- 1 root tty 4, 1 Nov 14 10:00 /dev/tty1\n"
        "-rw-r--r-- 1 root root 12 Nov 14 10:00 /dev/not-a-device\n"
    ))
    links = mdir / "links"
    links.mkdir(parents=True, exist_ok=True)
    broken = links / "broken"
    if broken.exists() or broken.is_symlink():
        broken.unlink()
    broken.symlink_to("../missing-target")


M07_SOLUTION = """\
#!/usr/bin/env bash
set -euo pipefail

mkdir -p reports
ln -sfn releases/v2 data/current
ln -f data/releases/v2/config.ini data/config.hard

find data -type f -size +1M -printf '%p\\n' | sort > reports/large.txt

while read -r perms links owner group major minor rest; do
    case "${perms:0:1}" in
        b) kind=block ;;
        c) kind=char ;;
        *) continue ;;
    esac
    printf '%s %s\\n' "$kind" "${rest##* }"
done < devices/ls-l.txt > reports/devices.txt

find links -xtype l -printf '%p\\n' | sort > reports/broken.txt
"""


def check_m07(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "file_audit.sh"
    if not script.is_file():
        return [Check("file_audit.sh exists", False, str(script))]
    checks.append(Check("file_audit.sh exists", True, str(script)))

    proc = run_command(["/bin/bash", str(script)], cwd=mdir, timeout=20)
    checks.append(Check("script runs successfully", proc.returncode == 0, output(proc)))
    if proc.returncode != 0:
        return checks

    current = mdir / "data/current"
    checks.append(Check(
        "data/current is a symbolic link",
        current.is_symlink(),
        "ln -s releases/v2 data/current",
    ))
    checks.append(Check(
        "symlink target is relative and points at v2",
        current.is_symlink() and os.readlink(current) == "releases/v2",
        f"target={os.readlink(current)!r}" if current.is_symlink() else "",
    ))

    hard = mdir / "data/config.hard"
    original = mdir / "data/releases/v2/config.ini"
    checks.append(Check(
        "data/config.hard is a hard link to the v2 config",
        hard.is_file() and original.is_file()
        and hard.stat().st_ino == original.stat().st_ino,
        f"inodes: {hard.stat().st_ino if hard.exists() else 'missing'} vs {original.stat().st_ino}",
    ))

    large = mdir / "reports/large.txt"
    checks.append(Check("reports/large.txt exists", large.is_file(), str(large)))
    if large.is_file():
        text = large.read_text()
        checks.append(Check(
            "large.txt lists the >1 MiB file",
            "data/big.bin" in text and "data/small.txt" not in text,
            text.strip(),
        ))

    devices = mdir / "reports/devices.txt"
    checks.append(Check("reports/devices.txt exists", devices.is_file(), str(devices)))
    if devices.is_file():
        lines = [line.strip() for line in devices.read_text().splitlines() if line.strip()]
        checks.append(Check(
            "classifies block and character devices",
            lines == [
                "block /dev/sda",
                "char /dev/null",
                "char /dev/tty1",
            ],
            f"got {lines!r}",
        ))

    broken = mdir / "reports/broken.txt"
    checks.append(Check("reports/broken.txt exists", broken.is_file(), str(broken)))
    if broken.is_file():
        checks.append(Check(
            "finds the broken symlink",
            "links/broken" in broken.read_text(),
            broken.read_text().strip(),
        ))
    return checks


M07 = Mission(
    id="xk201",
    num=7,
    dir_name="xk201_files_links",
    title="Files, links, and filesystem metadata",
    domain="Linux+ 2.1 Files and directories",
    brief="""\
MISSION 07 — Link, find, and classify

Create an executable `file_audit.sh`.  When run from the mission directory it
must:

  1. Create `data/current` as a relative symbolic link to `releases/v2`
     (so `data/current/config.ini` resolves).
  2. Create `data/config.hard` as a hard link to
     `data/releases/v2/config.ini`.
  3. Write `reports/large.txt`: every regular file under `data/` larger than
     1 MiB, one path per line, sorted.
  4. Write `reports/devices.txt`: one line per block or character device in
     `devices/ls-l.txt`, formatted as `block /dev/sda` or `char /dev/null`.
  5. Write `reports/broken.txt`: broken symbolic links under `links/`.

The difference between a symlink and a hard link is the key idea: changing
the symlink target is cheap, while a hard link is a second name for the same
inode.

Verify with:  python3 main.py verify 7
""",
    hints=[
        "ln -s releases/v2 data/current creates a relative symlink from data/.",
        "find data -type f -size +1M -printf '%p\\n' prints the path.",
        "find links -xtype l finds symlinks whose target does not exist.",
        "In a shell case statement, ${perms:0:1} is the first character of ls -l output.",
    ],
    solution={"file_audit.sh": M07_SOLUTION},
    setup=setup_m07,
    check=check_m07,
)


# ---------------------------------------------------------------------------
# Mission 08 — Local account management
# ---------------------------------------------------------------------------
PASSWD = """\
root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
svcweb:x:998:998:web service:/var/lib/svcweb:/bin/bash
alice:x:1000:1000:Alice:/home/alice:/bin/bash
bob:x:1001:1001:Bob:/home/bob:/bin/zsh
carol:x:1002:1002:Carol:/home/carol:/bin/bash
dave:x:0:1003:Dave:/home/dave:/bin/bash
"""

SHADOW = """\
root:$6$root:19000:0:99999:7:::
daemon:*:19000:0:99999:7:::
svcweb:!:19000:0:99999:7:::
alice:$6$alice:19000:0:99999:7:::
bob:$6$bob:19000:0:99999:7:::
carol:$6$carol:15000:0:30:7:::
dave:$6$dave:19000:0:99999:7:::
"""


def setup_m08(mdir: Path) -> None:
    write_file(mdir / "etc/passwd", PASSWD)
    write_file(mdir / "etc/shadow", SHADOW)
    write_file(mdir / "etc/group", "root:x:0:\nwheel:x:10:alice\nusers:x:100:alice,bob,carol,dave\n")
    for name in ("alice", "carol", "dave"):
        (mdir / "home" / name).mkdir(parents=True, exist_ok=True)
    write_file(mdir / "new_users.txt", "erin:1003:users:/bin/bash\nfrank:1004:users:/sbin/nologin\n")


M08_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Audit local accounts and emit a safe useradd plan.\"\"\"
import argparse
import json
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root)

    passwd = {}
    uid_owners: dict[str, list[str]] = {}
    for line in (root / "etc/passwd").read_text().splitlines():
        fields = line.split(":")
        if len(fields) < 7:
            continue
        name, _, uid, gid, _, home, shell = fields[:7]
        passwd[name] = {"uid": uid, "gid": gid, "home": home, "shell": shell}
        uid_owners.setdefault(uid, []).append(name)

    shadow = {}
    for line in (root / "etc/shadow").read_text().splitlines():
        fields = line.split(":")
        if len(fields) >= 3:
            shadow[fields[0]] = {
                "password": fields[1],
                "last_change": int(fields[2] or 0),
                "max_days": int(fields[4] or 0),
            }

    groups = {}
    for line in (root / "etc/group").read_text().splitlines():
        fields = line.split(":")
        if len(fields) >= 4:
            groups[fields[0]] = [name for name in fields[3].split(",") if name]

    today = int(time.time() // 86400)
    duplicate_uids = {uid: names for uid, names in uid_owners.items() if len(names) > 1}
    interactive = [
        name for name, data in passwd.items()
        if int(data["uid"]) < 1000 and int(data["uid"]) != 0
        and data["shell"].endswith(("bash", "sh", "zsh"))
    ]
    locked = [name for name, data in shadow.items()
              if data["password"].startswith("!")]
    expired = [
        name for name, data in shadow.items()
        if data["max_days"] and data["last_change"] + data["max_days"] < today
    ]
    missing_homes = [
        name for name, data in passwd.items()
        if int(data["uid"]) >= 1000 and not (root / data["home"].lstrip("/")).is_dir()
    ]

    commands = []
    for line in (root / "new_users.txt").read_text().splitlines():
        fields = line.split(":")
        if len(fields) != 4:
            continue
        name, uid, group, shell = fields
        home_flag = "-M" if shell.endswith("nologin") else "-m"
        commands.append(
            f"useradd -u {uid} -g {group} {home_flag} -s {shell} {name}"
        )

    print(json.dumps({
        "duplicate_uids": duplicate_uids,
        "interactive_service_accounts": sorted(interactive),
        "locked_accounts": sorted(locked),
        "expired_accounts": sorted(expired),
        "missing_homes": sorted(missing_homes),
        "wheel_members": sorted(groups.get("wheel", [])),
        "provision_commands": commands,
    }, indent=2))


if __name__ == "__main__":
    main()
"""


def check_m08(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "user_audit.py"
    if not script.is_file():
        return [Check("user_audit.py exists", False, str(script))]
    checks.append(Check("user_audit.py exists", True, str(script)))

    data, proc = script_json(script, "--root", ".", cwd=mdir)
    checks.append(Check("script prints valid JSON and exits 0", data is not None, output(proc)))
    if data is None:
        return checks

    ok, detail = has_keys(data, {
        "duplicate_uids", "interactive_service_accounts", "locked_accounts",
        "expired_accounts", "missing_homes", "wheel_members",
        "provision_commands",
    })
    checks.append(Check("report has every required key", ok, detail))
    checks.append(Check(
        "finds the duplicate UID 0",
        data.get("duplicate_uids") == {"0": ["root", "dave"]},
        f"got {data.get('duplicate_uids')!r}",
    ))
    checks.append(Check(
        "finds the service account with an interactive shell",
        data.get("interactive_service_accounts") == ["svcweb"],
        f"got {data.get('interactive_service_accounts')!r}",
    ))
    checks.append(Check(
        "finds the explicitly locked account",
        data.get("locked_accounts") == ["svcweb"],
        f"got {data.get('locked_accounts')!r}",
    ))
    checks.append(Check(
        "finds the expired account",
        data.get("expired_accounts") == ["carol"],
        f"got {data.get('expired_accounts')!r}",
    ))
    checks.append(Check(
        "finds the account whose home directory is missing",
        data.get("missing_homes") == ["bob"],
        f"got {data.get('missing_homes')!r}",
    ))
    checks.append(Check(
        "reads wheel group membership",
        data.get("wheel_members") == ["alice"],
        f"got {data.get('wheel_members')!r}",
    ))
    commands = data.get("provision_commands")
    checks.append(Check(
        "builds a useradd command for each new user",
        isinstance(commands, list)
        and len(commands) == 2
        and any("erin" in c and "-u 1003" in c and "-g users" in c and "-m" in c and "/bin/bash" in c for c in commands)
        and any("frank" in c and "-u 1004" in c and "-M" in c and "/sbin/nologin" in c for c in commands),
        f"got {commands!r}",
    ))
    return checks


M08 = Mission(
    id="xk202",
    num=8,
    dir_name="xk202_accounts",
    title="Local account management",
    domain="Linux+ 2.2 Local accounts",
    brief="""\
MISSION 08 — Account audit and provisioning plan

`etc/passwd`, `etc/shadow`, and `etc/group` are a frozen snapshot of a
server; `home/` contains only some home directories.  Build
`user_audit.py --root .` that prints one JSON object with:

  duplicate_uids               {"<uid>": ["user", ...]} for UIDs shared by users
  interactive_service_accounts UIDs below 1000 (except root) with a login shell
  locked_accounts              shadow passwords starting with "!"
  expired_accounts             last_change + max_days is before today
  missing_homes                regular users (UID >= 1000) without a home directory
  wheel_members                members of the wheel group
  provision_commands           one useradd command per line of new_users.txt

Provisioning format for `name:uid:group:shell`:

  useradd -u UID -g GROUP -m -s SHELL NAME        (normal login shell)
  useradd -u UID -g GROUP -M -s SHELL NAME        (nologin shell)

Do not execute useradd; this is a dry-run plan suitable for review.

Verify with:  python3 main.py verify 8
""",
    hints=[
        "Split passwd lines on ':' and unpack the first seven fields.",
        "today = int(time.time() // 86400) makes shadow date arithmetic easy.",
        "A service account is UID < 1000, but exclude UID 0 (root).",
        "Use -M when the requested shell ends with nologin, otherwise -m.",
    ],
    solution={"user_audit.py": M08_SOLUTION},
    setup=setup_m08,
    check=check_m08,
)


# ---------------------------------------------------------------------------
# Mission 09 — Processes, jobs, priorities, and scheduling
# ---------------------------------------------------------------------------
PS_TEXT = """\
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
root         1  0.0  0.1 168000 12000 ?        Ss   09:00   0:01 /sbin/init
root       220  0.0  0.0  15000  6000 ?        S    09:00   0:00 /usr/sbin/sshd
alice      330  0.0  0.0      0     0 ?        Z    09:04   0:00 [python3] <defunct>
root       440 92.5  3.2 880000 52000 ?        R    09:05  10:12 /usr/bin/ffmpeg
root       550  0.2  0.1  12000  4000 ?        D    09:05   0:00 /usr/bin/updatedb
bob        660  0.0  0.0  22000  5000 pts/0    S    09:06   0:00 /usr/bin/bash
root       770 12.0 20.0 2200000 320000 ?      S    09:06   0:20 /usr/bin/java
"""


def setup_m09(mdir: Path) -> None:
    write_file(mdir / "fixtures/ps.txt", PS_TEXT)
    write_file(mdir / "fixtures/pstree.txt", (
        "init(1)\n"
        "  sshd(220)\n"
        "    bash(660)\n"
        "  ffmpeg(440)\n"
        "  updatedb(550)\n"
        "  java(770)\n"
    ))


M09_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Find process-state and scheduling problems from command fixtures.\"\"\"
import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", default="fixtures")
    args = parser.parse_args()
    fixtures = Path(args.fixtures)

    rows = []
    for line in (fixtures / "ps.txt").read_text().splitlines()[1:]:
        fields = line.split(None, 10)
        if len(fields) < 11:
            continue
        user, pid, cpu, mem, _vsz, _rss, _tty, state, _start, _time, command = fields
        rows.append({
            "user": user, "pid": int(pid), "cpu": float(cpu),
            "mem": float(mem), "state": state, "command": command,
        })

    zombies = [row for row in rows if "Z" in row["state"]]
    blocked = [row for row in rows if "D" in row["state"]]
    top_cpu = max(rows, key=lambda row: row["cpu"])
    top_mem = max(rows, key=lambda row: row["mem"])

    parent_of = {}
    for line in (fixtures / "pstree.txt").read_text().splitlines():
        name, pid = line.strip().split("(")
        depth = (len(line) - len(line.lstrip())) // 2
        parent_of[pid.rstrip(")")] = depth

    lines = (fixtures / "pstree.txt").read_text().splitlines()
    bash_line = next(line for line in lines if "bash(" in line)
    index = lines.index(bash_line)
    parent = ""
    for previous in reversed(lines[:index]):
        if (len(previous) - len(previous.lstrip())) < (len(bash_line) - len(bash_line.lstrip())):
            parent = previous.strip().split("(")[1].rstrip(")")
            break

    print(json.dumps({
        "zombies": [{"pid": row["pid"], "user": row["user"]} for row in zombies],
        "blocked": [{"pid": row["pid"], "command": row["command"]} for row in blocked],
        "top_cpu": {"pid": top_cpu["pid"], "cpu": top_cpu["cpu"], "command": top_cpu["command"].split()[0]},
        "top_mem": {"pid": top_mem["pid"], "mem": top_mem["mem"], "command": top_mem["command"].split()[0]},
        "bash_parent": int(parent) if parent else 0,
        "running": sum(1 for row in rows if "R" in row["state"]),
    }, indent=2))


if __name__ == "__main__":
    main()
"""


def check_m09(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "proc_audit.py"
    if not script.is_file():
        return [Check("proc_audit.py exists", False, str(script))]
    checks.append(Check("proc_audit.py exists", True, str(script)))

    data, proc = script_json(script, "--fixtures", "fixtures", cwd=mdir)
    checks.append(Check("script prints valid JSON and exits 0", data is not None, output(proc)))
    if data is None:
        return checks

    ok, detail = has_keys(data, {
        "zombies", "blocked", "top_cpu", "top_mem", "bash_parent", "running",
    })
    checks.append(Check("report has every required key", ok, detail))
    checks.append(Check(
        "finds the zombie process",
        data.get("zombies") == [{"pid": 330, "user": "alice"}],
        f"got {data.get('zombies')!r}",
    ))
    checks.append(Check(
        "finds the uninterruptible blocked process",
        isinstance(data.get("blocked"), list)
        and any(item.get("pid") == 550 for item in data["blocked"]),
        f"got {data.get('blocked')!r}",
    ))
    checks.append(Check(
        "finds the CPU and memory hogs",
        isinstance(data.get("top_cpu"), dict)
        and data["top_cpu"].get("pid") == 440
        and isinstance(data.get("top_mem"), dict)
        and data["top_mem"].get("pid") == 770,
        f"top_cpu={data.get('top_cpu')!r} top_mem={data.get('top_mem')!r}",
    ))
    checks.append(Check(
        "finds bash's parent PID in the process tree",
        data.get("bash_parent") == 220,
        f"got {data.get('bash_parent')!r}",
    ))
    checks.append(Check(
        "counts running processes",
        data.get("running") == 1,
        f"got {data.get('running')!r}",
    ))

    cron = mdir / "cron.d/backup"
    checks.append(Check("cron.d/backup exists", cron.is_file(), str(cron)))
    if cron.is_file():
        text = cron.read_text()
        job = next((line for line in text.splitlines()
                    if line.strip() and not line.startswith("#") and not line.startswith("SHELL")
                    and not line.startswith("PATH")), "")
        fields = job.split()
        checks.append(Check(
            "schedules a daily 02:15 backup with logging",
            len(fields) >= 7
            and fields[0] == "15" and fields[1] == "2"
            and fields[5:7] == ["root", "/usr/local/bin/backup.sh"]
            and ">>" in job,
            f"job={job!r}",
        ))
    return checks


M09 = Mission(
    id="xk203",
    num=9,
    dir_name="xk203_processes",
    title="Processes, jobs, priorities, and scheduling",
    domain="Linux+ 2.3 Processes and jobs",
    brief="""\
MISSION 09 — Process triage and a backup schedule

Part A — build `proc_audit.py --fixtures fixtures`.  Read `ps.txt` and
`pstree.txt` and print:

  zombies     [{"pid": ..., "user": ...}, ...] for STAT containing Z
  blocked     [{"pid": ..., "command": ...}, ...] for STAT containing D
  top_cpu     {"pid": ..., "cpu": ..., "command": ...} highest %CPU
  top_mem     {"pid": ..., "mem": ..., "command": ...} highest %MEM
  bash_parent PID of bash's parent in pstree.txt
  running     count of processes with R in STAT

Part B — create `cron.d/backup` with SHELL and PATH lines, then a job that
runs `/usr/local/bin/backup.sh` as root every day at 02:15 and appends stdout
and stderr to `/var/log/backup.log`.

Remember: cron uses five time fields (minute hour day month weekday), then the
user, then the command. That is six fields before the command — do not confuse
it with a user crontab, which has only five.

Verify with:  python3 main.py verify 9
""",
    hints=[
        "ps output can be split with line.split(None, 10); the command keeps its spaces.",
        "Zombie = Z, uninterruptible sleep = D, running = R in the STAT column.",
        "A system cron.d line is: minute hour day month weekday user command.",
        "For 02:15 use: 15 2 * * * root /usr/local/bin/backup.sh >> /var/log/backup.log 2>&1",
    ],
    solution={
        "proc_audit.py": M09_SOLUTION,
        "cron.d/backup": (
            "SHELL=/bin/bash\n"
            "PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin\n"
            "15 2 * * * root /usr/local/bin/backup.sh >> /var/log/backup.log 2>&1\n"
        ),
    },
    setup=setup_m09,
    check=check_m09,
)


# ---------------------------------------------------------------------------
# Mission 10 — Software packages and systemd services
# ---------------------------------------------------------------------------
def setup_m10(mdir: Path) -> None:
    write_file(mdir / "fixtures/dpkg_status.txt", (
        "Package: openssh-server\nStatus: install ok installed\nVersion: 1:9.6p1-3ubuntu13\n\n"
        "Package: nginx\nStatus: install ok installed\nVersion: 1.24.0-2ubuntu7\n\n"
        "Package: old-utils\nStatus: deinstall ok config-files\nVersion: 1.0\n"
    ))
    write_file(mdir / "fixtures/sources.list", (
        "deb http://archive.ubuntu.com/ubuntu noble main\n"
        "deb [signed-by=/usr/share/keyrings/extra.gpg] https://repo.example.com/stable ./\n"
        "deb http://insecure.example.com/deb ./\n"
    ))
    write_file(mdir / "fixtures/systemctl_failed.txt", (
        "  UNIT LOAD ACTIVE SUB DESCRIPTION\n"
        "* nginx.service loaded failed failed A high performance web server\n"
        "  ssh.service loaded active running OpenBSD Secure Shell server\n"
    ))
    write_file(mdir / "units/nginx.service", (
        "[Unit]\nDescription=Web\nAfter=network.target\n\n"
        "[Service]\nExecStart=/usr/sbin/nginx -g 'daemon off;'\n"
        "Restart=always\nUser=www-data\n\n"
        "[Install]\nWantedBy=multi-user.target\n"
    ))
    write_file(mdir / "units/legacy.service", (
        "[Unit]\nDescription=Legacy\n\n"
        "[Service]\nExecStart=/usr/local/bin/legacy\n\n"
        "[Install]\nWantedBy=multi-user.target\n"
    ))


M10_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Audit package state, repository trust, and critical unit files.\"\"\"
import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root)
    fixtures = root / "fixtures"

    installed, config_only = [], []
    package = {}
    for line in (fixtures / "dpkg_status.txt").read_text().splitlines():
        if not line.strip():
            if package:
                name = package.get("Package", "")
                status = package.get("Status", "")
                if "installed" in status:
                    installed.append(name)
                elif "config-files" in status:
                    config_only.append(name)
                package = {}
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            package[key.strip()] = value.strip()
    if package:
        name = package.get("Package", "")
        status = package.get("Status", "")
        if "installed" in status:
            installed.append(name)
        elif "config-files" in status:
            config_only.append(name)

    untrusted = []
    for line in (fixtures / "sources.list").read_text().splitlines():
        if line.startswith("deb ") or line.startswith("deb["):
            if "signed-by=" not in line and not line.startswith("deb [signed-by"):
                untrusted.append(line)
            elif line.startswith("deb http://") and "signed-by=" not in line:
                untrusted.append(line)

    failed = []
    for line in (fixtures / "systemctl_failed.txt").read_text().splitlines()[1:]:
        fields = line.split()
        if fields and fields[0] == "*" and len(fields) > 1:
            failed.append(fields[1])

    unit_issues = {}
    for path in sorted((root / "units").glob("*.service")):
        text = path.read_text()
        issues = []
        if "Restart=" not in text:
            issues.append("missing Restart=")
        if "User=" not in text:
            issues.append("runs as root")
        if issues:
            unit_issues[path.name] = issues

    print(json.dumps({
        "installed_packages": installed,
        "config_only_packages": config_only,
        "untrusted_repos": untrusted,
        "failed_units": failed,
        "unit_issues": unit_issues,
    }, indent=2))


if __name__ == "__main__":
    main()
"""


def check_m10(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "pkg_audit.py"
    if not script.is_file():
        return [Check("pkg_audit.py exists", False, str(script))]
    checks.append(Check("pkg_audit.py exists", True, str(script)))

    data, proc = script_json(script, "--root", ".", cwd=mdir)
    checks.append(Check("script prints valid JSON and exits 0", data is not None, output(proc)))
    if data is None:
        return checks

    ok, detail = has_keys(data, {
        "installed_packages", "config_only_packages", "untrusted_repos",
        "failed_units", "unit_issues",
    })
    checks.append(Check("report has every required key", ok, detail))
    checks.append(Check(
        "separates installed packages from config-only packages",
        data.get("installed_packages") == ["openssh-server", "nginx"]
        and data.get("config_only_packages") == ["old-utils"],
        f"installed={data.get('installed_packages')!r} config={data.get('config_only_packages')!r}",
    ))
    repos = data.get("untrusted_repos")
    checks.append(Check(
        "flags every HTTP repository without signed-by",
        isinstance(repos, list)
        and len(repos) == 2
        and any("archive.ubuntu.com" in r for r in repos)
        and any("insecure.example.com" in r for r in repos),
        f"got {repos!r}",
    ))
    checks.append(Check(
        "lists the failed nginx unit",
        data.get("failed_units") == ["nginx.service"],
        f"got {data.get('failed_units')!r}",
    ))
    issues = data.get("unit_issues") if isinstance(data.get("unit_issues"), dict) else {}
    checks.append(Check(
        "flags legacy.service for restart and privilege issues",
        set(issues.get("legacy.service", [])) == {"missing Restart=", "runs as root"},
        f"got {issues!r}",
    ))
    checks.append(Check(
        "does not flag the hardened nginx.service",
        "nginx.service" not in issues,
        f"got {issues!r}",
    ))
    return checks


M10 = Mission(
    id="xk204",
    num=10,
    dir_name="xk204_packages_systemd",
    title="Software packages and systemd services",
    domain="Linux+ 2.4 Software + 2.5 systemd",
    brief="""\
MISSION 10 — Package and unit audit

Build `pkg_audit.py --root .`.  Read the fixtures and print:

  installed_packages    Package entries with "install ok installed"
  config_only_packages  entries with "deinstall ok config-files"
  untrusted_repos       repository lines that are not https AND have no
                        signed-by= option
  failed_units          units marked failed in systemctl_failed.txt
  unit_issues           {unit filename: [issues]} for units/*.service

Unit policy:
  * every service must set Restart=
  * every service must set User= (running as root is an issue)

The package fixture uses dpkg syntax. The unit files use systemd syntax.

Verify with:  python3 main.py verify 10
""",
    hints=[
        "A dpkg status stanza is separated by a blank line; collect keys until the blank line.",
        "Repository lines can start with 'deb ' or 'deb ['; signed-by= may appear in brackets.",
        "A systemd service runs as root when it has no User= directive.",
        "Check unit file names, not the Description line, when building unit_issues.",
    ],
    solution={"pkg_audit.py": M10_SOLUTION},
    setup=setup_m10,
    check=check_m10,
)


# ---------------------------------------------------------------------------
# Mission 11 — Containers
# ---------------------------------------------------------------------------
BAD_DOCKERFILE = """\
FROM python:latest
ENV API_KEY=supersecret
RUN pip install flask
CMD ["python", "app.py"]
"""

GOOD_DOCKERFILE = """\
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY app.py .
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8080
CMD ["python", "app.py"]
"""

BAD_COMPOSE = """\
services:
  web:
    image: myapp:latest
    privileged: true
    ports:
      - "8080:8080"
"""

GOOD_COMPOSE = """\
services:
  web:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - appdata:/data
    read_only: true
    cap_drop:
      - ALL
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
    networks:
      - frontend
volumes:
  appdata:
networks:
  frontend:
"""


def setup_m11(mdir: Path) -> None:
    write_file(mdir / "Dockerfile.bad", BAD_DOCKERFILE)
    write_file(mdir / "compose.bad.yaml", BAD_COMPOSE)
    write_file(mdir / "app.py", "print('hello')\n")


M11_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Lint a Dockerfile and a Compose file without third-party YAML packages.\"\"\"
import argparse
import json
import re
from pathlib import Path


def audit_dockerfile(path: Path) -> dict:
    text = path.read_text()
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    instructions = [line.split(None, 1)[0].upper() for line in lines]
    from_line = next((line for line in lines if line.upper().startswith("FROM ")), "")
    base = from_line.split(None, 1)[1] if from_line else ""
    pinned = bool(base) and ":" in base and not base.endswith(":latest")
    non_root = any(line.upper().startswith("USER ") and not line.upper().endswith("ROOT") for line in lines)
    has_cmd = "CMD" in instructions or "ENTRYPOINT" in instructions
    secrets = [line for line in lines if re.search(r"(API_KEY|PASSWORD|SECRET|TOKEN)\\s*=", line, re.I)]
    return {
        "base_image": base,
        "pinned": pinned,
        "non_root": non_root,
        "has_cmd": has_cmd,
        "secrets": secrets,
    }


def audit_compose(path: Path) -> dict:
    text = path.read_text()
    services = {}
    current = ""
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0 and stripped.endswith(":"):
            section = stripped[:-1]
            continue
        if section == "services" and indent == 2 and stripped.endswith(":"):
            current = stripped[:-1]
            services[current] = {
                "healthcheck": False, "read_only": False, "privileged": False,
                "volumes": [], "networks": [],
            }
            continue
        if current:
            if stripped.startswith("healthcheck:"):
                services[current]["healthcheck"] = True
            if stripped.startswith("read_only:") and "true" in stripped:
                services[current]["read_only"] = True
            if stripped.startswith("privileged:") and "true" in stripped:
                services[current]["privileged"] = True
            if stripped.startswith("volumes:"):
                services[current]["volumes"].append("declared")
            elif stripped.startswith("- ") and section == "services":
                item = stripped[2:].strip()
                if "/" in item or item.endswith(":/data"):
                    services[current]["volumes"].append(item)
                elif item in {"frontend", "backend", "appnet"}:
                    services[current]["networks"].append(item)
    volumes = []
    networks = []
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if indent == 0 and stripped.endswith(":"):
            section = stripped[:-1]
        elif indent == 2 and stripped.endswith(":") and section == "volumes":
            volumes.append(stripped[:-1])
        elif indent == 2 and stripped.endswith(":") and section == "networks":
            networks.append(stripped[:-1])
    return {"services": services, "volumes": volumes, "networks": networks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dockerfile", default="Dockerfile")
    parser.add_argument("--compose", default="compose.yaml")
    args = parser.parse_args()

    report = audit_dockerfile(Path(args.dockerfile))
    report.update(audit_compose(Path(args.compose)))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
"""


def check_m11(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    for name in ("Dockerfile", "compose.yaml", "container_audit.py"):
        path = mdir / name
        checks.append(Check(f"{name} exists", path.is_file(), str(path)))
    if not all((mdir / name).is_file() for name in ("Dockerfile", "compose.yaml", "container_audit.py")):
        return checks

    dockerfile = mdir / "Dockerfile"
    compose = mdir / "compose.yaml"
    script = mdir / "container_audit.py"

    text, detail = text_contains(dockerfile, [
        "FROM python:3.12-slim", "USER app", "CMD ",
    ])
    checks.append(Check("Dockerfile pins a slim base and drops to a non-root user", text, detail))
    checks.append(Check(
        "Dockerfile does not embed a secret",
        "API_KEY" not in dockerfile.read_text() and "PASSWORD" not in dockerfile.read_text(),
        "Never bake secrets into an image layer.",
    ))

    compose_text = compose.read_text()
    checks.append(Check(
        "Compose file declares a named volume, network, healthcheck, read-only root, and cap_drop",
        all(token in compose_text for token in (
            "appdata:", "frontend:", "healthcheck:", "read_only: true",
            "cap_drop:", "ALL",
        )),
        "Missing one of the required hardening or health settings.",
    ))

    data, proc = script_json(
        script, "--dockerfile", "Dockerfile", "--compose", "compose.yaml", cwd=mdir
    )
    checks.append(Check("audit script prints valid JSON", data is not None, output(proc)))
    if data is not None:
        checks.append(Check(
            "audit recognizes the hardened image",
            data.get("pinned") is True and data.get("non_root") is True
            and data.get("has_cmd") is True and data.get("secrets") == [],
            f"got {data!r}",
        ))
        services = data.get("services") if isinstance(data.get("services"), dict) else {}
        web = services.get("web", {})
        checks.append(Check(
            "audit recognizes the hardened web service",
            isinstance(web, dict) and web.get("healthcheck") is True
            and web.get("read_only") is True and web.get("privileged") is False,
            f"web={web!r}",
        ))
        checks.append(Check(
            "audit sees the named volume and network",
            data.get("volumes") == ["appdata"] and data.get("networks") == ["frontend"],
            f"volumes={data.get('volumes')!r} networks={data.get('networks')!r}",
        ))

    bad_data, bad_proc = script_json(
        script, "--dockerfile", "Dockerfile.bad", "--compose", "compose.bad.yaml", cwd=mdir
    )
    checks.append(Check("audit can inspect the bad fixtures", bad_data is not None, output(bad_proc)))
    if bad_data is not None:
        checks.append(Check(
            "audit flags latest tag, root user, and embedded secrets",
            bad_data.get("pinned") is False and bad_data.get("non_root") is False
            and bool(bad_data.get("secrets")),
            f"got {bad_data!r}",
        ))
        bad_services = bad_data.get("services") if isinstance(bad_data.get("services"), dict) else {}
        bad_web = bad_services.get("web", {})
        checks.append(Check(
            "audit flags privileged mode and a missing healthcheck",
            isinstance(bad_web, dict) and bad_web.get("privileged") is True
            and bad_web.get("healthcheck") is False,
            f"bad web={bad_web!r}",
        ))
    return checks


M11 = Mission(
    id="xk205",
    num=11,
    dir_name="xk205_containers",
    title="Containers: images, volumes, and networks",
    domain="Linux+ 2.6 Containers",
    brief="""\
MISSION 11 — Harden a container workload

The folder contains deliberately bad `Dockerfile.bad` and `compose.bad.yaml`
examples, plus a tiny `app.py`.

Write two real files and one linter:

1. `Dockerfile` for a Python 3.12 web app:
   - pinned `python:3.12-slim` base (never `latest`)
   - `WORKDIR /app`, copy app.py
   - create and switch to a non-root `app` user
   - expose 8080 and define `CMD`
   - no API keys, passwords, or tokens in ENV

2. `compose.yaml` with a `web` service that:
   - builds the image and publishes 8080
   - mounts the named volume `appdata` at /data
   - uses `read_only: true`, `cap_drop: [ALL]`, and a healthcheck
   - joins the `frontend` network

3. `container_audit.py --dockerfile FILE --compose FILE` that prints JSON with
   `base_image`, `pinned`, `non_root`, `has_cmd`, `secrets`, `services`,
   `volumes`, and `networks`. It must flag the bad fixtures correctly.

Verify with:  python3 main.py verify 11
""",
    hints=[
        "FROM python:3.12-slim is pinned; FROM python:latest is not.",
        "A container runs as root unless you create a user and add USER app.",
        "Compose healthcheck is a mapping under the service; test: is the command.",
        "You do not need PyYAML. A small indentation-aware loop is enough for these files.",
    ],
    solution={
        "Dockerfile": GOOD_DOCKERFILE,
        "compose.yaml": GOOD_COMPOSE,
        "container_audit.py": M11_SOLUTION,
    },
    setup=setup_m11,
    check=check_m11,
)


MISSIONS: list[Mission] = [M07, M08, M09, M10, M11]
