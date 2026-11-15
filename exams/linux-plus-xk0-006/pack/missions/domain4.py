"""XK0-006 Domain 4 — Automation, Orchestration, and Scripting (missions 16-19)."""
from __future__ import annotations

import json
import stat
from pathlib import Path

from .base import (
    Check,
    Mission,
    has_keys,
    output,
    run_command,
    script_json,
    text_contains,
    write_file,
)


# ---------------------------------------------------------------------------
# Mission 16 — Automation, IaC, CI/CD, and orchestration
# ---------------------------------------------------------------------------
INVENTORY = """\
[web]
web01 ansible_host=10.0.0.11
web02 ansible_host=10.0.0.12

[db]
db01 ansible_host=10.0.0.21

[all:vars]
ansible_user=deploy
"""

PLAYBOOK = """\
- name: Configure web tier
  hosts: web
  become: true
  tasks:
    - name: Install packages
      apt:
        name: nginx
        state: present
    - name: Deploy configuration
      template:
        src: nginx.conf.j2
        dest: /etc/nginx/nginx.conf
      notify: Reload nginx
  handlers:
    - name: Reload nginx
      service:
        name: nginx
        state: reloaded
- name: Configure database
  hosts: db
  become: true
  tasks:
    - name: Install PostgreSQL
      apt:
        name: postgresql
        state: present
"""

K8S_DEPLOYMENT = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: web
          image: nginx:latest
          securityContext:
            privileged: true
"""

GOOD_PLAYBOOK = """\
- name: Harden and deploy the web tier
  hosts: web
  become: true
  vars:
    app_image: nginx:1.27.3
  tasks:
    - name: Install nginx
      package:
        name: nginx
        state: present
      notify: Reload nginx
    - name: Deploy the vhost template
      template:
        src: vhost.conf.j2
        dest: /etc/nginx/conf.d/app.conf
      notify: Reload nginx
  handlers:
    - name: Reload nginx
      service:
        name: nginx
        state: reloaded
"""

GOOD_K8S = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 2
  template:
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: web
          image: nginx:1.27.3
          securityContext:
            privileged: false
            readOnlyRootFilesystem: true
          resources:
            limits:
              cpu: "500m"
              memory: "256Mi"
            requests:
              cpu: "100m"
              memory: "128Mi"
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
            periodSeconds: 20
"""


def setup_m16(mdir: Path) -> None:
    write_file(mdir / "fixtures/inventory.ini", INVENTORY)
    write_file(mdir / "fixtures/playbook.yml", PLAYBOOK)
    write_file(mdir / "fixtures/k8s.yaml", K8S_DEPLOYMENT)


M16_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Audit Ansible inventory/playbook and Kubernetes manifest without PyYAML.\"\"\"
import argparse
import json
import re
from pathlib import Path

KNOWN_MODULES = {
    "apt", "copy", "cron", "file", "lineinfile", "package", "service",
    "shell", "command", "systemd", "template", "user", "yum", "dnf",
}


def inventory_groups(path: Path) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    current = ""
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1]
            current = "" if ":" in name else name
            if current:
                groups.setdefault(current, [])
            continue
        if current:
            groups[current].append(line.split()[0])
    return groups


def playbook_facts(path: Path) -> dict:
    text = path.read_text()
    hosts = re.findall(r"^\\s*hosts:\\s*(\\S+)", text, re.M | re.I)
    modules: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\\s{4,8}([a-z_]+):\\s*$", line)
        if match and match.group(1).lower() in KNOWN_MODULES:
            name = match.group(1).lower()
            if name not in modules:
                modules.append(name)
    return {
        "play_hosts": hosts,
        "task_modules": modules,
        "uses_become": bool(re.search(r"^\\s*become:\\s*true", text, re.M | re.I)),
        "has_handlers": "handlers:" in text,
        "handler_notify": "notify:" in text,
        "uses_vars": "vars:" in text,
    }


def k8s_facts(path: Path) -> dict:
    text = path.read_text()
    kind = re.search(r"^kind:\\s*(\\S+)", text, re.M)
    name = re.search(r"^  name:\\s*(\\S+)", text, re.M)
    image = re.search(r"^\\s*image:\\s*(\\S+)", text, re.M)
    replicas = re.search(r"^\\s*replicas:\\s*(\\d+)", text, re.M)
    return {
        "kind": kind.group(1) if kind else "",
        "name": name.group(1) if name else "",
        "image": image.group(1) if image else "",
        "replicas": int(replicas.group(1)) if replicas else 0,
        "privileged": bool(re.search(r"^\\s*privileged:\\s*true", text, re.M)),
        "has_limits": bool(re.search(r"^\\s*limits:", text, re.M)),
        "has_liveness": "livenessProbe:" in text,
        "has_readiness": "readinessProbe:" in text,
        "read_only_root": bool(
            re.search(r"readOnlyRootFilesystem:\\s*true", text)
        ),
        "non_root": bool(re.search(r"runAsNonRoot:\\s*true", text)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root)

    groups = inventory_groups(root / "fixtures/inventory.ini")
    play = playbook_facts(root / "fixtures/playbook.yml")
    k8s = k8s_facts(root / "fixtures/k8s.yaml")

    issues = []
    if k8s["image"].endswith(":latest"):
        issues.append("container image uses the mutable latest tag")
    if k8s["privileged"]:
        issues.append("container runs privileged")
    if not k8s["has_limits"]:
        issues.append("container has no resource limits")
    if not k8s["has_liveness"]:
        issues.append("container has no liveness probe")
    if not k8s["read_only_root"]:
        issues.append("container root filesystem is writable")
    if not k8s["non_root"]:
        issues.append("pod does not require a non-root user")

    print(json.dumps({
        "inventory_groups": groups,
        "play_hosts": play["play_hosts"],
        "task_modules": play["task_modules"],
        "uses_become": play["uses_become"],
        "has_handlers": play["has_handlers"],
        "handler_notify": play["handler_notify"],
        "uses_vars": play["uses_vars"],
        "k8s": k8s,
        "issues": issues,
    }, indent=2))


if __name__ == "__main__":
    main()
"""


def check_m16(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "iac_audit.py"
    if not script.is_file():
        return [Check("iac_audit.py exists", False, str(script))]
    checks.append(Check("iac_audit.py exists", True, str(script)))

    data, proc = script_json(script, "--root", ".", cwd=mdir)
    checks.append(Check("script prints valid JSON and exits 0", data is not None, output(proc)))
    if data is None:
        return checks

    ok, detail = has_keys(data, {
        "inventory_groups", "play_hosts", "task_modules", "uses_become",
        "has_handlers", "handler_notify", "uses_vars", "k8s", "issues",
    })
    checks.append(Check("report has every required key", ok, detail))
    checks.append(Check(
        "parses the inventory groups and hosts",
        data.get("inventory_groups") == {
            "web": ["web01", "web02"],
            "db": ["db01"],
        },
        f"got {data.get('inventory_groups')!r}",
    ))
    checks.append(Check(
        "reads both plays and their modules",
        data.get("play_hosts") == ["web", "db"]
        and set(data.get("task_modules") or []) >= {"apt", "template", "service"},
        f"hosts={data.get('play_hosts')!r} modules={data.get('task_modules')!r}",
    ))
    checks.append(Check(
        "detects become, handlers, notify, and vars",
        data.get("uses_become") is True
        and data.get("has_handlers") is True
        and data.get("handler_notify") is True
        and data.get("uses_vars") is False,
        f"become={data.get('uses_become')!r} handlers={data.get('has_handlers')!r} notify={data.get('handler_notify')!r} vars={data.get('uses_vars')!r}",
    ))
    k8s = data.get("k8s") if isinstance(data.get("k8s"), dict) else {}
    checks.append(Check(
        "reads the Kubernetes deployment",
        k8s.get("kind") == "Deployment"
        and k8s.get("name") == "web"
        and k8s.get("image") == "nginx:latest"
        and k8s.get("replicas") == 2,
        f"got {k8s!r}",
    ))
    checks.append(Check(
        "detects the container security problems",
        k8s.get("privileged") is True
        and k8s.get("has_limits") is False
        and k8s.get("has_liveness") is False,
        f"got {k8s!r}",
    ))
    issues = data.get("issues") if isinstance(data.get("issues"), list) else []
    checks.append(Check(
        "reports mutable tag, privileged mode, and missing limits",
        any("latest" in issue for issue in issues)
        and any("privileged" in issue for issue in issues)
        and any("limits" in issue for issue in issues),
        f"issues={issues!r}",
    ))

    playbook = mdir / "deploy/site.yml"
    checks.append(Check("deploy/site.yml exists", playbook.is_file(), str(playbook)))
    if playbook.is_file():
        text = playbook.read_text()
        ok2, detail2 = text_contains(playbook, [
            "hosts:", "become: true", "handlers:", "notify:", "nginx:1.27.3",
        ])
        checks.append(Check(
            "playbook is idempotent, privileged, and uses a handler",
            ok2,
            detail2,
        ))

    manifest = mdir / "deploy/k8s.yaml"
    checks.append(Check("deploy/k8s.yaml exists", manifest.is_file(), str(manifest)))
    if manifest.is_file():
        text = manifest.read_text()
        required = [
            "image: nginx:1.27.3", "resources:", "limits:",
            "livenessProbe:", "readinessProbe:", "readOnlyRootFilesystem: true",
            "runAsNonRoot: true", "privileged: false",
        ]
        missing = [item for item in required if item not in text]
        checks.append(Check(
            "manifest pins the image and adds limits, probes, and hardening",
            not missing,
            f"missing {missing}" if missing else "all controls present",
        ))
        checks.append(Check(
            "manifest never uses the latest tag or privileged mode",
            ":latest" not in text and "privileged: true" not in text,
            "Remove mutable tags and privileged containers.",
        ))
    return checks


M16 = Mission(
    id="xk401",
    num=16,
    dir_name="xk401_iac",
    title="Automation, IaC, CI/CD, and orchestration",
    domain="Linux+ 4.1 Automation and orchestration",
    brief="""\
MISSION 16 — Audit infrastructure as code

`fixtures/` holds a two-play Ansible playbook, an inventory, and a
Kubernetes Deployment.  Build `iac_audit.py --root .` that prints:

  inventory_groups  {"web": ["web01", "web02"], "db": ["db01"]}
  play_hosts        hosts: value for each play, in order
  task_modules      Ansible modules used by tasks (apt, template, service, ...)
  uses_become       true when become: true appears
  has_handlers      true when handlers: appears
  handler_notify    true when notify: appears
  uses_vars         true when vars: appears
  k8s               {kind, name, image, replicas, privileged, has_limits,
                     has_liveness, has_readiness, read_only_root, non_root}
  issues            concrete problems in the Kubernetes manifest

You do not need PyYAML; a careful line parser is enough for these fixtures.

Then write production-shaped versions:

  deploy/site.yml   one become: true play for the web group, a vars: block
                    with app_image: nginx:1.27.3, a task that notifies a
                    handler, and a handlers: block that reloads nginx
  deploy/k8s.yaml   Deployment named web using image nginx:1.27.3, with
                    resources limits and requests, readinessProbe,
                    livenessProbe, runAsNonRoot: true,
                    privileged: false, and readOnlyRootFilesystem: true

Verify with:  python3 main.py verify 16
""",
    hints=[
        "Inventory group headers are [name]; skip [group:vars] and [group:children].",
        "Play hosts come from lines beginning with hosts:; there are two plays.",
        "Module names sit on their own indented line, for example '      apt:'.",
        "In Kubernetes YAML, metadata name is indented two spaces; container image is deeper.",
        "Latest is a mutable tag. Pin a version such as nginx:1.27.3.",
    ],
    solution={
        "iac_audit.py": M16_SOLUTION,
        "deploy/site.yml": GOOD_PLAYBOOK,
        "deploy/k8s.yaml": GOOD_K8S,
    },
    setup=setup_m16,
    check=check_m16,
)


# ---------------------------------------------------------------------------
# Mission 17 — Production shell scripting
# ---------------------------------------------------------------------------
LOG_WEB = """\
INFO|web|started
ERROR|web|upstream timeout
WARN|web|slow request
ERROR|web|upstream timeout
INFO|web|healthy
"""

LOG_DB = """\
WARN|db|replica lag
ERROR|db|disk full
INFO|db|vacuum done
"""

LOG_CACHE = """\
WARN|cache|eviction pressure
INFO|cache|hit rate ok
"""


def setup_m17(mdir: Path) -> None:
    write_file(mdir / "logs/web.log", LOG_WEB)
    write_file(mdir / "logs/db.log", LOG_DB)
    write_file(mdir / "logs/cache.log", LOG_CACHE)


M17_SOLUTION = r"""#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "usage: audit_report.sh [-t THRESHOLD] SOURCE OUT" >&2
}

threshold=-1
while getopts ":t:h" opt; do
    case "$opt" in
        t) threshold=${OPTARG:-0} ;;
        h) usage; exit 0 ;;
        *) usage; exit 2 ;;
    esac
done
shift $((OPTIND - 1))

if [[ $# -ne 2 ]]; then
    usage
    exit 2
fi

src=$1
out=$2
if [[ ! -d "$src" ]]; then
    echo "not a directory: $src" >&2
    exit 2
fi

mkdir -p "$(dirname "$out")"
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

declare -A errors=()
declare -A warnings=()

count_level() {
    local file=$1
    local wanted=$2
    local count=0
    local level
    while IFS='|' read -r level _service _message; do
        [[ -z "${level:-}" ]] && continue
        if [[ "$level" == "$wanted" ]]; then
            count=$((count + 1))
        fi
    done < "$file"
    echo "$count"
}

for file in "$src"/*.log; do
    [[ -e "$file" ]] || continue
    service=${file##*/}
    service=${service%.log}
    errors[$service]=$(count_level "$file" ERROR)
    warnings[$service]=$(count_level "$file" WARN)
    while IFS='|' read -r level _service message; do
        if [[ "$message" =~ (timeout|disk[[:space:]]full) ]]; then
            printf '%s\n' "$service:$message" >> "$tmp"
        fi
    done < "$file"
done

{
    echo "service,errors,warnings"
    for service in "${!errors[@]}"; do
        echo "$service,${errors[$service]},${warnings[$service]}"
    done | sort
} > "$out"

total_errors=0
total_warnings=0
for service in "${!errors[@]}"; do
    total_errors=$((total_errors + errors[$service]))
    total_warnings=$((total_warnings + warnings[$service]))
done

echo "services=${#errors[@]} errors=$total_errors warnings=$total_warnings"
echo "incidents=$(wc -l < "$tmp" | tr -d ' ')"

if (( threshold >= 0 && total_errors > threshold )); then
    exit 1
fi
"""


def check_m17(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "audit_report.sh"
    if not script.is_file():
        return [Check("audit_report.sh exists", False, str(script))]
    checks.append(Check("audit_report.sh exists", True, str(script)))
    checks.append(Check(
        "audit_report.sh is executable",
        bool(script.stat().st_mode & stat.S_IXUSR),
        f"mode {stat.S_IMODE(script.stat().st_mode):04o}",
    ))

    syntax = run_command(["/bin/bash", "-n", str(script)], cwd=mdir)
    checks.append(Check("bash syntax check passes", syntax.returncode == 0, output(syntax)))
    text = script.read_text()
    constructs = [
        ("strict mode", "set -euo pipefail"),
        ("function", "count_level"),
        ("case statement", "case "),
        ("IFS", "IFS="),
        ("regex match", "=~"),
        ("local variable", "local "),
        ("parameter expansion", "${file##*/}"),
        ("command substitution", "$("),
        ("exit status", "exit 2"),
    ]
    missing = [label for label, needle in constructs if needle not in text]
    checks.append(Check(
        "script uses the required shell constructs",
        not missing,
        f"missing {missing}" if missing else "all constructs present",
    ))

    out = mdir / "reports/summary.csv"
    proc = run_command(["/bin/bash", str(script), "logs", "reports/summary.csv"], cwd=mdir)
    checks.append(Check("script runs successfully", proc.returncode == 0, output(proc)))
    checks.append(Check(
        "prints service, error, and warning totals",
        "services=3" in proc.stdout and "errors=3" in proc.stdout
        and "warnings=3" in proc.stdout,
        output(proc),
    ))
    checks.append(Check(
        "prints the incident count from the regex scan",
        "incidents=3" in proc.stdout,
        output(proc),
    ))
    checks.append(Check("creates reports/summary.csv", out.is_file(), str(out)))
    if out.is_file():
        rows = [line.strip() for line in out.read_text().splitlines() if line.strip()]
        checks.append(Check(
            "writes a sorted CSV with exact per-service counts",
            rows == [
                "service,errors,warnings",
                "cache,0,1",
                "db,1,1",
                "web,2,1",
            ],
            f"got {rows!r}",
        ))

    bad = run_command(["/bin/bash", str(script)], cwd=mdir)
    checks.append(Check(
        "missing arguments exit 2 with usage",
        bad.returncode == 2 and "usage" in bad.stderr.lower(),
        output(bad),
    ))
    missing_dir = run_command(["/bin/bash", str(script), "nope", "out.csv"], cwd=mdir)
    checks.append(Check(
        "a missing source directory exits 2",
        missing_dir.returncode == 2,
        output(missing_dir),
    ))
    bad_opt = run_command(["/bin/bash", str(script), "-x", "logs", "out.csv"], cwd=mdir)
    checks.append(Check(
        "an unknown option exits 2",
        bad_opt.returncode == 2,
        output(bad_opt),
    ))
    help_proc = run_command(["/bin/bash", str(script), "-h"], cwd=mdir)
    checks.append(Check(
        "-h prints usage and exits 0",
        help_proc.returncode == 0 and "usage" in help_proc.stderr.lower(),
        output(help_proc),
    ))
    threshold = run_command(
        ["/bin/bash", str(script), "-t", "2", "logs", "reports/threshold.csv"],
        cwd=mdir,
    )
    checks.append(Check(
        "a -t threshold above the error count exits 1",
        threshold.returncode == 1,
        output(threshold),
    ))
    return checks


M17 = Mission(
    id="xk402",
    num=17,
    dir_name="xk402_shell_scripting",
    title="Production shell scripting",
    domain="Linux+ 4.2 Shell scripting",
    brief=r"""\
MISSION 17 — Build a defensive log report

Write an executable `audit_report.sh` that accepts:

    ./audit_report.sh [-t THRESHOLD] SOURCE OUT

Rules:

  * `set -euo pipefail`, a `usage()` function, `local` variables, a `case`
    statement, `IFS='|'` reads, a `[[ ... =~ ... ]]` regex, and `${file##*/}`
    parameter expansion.
  * No arguments or the wrong number: print usage to stderr, exit 2.
  * SOURCE is not a directory: exit 2.
  * Unknown option: print usage, exit 2.  `-h`: print usage, exit 0.
  * Read every `*.log` in SOURCE.  Each line is `LEVEL|service|message`.
  * Write OUT as CSV, header `service,errors,warnings`, one row per service,
    sorted by service.
  * Print `services=N errors=N warnings=N` and `incidents=N` where incidents
    are messages matching `timeout` or `disk full`.
  * With `-t N`, exit 1 when total errors are greater than N; otherwise 0.
  * Create OUT's parent directory.

The fixture is `logs/`; write to `reports/summary.csv` while testing.

Verify with:  python3 main.py verify 17
""",
    hints=[
        "getopts ':t:h' puts an unknown option in opt as ?; call usage and exit 2.",
        "After getopts, shift $((OPTIND - 1)) leaves the positional arguments.",
        "service=${file##*/} strips the directory; service=${service%.log} strips the suffix.",
        "count_level can loop with IFS='|' read -r level _service _message.",
        "Associative arrays require bash 4: declare -A errors=() and errors[$service]=$count.",
        "Sort the CSV body in a brace group: { echo header; ... | sort; } > \"$out\".",
    ],
    solution={"audit_report.sh": M17_SOLUTION},
    setup=setup_m17,
    check=check_m17,
)


# ---------------------------------------------------------------------------
# Mission 18 — Python administration and virtual environments
# ---------------------------------------------------------------------------
DF_TEXT = """\
Filesystem     1024-blocks     Used Available Capacity Mounted on
/dev/sda1          102400000 95000000   7400000      93% /
/dev/sdb1          204800000 40960000 163840000      20% /var
tmpfs                8192000        0   8192000       0% /dev/shm
"""

REQUIREMENTS = """\
PyYAML==6.0.2
requests==2.32.3
"""

SETUP_VENV = r"""#!/usr/bin/env bash
set -euo pipefail

# This sandbox has no ensurepip, so create the environment without pip.
# On a normal host: python3 -m venv .venv && . .venv/bin/activate
python3 -m venv --without-pip venv
./venv/bin/python -m py_compile disk_report.py
"""


def setup_m18(mdir: Path) -> None:
    write_file(mdir / "fixtures/df.txt", DF_TEXT)


M18_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Report filesystem usage from df -P output, with a configurable threshold.\"\"\"
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Filesystem:
    device: str
    mount: str
    size_kib: int
    used_kib: int
    available_kib: int
    usage_percent: int


def parse_df(path: Path) -> list[Filesystem]:
    filesystems: list[Filesystem] = []
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        fields = line.split()
        if len(fields) < 6:
            continue
        device, size, used, available, capacity, mount = fields[:6]
        filesystems.append(
            Filesystem(
                device=device,
                mount=mount,
                size_kib=int(size),
                used_kib=int(used),
                available_kib=int(available),
                usage_percent=int(capacity.rstrip("%")),
            )
        )
    return filesystems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--threshold", type=int, default=85)
    args = parser.parse_args()

    root = Path(args.root)
    filesystems = parse_df(root / "fixtures/df.txt")
    over = [item.mount for item in filesystems if item.usage_percent >= args.threshold]

    print(
        json.dumps(
            {
                "filesystems": [asdict(item) for item in filesystems],
                "over_threshold": over,
                "count": len(filesystems),
                "threshold": args.threshold,
                "python": sys.version.split()[0],
                "executable": sys.executable,
                "total_used_gib": round(
                    sum(item.used_kib for item in filesystems) / 1024 / 1024, 2
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
"""


def check_m18(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "disk_report.py"
    venv_python = mdir / "venv/bin/python"
    for path, label in (
        (script, "disk_report.py"),
        (mdir / "requirements.txt", "requirements.txt"),
        (mdir / "setup.sh", "setup.sh"),
        (mdir / "venv/pyvenv.cfg", "venv/pyvenv.cfg"),
        (venv_python, "venv/bin/python"),
    ):
        checks.append(Check(f"{label} exists", path.is_file(), str(path)))
    if not script.is_file() or not venv_python.is_file():
        return checks

    requirements = mdir / "requirements.txt"
    if requirements.is_file():
        lines = [line.strip() for line in requirements.read_text().splitlines()
                 if line.strip() and not line.startswith("#")]
        checks.append(Check(
            "requirements pin exact versions",
            bool(lines) and all("==" in line for line in lines),
            f"got {lines!r}",
        ))

    compile_proc = run_command(
        [str(venv_python), "-m", "py_compile", str(script)], cwd=mdir
    )
    checks.append(Check(
        "script compiles with the venv interpreter",
        compile_proc.returncode == 0,
        output(compile_proc),
    ))

    proc = run_command(
        [str(venv_python), str(script), "--root", ".", "--threshold", "85"],
        cwd=mdir,
    )
    checks.append(Check("script runs under the venv", proc.returncode == 0, output(proc)))
    data = None
    if proc.returncode == 0:
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            checks.append(Check("output is valid JSON", False, f"{exc}\n{proc.stdout[:400]}"))
    if data is None:
        return checks
    checks.append(Check("output is a JSON object", isinstance(data, dict), str(type(data))))

    ok, detail = has_keys(data, {
        "filesystems", "over_threshold", "count", "threshold", "python",
        "executable", "total_used_gib",
    })
    checks.append(Check("report has every required key", ok, detail))
    filesystems = data.get("filesystems") if isinstance(data.get("filesystems"), list) else []
    checks.append(Check(
        "parses all three filesystems",
        len(filesystems) == 3
        and data.get("count") == 3
        and filesystems[0].get("mount") == "/"
        and filesystems[0].get("usage_percent") == 93,
        f"count={data.get('count')!r} first={filesystems[:1]!r}",
    ))
    checks.append(Check(
        "flags the root filesystem at the 85% threshold",
        data.get("over_threshold") == ["/"],
        f"got {data.get('over_threshold')!r}",
    ))
    checks.append(Check(
        "reports the venv interpreter and Python version",
        "venv" in str(data.get("executable", ""))
        and str(data.get("python", "")).startswith("3."),
        f"executable={data.get('executable')!r} python={data.get('python')!r}",
    ))

    high = run_command(
        [str(venv_python), str(script), "--root", ".", "--threshold", "95"],
        cwd=mdir,
    )
    high_data = None
    if high.returncode == 0:
        try:
            high_data = json.loads(high.stdout)
        except json.JSONDecodeError:
            pass
    checks.append(Check(
        "a 95% threshold clears every filesystem",
        isinstance(high_data, dict) and high_data.get("over_threshold") == [],
        output(high),
    ))

    text = script.read_text()
    imports = ["argparse", "dataclass", "pathlib", "json"]
    missing = [name for name in imports if name not in text]
    checks.append(Check(
        "uses argparse, dataclasses, pathlib, and json",
        not missing,
        f"missing {missing}" if missing else "all standard-library tools used",
    ))
    checks.append(Check(
        "follows basic PEP 8 layout",
        "\t" not in text
        and all(len(line) <= 100 for line in text.splitlines())
        and text.endswith("\n"),
        "Use spaces, keep lines <= 100 characters, and end with a newline.",
    ))
    setup = mdir / "setup.sh"
    checks.append(Check(
        "setup.sh recreates the environment reproducibly",
        setup.is_file()
        and "python3 -m venv" in setup.read_text()
        and "set -euo pipefail" in setup.read_text(),
        setup.read_text() if setup.is_file() else "missing",
    ))
    return checks


M18 = Mission(
    id="xk403",
    num=18,
    dir_name="xk403_python_venv",
    title="Python administration and virtual environments",
    domain="Linux+ 4.3 Python basics",
    brief="""\
MISSION 18 — A reproducible Python administration tool

Build three files:

1. `disk_report.py` — `--root . --threshold 85`
   * read `fixtures/df.txt`, skip the header, parse device, size, used,
     available, capacity, and mount
   * use a `@dataclass` for each filesystem and `pathlib.Path` for I/O
   * print JSON with `filesystems`, `over_threshold` (mounts at or above the
     threshold), `count`, `threshold`, `python`, `executable`,
     `total_used_gib`
   * keep lines <= 100 chars, spaces (no tabs), and a final newline (PEP 8)

2. `requirements.txt` — pinned dependencies, one per line (for example
   `PyYAML==6.0.2`).  Never use unpinned or `latest`.

3. `setup.sh` — `set -euo pipefail`, create `venv/`, and byte-compile the
   script.  This sandbox lacks ensurepip, so use
   `python3 -m venv --without-pip venv`.  On a normal host the lesson shows
   the standard `python3 -m venv .venv` plus `pip install -r requirements.txt`.

The checker runs `venv/bin/python disk_report.py` so the result must come from
the virtual environment, not the system interpreter.

Verify with:  python3 main.py verify 18
""",
    hints=[
        "df output can be split with line.split(); skip splitlines()[0].",
        "capacity is a string like '93%'; int(capacity.rstrip('%')) converts it.",
        "A dataclass plus dataclasses.asdict() gives clean JSON output.",
        "sys.executable inside the venv points at venv/bin/python.",
        "PEP 8: four-space indent, no tabs, 79-100 columns, newline at EOF.",
        "venv/bin/python can run py_compile even when pip is unavailable.",
    ],
    solution={
        "disk_report.py": M18_SOLUTION,
        "requirements.txt": REQUIREMENTS,
        "setup.sh": SETUP_VENV,
    },
    setup=setup_m18,
    check=check_m18,
    post_install=lambda mdir: _run_setup(mdir),
)


def _run_setup(mdir: Path) -> None:
    """Create the venv used by mission 18's reference solution."""
    run_command(["/bin/bash", str(mdir / "setup.sh")], cwd=mdir, timeout=60)


# ---------------------------------------------------------------------------
# Mission 19 — Git version control and responsible AI use
# ---------------------------------------------------------------------------
APP_PY = """\
def greet(name):
    return f"Hello, {name}!"


if __name__ == "__main__":
    print(greet("world"))
"""

README = """\
# Sample application

A tiny module used to practise Git workflow.
"""

SECRET_ENV = """\
API_KEY=do-not-commit-this
DB_PASSWORD=also-secret
"""


def setup_m19(mdir: Path) -> None:
    write_file(mdir / "app.py", APP_PY)
    write_file(mdir / "README.md", README)
    write_file(mdir / "secrets.env", SECRET_ENV)
    write_file(mdir / "notes.tmp", "scratch\n")
    write_file(mdir / "tests/test_app.py", "from app import greet\n\n\ndef test_greet():\n    assert greet('x') == 'Hello, x!'\n")


M19_SOLUTION = r"""#!/usr/bin/env bash
set -euo pipefail

git init -b main
git config user.name "Lab Learner"
git config user.email "learner@example.com"

cat > .gitignore <<'EOF'
*.env
*.tmp
__pycache__/
*.pyc
.venv/
EOF

git add .gitignore app.py README.md tests build_repo.sh
git commit -m "Initial application and test"

git checkout -b feature/greeting
cat >> app.py <<'EOF'


def farewell(name):
    return f"Goodbye, {name}!"
EOF
git add app.py
git commit -m "Add farewell helper"

git checkout main
git merge --no-ff feature/greeting -m "Merge feature/greeting"

git tag -a v1.0.0 -m "Release 1.0.0"

mkdir -p docs
cat > docs/ai-review.md <<'EOF'
# AI-assisted change review

- [x] Output reviewed by a human
- [x] Tests executed locally
- [x] No secrets or credentials in the diff
- [x] License and upstream source considered
- [x] Documentation updated
EOF
git add docs/ai-review.md
git commit -m "Document the AI review checklist"
"""


def _git(mdir: Path, *args: str) -> object:
    return run_command(["git", "-C", str(mdir), *args], cwd=mdir)


def check_m19(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    if not (mdir / ".git").exists():
        return [Check("Git repository initialized", False, ".git is missing")]

    inside = _git(mdir, "rev-parse", "--is-inside-work-tree")
    checks.append(Check(
        "Git repository initialized",
        inside.returncode == 0 and inside.stdout.strip() == "true",
        output(inside),
    ))

    name = _git(mdir, "config", "user.name")
    email = _git(mdir, "config", "user.email")
    checks.append(Check(
        "local author identity configured",
        bool(name.stdout.strip()) and bool(email.stdout.strip()),
        f"name={name.stdout.strip()!r} email={email.stdout.strip()!r}",
    ))

    branch = _git(mdir, "symbolic-ref", "--short", "HEAD")
    checks.append(Check(
        "default branch is main",
        branch.stdout.strip() == "main",
        f"got {branch.stdout.strip()!r}",
    ))
    feature = _git(mdir, "branch", "--list", "feature/greeting")
    checks.append(Check(
        "feature/greeting branch exists",
        "feature/greeting" in feature.stdout,
        output(feature),
    ))
    merged = _git(mdir, "merge-base", "--is-ancestor", "feature/greeting", "HEAD")
    checks.append(Check(
        "feature/greeting is merged into main",
        merged.returncode == 0,
        output(merged),
    ))

    log = _git(mdir, "log", "--all", "--format=%s")
    subjects = log.stdout.splitlines()
    checks.append(Check(
        "history records the feature, merge, and review commits",
        any("farewell" in subject.lower() for subject in subjects)
        and any("merge" in subject.lower() for subject in subjects)
        and any("ai review" in subject.lower() for subject in subjects),
        f"subjects={subjects!r}",
    ))
    checks.append(Check(
        "at least four commits exist",
        log.returncode == 0 and len(subjects) >= 4,
        f"count={len(subjects)}",
    ))

    tag = _git(mdir, "tag", "--list", "v1.0.0")
    tag_type = _git(mdir, "cat-file", "-t", "v1.0.0")
    checks.append(Check(
        "annotated tag v1.0.0 exists",
        tag.stdout.strip() == "v1.0.0" and tag_type.stdout.strip() == "tag",
        f"tag={tag.stdout.strip()!r} type={tag_type.stdout.strip()!r}",
    ))

    status = _git(mdir, "status", "--porcelain")
    checks.append(Check(
        "working tree is clean",
        status.returncode == 0 and status.stdout.strip() == "",
        output(status),
    ))

    tracked = _git(mdir, "ls-files")
    tracked_names = set(tracked.stdout.split())
    checks.append(Check(
        "secrets and scratch files are ignored",
        "secrets.env" not in tracked_names
        and "notes.tmp" not in tracked_names
        and ".gitignore" in tracked_names,
        f"tracked={sorted(tracked_names)!r}",
    ))
    grep = _git(mdir, "grep", "-n", "API_KEY")
    checks.append(Check(
        "no secret is committed to the repository",
        grep.returncode != 0 or not grep.stdout.strip(),
        output(grep),
    ))

    tag_tree = _git(mdir, "ls-tree", "-r", "--name-only", "v1.0.0")
    checks.append(Check(
        "the release tag contains the application and ignore rules",
        "app.py" in tag_tree.stdout and ".gitignore" in tag_tree.stdout,
        output(tag_tree),
    ))

    app = mdir / "app.py"
    checks.append(Check(
        "feature branch added farewell()",
        app.is_file() and "def farewell" in app.read_text(),
        app.read_text() if app.is_file() else "app.py missing",
    ))
    review = mdir / "docs/ai-review.md"
    checks.append(Check("docs/ai-review.md exists", review.is_file(), str(review)))
    if review.is_file():
        ok, detail = text_contains(review, [
            "human", "Tests", "No secrets", "License", "Documentation",
        ])
        checks.append(Check(
            "AI review checklist covers human review, tests, and secrets",
            ok,
            detail,
        ))
    return checks


M19 = Mission(
    id="xk404",
    num=19,
    dir_name="xk404_git_ai",
    title="Git version control and responsible AI use",
    domain="Linux+ 4.4 Git + 4.5 AI best practices",
    brief="""\
MISSION 19 — A reviewable Git workflow

The folder is a small application with `app.py`, `README.md`, a test, a
`secrets.env`, and a `notes.tmp`.

Create an executable `build_repo.sh` that performs a realistic workflow:

  1. `git init -b main` and set local `user.name` and `user.email`.
  2. Write `.gitignore` covering `*.env`, `*.tmp`, `__pycache__/`, `*.pyc`,
     and `.venv/`.
  3. Commit the app, README, tests, `.gitignore`, and your own
     `build_repo.sh` so the tree ends clean.
  4. Create `feature/greeting`, add a `farewell()` function, and commit it.
  5. Check out main and merge the branch with `--no-ff`.
  6. Create annotated tag `v1.0.0`.
  7. Add `docs/ai-review.md` with a human-review checklist covering human
     review, local tests, no secrets, license/source, and documentation, then
     commit it.

The final working tree must be clean, `secrets.env` and `notes.tmp` must never
be tracked, and no `API_KEY` may appear in tracked history.

Verify with:  python3 main.py verify 19
""",
    hints=[
        "git init -b main creates the initial branch without a global config change.",
        "git config user.name/user.email without --global keeps the lab self-contained.",
        "git merge --no-ff feature/greeting preserves an explicit merge commit.",
        "git tag -a v1.0.0 -m 'Release 1.0.0' creates an annotated tag.",
        "Commit docs/ai-review.md last so the working tree ends clean.",
        "Check with: git status --porcelain, git ls-files, git log --graph --all.",
    ],
    solution={"build_repo.sh": M19_SOLUTION},
    setup=setup_m19,
    check=check_m19,
    post_install=lambda mdir: run_command(
        ["/bin/bash", str(mdir / "build_repo.sh")], cwd=mdir, timeout=60
    ),
)


MISSIONS: list[Mission] = [M16, M17, M18, M19]
