"""XK0-006 Domain 5 — Troubleshooting (missions 20-22)."""
from __future__ import annotations

from pathlib import Path

from .base import (
    Check,
    Mission,
    has_keys,
    output,
    script_json,
    text_contains,
    write_file,
)


# ---------------------------------------------------------------------------
# Mission 20 — Monitoring, SLOs, and performance analysis
# ---------------------------------------------------------------------------
METRICS = """\
timestamp,requests,errors,latency_ms
2026-11-14T10:00:00Z,1000,2,120
2026-11-14T10:01:00Z,1000,4,130
2026-11-14T10:02:00Z,1000,6,150
2026-11-14T10:03:00Z,1000,3,160
2026-11-14T10:04:00Z,1000,5,180
2026-11-14T10:05:00Z,1000,8,210
2026-11-14T10:06:00Z,1000,4,240
2026-11-14T10:07:00Z,1000,6,320
2026-11-14T10:08:00Z,1000,10,350
2026-11-14T10:09:00Z,1000,2,140
"""

ALERTS = """\
groups:
  - name: slo
    rules:
      - alert: AvailabilityBelowSLO
        expr: sli_availability < 99.9
        for: 5m
        labels:
          severity: page
      - alert: P95LatencyHigh
        expr: latency_p95_ms > 300
        for: 10m
        labels:
          severity: ticket
      - alert: ErrorBudgetBurn
        expr: burn_rate > 1
        for: 15m
        labels:
          severity: page
"""


def setup_m20(mdir: Path) -> None:
    write_file(mdir / "fixtures/metrics.csv", METRICS)


M20_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Compute SLI/SLO health from a minute-by-minute metrics CSV.\"\"\"
import argparse
import csv
import json
import math
from pathlib import Path


def percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", default="fixtures/metrics.csv")
    parser.add_argument("--target", type=float, default=99.9)
    parser.add_argument("--latency-ms", type=int, default=300)
    args = parser.parse_args()

    rows = []
    with Path(args.metrics).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append({
                "requests": int(row["requests"]),
                "errors": int(row["errors"]),
                "latency": int(row["latency_ms"]),
            })

    total_requests = sum(row["requests"] for row in rows)
    total_errors = sum(row["errors"] for row in rows)
    latencies = [row["latency"] for row in rows]
    availability = (total_requests - total_errors) / total_requests * 100
    allowed_errors = total_requests * (1 - args.target / 100)
    budget_used = total_errors / allowed_errors * 100 if allowed_errors else 100.0
    remaining = max(0.0, 100.0 - budget_used)
    burn_rate = (total_errors / total_requests) / (1 - args.target / 100)
    p95 = percentile(latencies, 0.95)
    breaches = sum(1 for value in latencies if value > args.latency_ms)

    alerts = []
    if availability < args.target:
        alerts.append("AvailabilityBelowSLO")
    if p95 > args.latency_ms:
        alerts.append("P95LatencyHigh")
    if burn_rate > 1:
        alerts.append("ErrorBudgetBurn")

    recommendations = []
    if availability < args.target:
        recommendations.append("reduce the error rate before the next release")
    if p95 > args.latency_ms:
        recommendations.append("profile the slowest requests and add a latency budget")
    if burn_rate > 1:
        recommendations.append("freeze risky changes until the error budget recovers")
    if not recommendations:
        recommendations.append("keep the current change cadence")

    print(json.dumps({
        "total_requests": total_requests,
        "total_errors": total_errors,
        "availability_percent": round(availability, 3),
        "error_budget_percent": round(100 - args.target, 3),
        "budget_remaining_percent": round(remaining, 1),
        "burn_rate": round(burn_rate, 2),
        "p95_latency_ms": p95,
        "latency_breaches": breaches,
        "sli": round(availability, 3),
        "slo_met": availability >= args.target,
        "alerts": alerts,
        "recommendations": recommendations,
    }, indent=2))


if __name__ == "__main__":
    main()
"""


def check_m20(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "slo_report.py"
    if not script.is_file():
        return [Check("slo_report.py exists", False, str(script))]
    checks.append(Check("slo_report.py exists", True, str(script)))

    data, proc = script_json(
        script, "--metrics", "fixtures/metrics.csv", "--target", "99.9",
        "--latency-ms", "300", cwd=mdir,
    )
    checks.append(Check("script prints valid JSON and exits 0", data is not None, output(proc)))
    if data is None:
        return checks

    ok, detail = has_keys(data, {
        "total_requests", "total_errors", "availability_percent",
        "error_budget_percent", "budget_remaining_percent", "burn_rate",
        "p95_latency_ms", "latency_breaches", "sli", "slo_met", "alerts",
        "recommendations",
    })
    checks.append(Check("report has every required key", ok, detail))
    checks.append(Check(
        "totals requests and errors",
        data.get("total_requests") == 10000 and data.get("total_errors") == 50,
        f"requests={data.get('total_requests')!r} errors={data.get('total_errors')!r}",
    ))
    checks.append(Check(
        "computes 99.5% availability against a 99.9% SLO",
        data.get("availability_percent") == 99.5
        and data.get("sli") == 99.5
        and data.get("slo_met") is False,
        f"availability={data.get('availability_percent')!r} sli={data.get('sli')!r} met={data.get('slo_met')!r}",
    ))
    checks.append(Check(
        "computes budget consumption and burn rate",
        data.get("error_budget_percent") == 0.1
        and data.get("budget_remaining_percent") == 0.0
        and data.get("burn_rate") == 5.0,
        f"budget={data.get('error_budget_percent')!r} remaining={data.get('budget_remaining_percent')!r} burn={data.get('burn_rate')!r}",
    ))
    checks.append(Check(
        "computes nearest-rank p95 latency",
        data.get("p95_latency_ms") == 350,
        f"got {data.get('p95_latency_ms')!r}",
    ))
    checks.append(Check(
        "counts latency threshold breaches",
        data.get("latency_breaches") == 2,
        f"got {data.get('latency_breaches')!r}",
    ))
    checks.append(Check(
        "raises all three alerts",
        set(data.get("alerts") or [])
        == {"AvailabilityBelowSLO", "P95LatencyHigh", "ErrorBudgetBurn"},
        f"got {data.get('alerts')!r}",
    ))
    checks.append(Check(
        "recommends concrete actions",
        isinstance(data.get("recommendations"), list)
        and len(data["recommendations"]) >= 3,
        f"got {data.get('recommendations')!r}",
    ))

    alerts = mdir / "monitoring/alerts.yaml"
    checks.append(Check("monitoring/alerts.yaml exists", alerts.is_file(), str(alerts)))
    if alerts.is_file():
        text = alerts.read_text()
        required = [
            "AvailabilityBelowSLO", "P95LatencyHigh", "ErrorBudgetBurn",
            "99.9", "300", "burn_rate",
        ]
        missing = [item for item in required if item not in text]
        checks.append(Check(
            "alert rules encode availability, latency, and budget burn",
            not missing,
            f"missing {missing}" if missing else "all alert rules present",
        ))
    return checks


M20 = Mission(
    id="xk501",
    num=20,
    dir_name="xk501_monitoring",
    title="Monitoring, SLOs, and performance analysis",
    domain="Linux+ 5.1 Monitoring + 5.5 Performance",
    brief="""\
MISSION 20 — Turn metrics into an SLO verdict

`fixtures/metrics.csv` has one row per minute with `requests`, `errors`, and
`latency_ms`.

Build `slo_report.py` with:

    --metrics fixtures/metrics.csv --target 99.9 --latency-ms 300

Print one JSON object with:

  total_requests, total_errors
  availability_percent = (requests - errors) / requests * 100
  error_budget_percent = 100 - target
  budget_remaining_percent = max(0, 100 - errors / allowed_errors * 100)
  burn_rate = observed_error_rate / allowed_error_rate
  p95_latency_ms = nearest-rank 95th percentile
  latency_breaches = count of values strictly above --latency-ms
  sli = availability_percent
  slo_met = availability >= target
  alerts = subset of AvailabilityBelowSLO, P95LatencyHigh, ErrorBudgetBurn
  recommendations = concrete next actions

Then write `monitoring/alerts.yaml` with three rules named
`AvailabilityBelowSLO`, `P95LatencyHigh`, and `ErrorBudgetBurn`, using the
99.9 target, the 300 ms latency limit, and `burn_rate`.

Verify with:  python3 main.py verify 20
""",
    hints=[
        "Nearest-rank p95: sort, then index ceil(0.95 * n) - 1.",
        "Allowed errors = total_requests * (1 - target / 100); here that is 10.",
        "50 errors against a budget of 10 is a 500% draw and a burn rate of 5.0.",
        "Clamp budget_remaining_percent at 0 so an exhausted budget never looks positive.",
        "An alert rule is alert:, expr:, for:, and labels: under rules:.",
    ],
    solution={
        "slo_report.py": M20_SOLUTION,
        "monitoring/alerts.yaml": ALERTS,
    },
    setup=setup_m20,
    check=check_m20,
)


# ---------------------------------------------------------------------------
# Mission 21 — Hardware, storage, and OS triage
# ---------------------------------------------------------------------------
DMESG = """\
[    0.000000] Linux version 6.8.0-31-generic (buildd@lcy02) #31-Ubuntu
[    1.200000] EXT4-fs error (device sda1): ext4_lookup: deleted inode referenced: 1042
[    2.300000] Out of memory: Killed process 4242 (java) total-vm:8291440kB, anon-rss:6100000kB
[    3.400000] blk_update_request: I/O error, dev sdb, sector 12345 op 0x0:(READ)
[    4.500000] Kernel panic - not syncing: VFS: Unable to mount root fs on unknown-block(0,0)
"""

DF = """\
Filesystem     1024-blocks     Used Available Capacity Mounted on
/dev/sda1          102400000 102400000         0     100% /
/dev/sdb1           51200000  49664000   1536000      97% /var
/dev/sdc1          204800000  81920000 122880000      40% /home
"""

DF_INODES = """\
Filesystem      Inodes  IUsed   IFree IUse% Mounted on
/dev/sda1      6553600  98304 6455296    2% /
/dev/sdb1      3276800 3276800       0  100% /var
/dev/sdc1     12800000  512000 12288000    4% /home
"""

FREE = """\
               total        used        free      shared  buff/cache   available
Mem:        16384000    15900000      128000      512000      356000      204800
Swap:              0           0           0
"""

SYSTEMCTL = """\
  UNIT            LOAD   ACTIVE SUB    DESCRIPTION
  app.service     loaded failed failed Application backend
  nginx.service   loaded active running A high performance web server
  postgresql.service loaded active running PostgreSQL
"""

SMART = """\
Device: /dev/sdb
ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE
  5 Reallocated_Sector_Ct   0x0033   001   001   036    Pre-fail  Always   FAILING_NOW 4096
197 Current_Pending_Sector  0x0012   001   001   000    Old_age   Always   FAILING_NOW 512
"""

PKG = """\
dpkg: error processing package libfoo:amd64 (--configure):
 dependency problems - leaving unconfigured
dpkg: error processing package app-server:amd64 (--configure):
 dependency problems - leaving unconfigured
"""

GRUB = """\
set default="2"
set timeout=5

menuentry 'Ubuntu' --class ubuntu {
    linux /boot/vmlinuz-6.8.0-31-generic ro quiet splash
    initrd /boot/initrd.img-6.8.0-31-generic
}
"""

RUNBOOK = """\
# OS triage runbook

## Kernel panic
Confirm with `dmesg -T | tail -100` and `journalctl -k -b -1`. Boot the previous
kernel, check the initrd, and verify the GRUB `root=` UUID with `blkid`.

## Filesystem full and inode exhaustion
Run `df -h` and `df -i`. A filesystem full condition or exhausted inodes both
stop writes even when the other resource looks healthy. Find the consumers
with `du -xhd1 /` and `find /var -xdev -type f | wc -l`. Rotate logs, delete
stale files, or extend the logical volume.

## Filesystem corruption and I/O errors
Run `smartctl -a /dev/sdb` and check `dmesg` for block errors. Boot rescue
media, run `fsck -f` on the affected device, and restore from backup.

## systemd unit failures
Inspect `systemctl status app.service` and `journalctl -u app.service -b`.
Fix the ExecStart path, permissions, or dependency and add `Restart=on-failure`.

## Memory pressure and OOM
Check `free -h`, `vmstat 1`, and `systemd-cgtop`. Find the largest RSS process,
cap it with a memory limit, and add swap if the workload is legitimate.

## Package dependency failure
Run `dpkg --configure -a`, then `apt --fix-broken install` and review the
repository pinning before retrying the upgrade.

## GRUB misconfiguration
Validate with `grub-script-check /boot/grub/grub.cfg`, set a valid default
index, and regenerate with `update-grub`. Keep a rescue kernel available.
"""


def setup_m21(mdir: Path) -> None:
    write_file(mdir / "fixtures/dmesg.txt", DMESG)
    write_file(mdir / "fixtures/df.txt", DF)
    write_file(mdir / "fixtures/df_inodes.txt", DF_INODES)
    write_file(mdir / "fixtures/free.txt", FREE)
    write_file(mdir / "fixtures/systemctl_failed.txt", SYSTEMCTL)
    write_file(mdir / "fixtures/smart.txt", SMART)
    write_file(mdir / "fixtures/pkg.txt", PKG)
    write_file(mdir / "fixtures/grub.cfg", GRUB)


M21_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Triage hardware, storage, and OS evidence into prioritized findings.\"\"\"
import argparse
import json
import re
from pathlib import Path


def usage_by_mount(path: Path) -> dict[str, int]:
    values = {}
    for line in path.read_text().splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 6 and fields[4].endswith("%"):
            values[fields[5]] = int(fields[4].rstrip("%"))
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root)
    fixtures = root / "fixtures"

    dmesg = (fixtures / "dmesg.txt").read_text().splitlines()
    disk = usage_by_mount(fixtures / "df.txt")
    inodes = usage_by_mount(fixtures / "df_inodes.txt")

    findings = []
    require_reboot = False

    for line in dmesg:
        lowered = line.lower()
        if "kernel panic" in lowered:
            findings.append({
                "severity": "critical",
                "area": "kernel",
                "symptom": "kernel panic",
                "evidence": line.strip(),
                "action": "boot the previous kernel and inspect the initrd and root= parameter",
            })
            require_reboot = True
        elif "ext4-fs error" in lowered or "filesystem error" in lowered:
            findings.append({
                "severity": "critical",
                "area": "storage",
                "symptom": "filesystem corruption",
                "evidence": line.strip(),
                "action": "boot rescue media, run fsck on the affected device, and restore from backup",
            })
            require_reboot = True
        elif "out of memory" in lowered:
            findings.append({
                "severity": "critical",
                "area": "memory",
                "symptom": "out of memory kill",
                "evidence": line.strip(),
                "action": "find the leaking process and add memory limits or swap",
            })
        elif "i/o error" in lowered:
            findings.append({
                "severity": "high",
                "area": "hardware",
                "symptom": "block device I/O error",
                "evidence": line.strip(),
                "action": "check SMART health and replace the failing disk",
            })

    for mount, percent in disk.items():
        if percent >= 95:
            findings.append({
                "severity": "critical",
                "area": "storage",
                "symptom": "filesystem full",
                "evidence": f"{mount} is {percent}% used",
                "action": "delete stale files, rotate logs, or extend the filesystem",
            })
    for mount, percent in inodes.items():
        if percent >= 95:
            findings.append({
                "severity": "critical",
                "area": "storage",
                "symptom": "inode exhaustion",
                "evidence": f"{mount} has {percent}% inodes used",
                "action": "find directories with millions of small files and remove them",
            })

    free = {}
    for line in (fixtures / "free.txt").read_text().splitlines():
        fields = line.split()
        if fields and fields[0] in {"Mem:", "Swap:"}:
            free[fields[0]] = [int(value) for value in fields[1:4]]
    total_mem, _, _ = free.get("Mem:", [0, 0, 0])
    available = 0
    for line in (fixtures / "free.txt").read_text().splitlines():
        fields = line.split()
        if fields and fields[0] == "Mem:" and len(fields) >= 7:
            available = int(fields[6])
    memory_pressure = total_mem > 0 and available / total_mem < 0.05
    no_swap = free.get("Swap:", [0])[0] == 0
    if memory_pressure:
        findings.append({
            "severity": "critical",
            "area": "memory",
            "symptom": "memory pressure",
            "evidence": f"{available} KiB available of {total_mem} KiB; swap total {free.get('Swap:', [0])[0]}",
            "action": "identify the largest RSS processes and add swap or memory",
        })

    failed_units = []
    for line in (fixtures / "systemctl_failed.txt").read_text().splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0].endswith(".service") and fields[2] == "failed":
            failed_units.append(fields[0])
    for unit in failed_units:
        findings.append({
            "severity": "high",
            "area": "systemd",
            "symptom": "failed systemd unit",
            "evidence": f"{unit} is failed",
            "action": f"inspect journalctl -u {unit} and fix the ExecStart or dependency",
        })

    smart = (fixtures / "smart.txt").read_text()
    smart_failures = []
    if "FAILING_NOW" in smart:
        match = re.search(r"Device:\\s*(\\S+)", smart)
        if match:
            smart_failures.append(match.group(1))
        findings.append({
            "severity": "critical",
            "area": "hardware",
            "symptom": "SMART failure",
            "evidence": "Reallocated or pending sectors report FAILING_NOW",
            "action": "replace the disk and restore data from backup",
        })

    pkg_text = (fixtures / "pkg.txt").read_text()
    package_issues = "dependency problems" in pkg_text
    if package_issues:
        findings.append({
            "severity": "high",
            "area": "packages",
            "symptom": "package dependency failure",
            "evidence": pkg_text.strip().splitlines()[0],
            "action": "run dpkg --configure -a and fix or remove the broken dependency",
        })

    grub = (fixtures / "grub.cfg").read_text()
    grub_issues = []
    default_match = re.search(r'set default="(\\d+)"', grub)
    menuentries = len(re.findall(r"^\\s*menuentry\\s", grub, re.M))
    if default_match and int(default_match.group(1)) >= menuentries:
        grub_issues.append("default boot entry index is out of range")
    linux_lines = [line for line in grub.splitlines() if line.strip().startswith("linux ")]
    if linux_lines and all("root=" not in line for line in linux_lines):
        grub_issues.append("kernel command line has no root= parameter")
    if not menuentries:
        grub_issues.append("no menuentry is defined")
    if grub_issues:
        findings.append({
            "severity": "critical",
            "area": "bootloader",
            "symptom": "GRUB misconfiguration",
            "evidence": "; ".join(grub_issues),
            "action": "regenerate grub.cfg and verify the default entry and root= UUID",
        })

    severity_order = {"critical": 0, "high": 1, "medium": 2}
    findings.sort(key=lambda item: (severity_order.get(item["severity"], 9), item["area"]))

    recommendations = []
    if memory_pressure and no_swap:
        recommendations.append("add a swap file or increase RAM; there is no swap device")
    if disk and max(disk.values()) >= 95:
        recommendations.append("extend or clean the full filesystem before it becomes read-only")
    if smart_failures:
        recommendations.append("replace the SMART-failing disk and verify backups")
    if failed_units:
        recommendations.append("fix failed units and enable Restart= policies")
    if grub_issues:
        recommendations.append("validate GRUB with grub-script-check and a rescue boot")
    if package_issues:
        recommendations.append("repair the package database before the next upgrade")

    print(json.dumps({
        "findings": findings,
        "critical_count": sum(1 for item in findings if item["severity"] == "critical"),
        "requires_reboot": require_reboot,
        "filesystems_full": sorted(mount for mount, pct in disk.items() if pct >= 95),
        "inodes_full": sorted(mount for mount, pct in inodes.items() if pct >= 95),
        "memory_pressure": memory_pressure,
        "swap_total_kib": free.get("Swap:", [0])[0],
        "failed_units": failed_units,
        "smart_failures": smart_failures,
        "package_issues": package_issues,
        "grub_issues": grub_issues,
        "recommendations": recommendations,
    }, indent=2))


if __name__ == "__main__":
    main()
"""


def check_m21(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "os_triage.py"
    if not script.is_file():
        return [Check("os_triage.py exists", False, str(script))]
    checks.append(Check("os_triage.py exists", True, str(script)))

    data, proc = script_json(script, "--root", ".", cwd=mdir)
    checks.append(Check("script prints valid JSON and exits 0", data is not None, output(proc)))
    if data is None:
        return checks

    ok, detail = has_keys(data, {
        "findings", "critical_count", "requires_reboot", "filesystems_full",
        "inodes_full", "memory_pressure", "swap_total_kib", "failed_units",
        "smart_failures", "package_issues", "grub_issues", "recommendations",
    })
    checks.append(Check("report has every required key", ok, detail))
    checks.append(Check(
        "finds the full filesystems and exhausted inodes",
        data.get("filesystems_full") == ["/", "/var"]
        and data.get("inodes_full") == ["/var"],
        f"disk={data.get('filesystems_full')!r} inodes={data.get('inodes_full')!r}",
    ))
    checks.append(Check(
        "detects memory pressure with no swap",
        data.get("memory_pressure") is True and data.get("swap_total_kib") == 0,
        f"pressure={data.get('memory_pressure')!r} swap={data.get('swap_total_kib')!r}",
    ))
    checks.append(Check(
        "finds the failed unit and the SMART failure",
        data.get("failed_units") == ["app.service"]
        and data.get("smart_failures") == ["/dev/sdb"],
        f"units={data.get('failed_units')!r} smart={data.get('smart_failures')!r}",
    ))
    checks.append(Check(
        "detects the package and GRUB problems",
        data.get("package_issues") is True
        and "default boot entry index is out of range" in (data.get("grub_issues") or [])
        and "kernel command line has no root= parameter" in (data.get("grub_issues") or []),
        f"packages={data.get('package_issues')!r} grub={data.get('grub_issues')!r}",
    ))
    findings = data.get("findings") if isinstance(data.get("findings"), list) else []
    symptoms = {item.get("symptom") for item in findings if isinstance(item, dict)}
    checks.append(Check(
        "classifies kernel, corruption, I/O, OOM, boot, and storage findings",
        {
            "kernel panic", "filesystem corruption", "block device I/O error",
            "out of memory kill", "GRUB misconfiguration", "filesystem full",
            "inode exhaustion", "failed systemd unit", "SMART failure",
            "package dependency failure",
        } <= symptoms,
        f"got {sorted(symptoms)!r}",
    ))
    checks.append(Check(
        "marks the kernel panic as a reboot condition",
        data.get("requires_reboot") is True,
        f"got {data.get('requires_reboot')!r}",
    ))
    checks.append(Check(
        "orders critical findings before high findings",
        isinstance(findings, list) and findings
        and findings[0].get("severity") == "critical",
        f"first={findings[:1]!r}",
    ))
    checks.append(Check(
        "produces at least five recommendations",
        isinstance(data.get("recommendations"), list)
        and len(data["recommendations"]) >= 5,
        f"got {data.get('recommendations')!r}",
    ))

    runbook = mdir / "runbook.md"
    checks.append(Check("runbook.md exists", runbook.is_file(), str(runbook)))
    if runbook.is_file():
        ok2, detail2 = text_contains(runbook, [
            "Kernel panic", "inode", "filesystem full", "systemd",
            "memory", "GRUB", "smartctl", "dmesg", "journalctl",
        ])
        checks.append(Check(
            "runbook covers every triage area and the evidence commands",
            ok2,
            detail2,
        ))
    return checks


M21 = Mission(
    id="xk502",
    num=21,
    dir_name="xk502_os_triage",
    title="Hardware, storage, and OS triage",
    domain="Linux+ 5.2 Hardware, storage, and OS issues",
    brief="""\
MISSION 21 — Triage a failing server

`fixtures/` contains dmesg, df, df -i, free, systemctl, SMART, dpkg, and GRUB
evidence from one broken server.

Build `os_triage.py --root .` that prints:

  findings            ordered list of {severity, area, symptom, evidence, action}
  critical_count      number of critical findings
  requires_reboot     true when the kernel panicked or corruption was found
  filesystems_full    mounts at 95% or more
  inodes_full         mounts at 95% inodes or more
  memory_pressure     true when MemAvailable is under 5% of total
  swap_total_kib      Swap total from free
  failed_units        failed systemd units
  smart_failures      devices reporting FAILING_NOW
  package_issues      true when dpkg reports dependency problems
  grub_issues         detected default-entry and root= problems
  recommendations     prioritized remediation steps

Recognize these symptoms at minimum: kernel panic, filesystem corruption,
out-of-memory kill, block-device I/O error, filesystem full, inode exhaustion,
failed systemd unit, SMART failure, package dependency failure, and GRUB
misconfiguration.  Sort critical findings before high findings.

Also write `runbook.md` explaining how to confirm and fix each area, naming the
real commands (`dmesg`, `journalctl`, `smartctl`, `fsck`, `grub-script-check`,
`dpkg --configure -a`).

Verify with:  python3 main.py verify 21
""",
    hints=[
        "df and df -i have the same percentage and mount columns; one parser works for both.",
        "free -m style output: fields[6] of the Mem: row is available memory.",
        "A unit is failed when fields[2] == 'failed' and fields[0] ends with .service.",
        "The GRUB default index is out of range when it is >= the number of menuentry lines.",
        "A missing root= on every linux line means the kernel cannot find its root filesystem.",
        "Sort with a severity rank: critical 0, high 1, medium 2.",
    ],
    solution={
        "os_triage.py": M21_SOLUTION,
        "runbook.md": RUNBOOK,
    },
    setup=setup_m21,
    check=check_m21,
)


# ---------------------------------------------------------------------------
# Mission 22 — Network and security incident triage
# ---------------------------------------------------------------------------
IP_ADDR = """\
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN
    inet 127.0.0.1/8 scope host lo
2: eth0: <BROADCAST,MULTICAST> mtu 1500 qdisc mq state DOWN
3: eth1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP
    inet 10.0.0.15/24 brd 10.0.0.255 scope global eth1
4: eth2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP
    inet 10.0.0.15/24 brd 10.0.0.255 scope global eth2
5: eth3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9000 qdisc mq state UP
    inet 10.0.0.16/24 brd 10.0.0.255 scope global eth3
"""

IP_ROUTE = """\
10.0.0.0/24 dev eth1 proto kernel scope link src 10.0.0.15
10.0.1.0/24 dev eth3 proto kernel scope link src 10.0.0.16
"""

RESOLV = """\
nameserver 10.0.0.53
options edns0 trust-ad
"""

DIG = """\
; <<>> DiG 9.18 <<>> app.internal
;; ->>HEADER<<- opcode: QUERY, status: SERVFAIL, id: 4242
;; QUESTION SECTION:
;app.internal.                  IN      A
"""

SS = """\
State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process
LISTEN 0      128    0.0.0.0:22         0.0.0.0:*
LISTEN 0      128    0.0.0.0:23         0.0.0.0:*
LISTEN 0      128    0.0.0.0:21         0.0.0.0:*
LISTEN 0      128    127.0.0.1:5432     0.0.0.0:*
LISTEN 0      128    [::]:443           [::]:*
"""

SELINUX = """\
type=AVC msg=audit(1763124000.123:88): avc:  denied  { read } for  pid=1234 comm="nginx" name="index.html" scontext=system_u:system_r:httpd_t:s0 tcontext=system_u:object_r:user_home_t:s0 tclass=file permissive=0
type=AVC msg=audit(1763124001.456:89): avc:  denied  { open } for  pid=2234 comm="php-fpm" name="cache.db" scontext=system_u:system_r:httpd_t:s0 tcontext=system_u:object_r:var_lib_t:s0 tclass=file permissive=0
"""

TLS = """\
CONNECTED(00000003)
depth=0 CN = app.internal
verify error:num=18:self-signed certificate
verify return:1
---
Protocol  : TLSv1
Cipher    : AES128-SHA
"""

FIREWALL = """\
table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        tcp dport 22 accept
        tcp dport 23 accept
        tcp dport 3306 accept
    }
}
"""

TRIAGE = """\
# Network and security triage runbook

## Link and MTU
Confirm with `ip -br addr` and `ip link`. Bring a down link up with
`ip link set eth0 up`. Set a consistent MTU, then prove it with
`ping -M do -s 1472 <peer>`; a 9000-byte MTU on one host causes black-hole
packets and random timeouts.

## Duplicate IP and routing
Run `ip addr` and `ip route`. A duplicate address is visible as the same
address on two interfaces; remove one with `ip addr del`. Add or repair the
default route with `ip route add default via <gateway>` or fix the
NetworkManager/DHCP configuration.

## DNS
Use `dig app.internal`, `dig @10.0.0.53 app.internal`, and
`resolvectl query app.internal`. SERVFAIL points at the resolver, zone
delegation, or a firewall blocking UDP/TCP 53.

## SELinux
Inspect denials with `ausearch -m AVC -ts recent` and `sealert -a
/var/log/audit/audit.log`. Restore labels with `restorecon -Rv /var/www`,
check booleans with `getsebool -a`, and only then consider a targeted policy
module from `audit2allow`.

## TLS
Test with `openssl s_client -connect app.internal:443 -servername
app.internal`. Replace self-signed certificates with a CA-issued certificate
and require TLS 1.2 or newer with a modern cipher list.

## Exposed services
Inventory sockets with `ss -tulpn`. Disable telnet (23) and FTP (21) in favour
of SSH/SFTP, and restrict MySQL 3306 to the application subnet in nftables,
firewalld, or ufw.
"""


def setup_m22(mdir: Path) -> None:
    write_file(mdir / "fixtures/ip_addr.txt", IP_ADDR)
    write_file(mdir / "fixtures/ip_route.txt", IP_ROUTE)
    write_file(mdir / "fixtures/dig.txt", DIG)
    write_file(mdir / "fixtures/ss.txt", SS)
    write_file(mdir / "fixtures/selinux_denials.txt", SELINUX)
    write_file(mdir / "fixtures/tls.txt", TLS)
    write_file(mdir / "fixtures/firewall.txt", FIREWALL)
    write_file(mdir / "etc/resolv.conf", RESOLV)


M22_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Triage network and security evidence into root causes and fixes.\"\"\"
import argparse
import json
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root)
    fixtures = root / "fixtures"

    interfaces: dict[str, dict[str, str]] = {}
    current = ""
    for line in (fixtures / "ip_addr.txt").read_text().splitlines():
        header = re.match(r"\\d+: (\\S+): .* mtu (\\d+).* state (\\S+)", line)
        if header:
            current = header.group(1)
            interfaces[current] = {"mtu": header.group(2), "state": header.group(3)}
            continue
        match = re.search(r"inet (\\d+\\.\\d+\\.\\d+\\.\\d+)/", line)
        if match and current:
            interfaces[current]["ip"] = match.group(1)

    addresses: dict[str, list[str]] = {}
    for name, data in interfaces.items():
        if "ip" in data:
            addresses.setdefault(data["ip"], []).append(name)
    duplicate_ips = {ip: names for ip, names in addresses.items() if len(names) > 1}
    link_down = sorted(name for name, data in interfaces.items()
                       if data.get("state") == "DOWN" and name != "lo")
    mtu_mismatch = sorted(name for name, data in interfaces.items()
                          if name != "lo" and data.get("mtu") != "1500")

    default_gateway = ""
    for line in (fixtures / "ip_route.txt").read_text().splitlines():
        if line.startswith("default "):
            match = re.search(r"via (\\S+)", line)
            if match:
                default_gateway = match.group(1)

    dig = (fixtures / "dig.txt").read_text()
    status_match = re.search(r"status: (\\w+)", dig)
    dns_status = status_match.group(1) if status_match else "UNKNOWN"

    listening: set[int] = set()
    for line in (fixtures / "ss.txt").read_text().splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 4 and fields[0] == "LISTEN":
            try:
                listening.add(int(fields[3].rsplit(":", 1)[1]))
            except ValueError:
                continue
    insecure_services = sorted(port for port in listening if port in {21, 23, 25, 80})

    denials = []
    for line in (fixtures / "selinux_denials.txt").read_text().splitlines():
        if "avc:" not in line:
            continue
        permission = re.search(r"denied\\s+\\{\\s*(\\w+)\\s*\\}", line)
        comm = re.search(r'comm="([^"]+)"', line)
        target = re.search(r"tcontext=(?:\\w+:){2}([^:]+):", line)
        denials.append({
            "permission": permission.group(1) if permission else "",
            "comm": comm.group(1) if comm else "",
            "target_type": target.group(1) if target else "",
        })

    tls = (fixtures / "tls.txt").read_text()
    protocol_match = re.search(r"Protocol\\s*:\\s*(\\S+)", tls)
    cipher_match = re.search(r"Cipher\\s*:\\s*(\\S+)", tls)
    protocol = protocol_match.group(1) if protocol_match else ""
    cipher = cipher_match.group(1) if cipher_match else ""
    tls_issues = []
    if "self-signed" in tls:
        tls_issues.append("self-signed certificate")
    if protocol in {"TLSv1", "TLSv1.1", "SSLv3"}:
        tls_issues.append(f"obsolete {protocol} protocol")
    if cipher and "SHA" in cipher and "SHA256" not in cipher and "SHA384" not in cipher:
        tls_issues.append(f"weak cipher suite {cipher}")

    firewall_ports = sorted({
        int(value)
        for value in re.findall(r"tcp dport\\s+(\\d+)\\s+accept", (fixtures / "firewall.txt").read_text())
    })

    issues = []
    if link_down:
        issues.append({
            "severity": "high",
            "category": "link",
            "evidence": f"interfaces down: {link_down}",
            "action": "check the cable, switch port, and ip link set <iface> up",
        })
    if not default_gateway:
        issues.append({
            "severity": "critical",
            "category": "routing",
            "evidence": "no default route is present",
            "action": "add a default route or fix the DHCP/NetworkManager configuration",
        })
    if duplicate_ips:
        issues.append({
            "severity": "critical",
            "category": "ip-conflict",
            "evidence": f"duplicate addresses: {duplicate_ips}",
            "action": "remove the duplicate address and use DHCP reservations or static planning",
        })
    if mtu_mismatch:
        issues.append({
            "severity": "high",
            "category": "mtu",
            "evidence": f"non-standard MTU on {mtu_mismatch}",
            "action": "set a consistent MTU and test with ping -M do -s 1472",
        })
    if dns_status != "NOERROR":
        issues.append({
            "severity": "critical",
            "category": "dns",
            "evidence": f"dig status is {dns_status} for app.internal",
            "action": "check the resolver, zone delegation, and firewall to 10.0.0.53",
        })
    if insecure_services:
        issues.append({
            "severity": "critical",
            "category": "security",
            "evidence": f"insecure services listening: {insecure_services}",
            "action": "disable telnet/FTP and replace them with SSH/SFTP",
        })
    if denials:
        issues.append({
            "severity": "high",
            "category": "selinux",
            "evidence": f"{len(denials)} AVC denials, first comm={denials[0]['comm']}",
            "action": "restore the correct context with restorecon or add a targeted policy",
        })
    if tls_issues:
        issues.append({
            "severity": "critical",
            "category": "tls",
            "evidence": ", ".join(tls_issues),
            "action": "use a CA-issued certificate and require TLS 1.2 or newer",
        })
    if 3306 in firewall_ports:
        issues.append({
            "severity": "critical",
            "category": "firewall",
            "evidence": "the firewall accepts 3306 from any source",
            "action": "restrict the database port to the application subnet",
        })

    recommendations = [item["action"] for item in issues]
    print(json.dumps({
        "default_gateway": default_gateway,
        "duplicate_ips": duplicate_ips,
        "mtu_mismatch": mtu_mismatch,
        "link_down": link_down,
        "dns_status": dns_status,
        "dns_ok": dns_status == "NOERROR",
        "listening_ports": sorted(listening),
        "insecure_services": insecure_services,
        "selinux_denials": denials,
        "selinux_denial_count": len(denials),
        "tls_protocol": protocol,
        "tls_cipher": cipher,
        "tls_issues": tls_issues,
        "firewall_open_ports": firewall_ports,
        "issues": issues,
        "recommendations": recommendations,
    }, indent=2))


if __name__ == "__main__":
    main()
"""


def check_m22(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "net_triage.py"
    if not script.is_file():
        return [Check("net_triage.py exists", False, str(script))]
    checks.append(Check("net_triage.py exists", True, str(script)))

    data, proc = script_json(script, "--root", ".", cwd=mdir)
    checks.append(Check("script prints valid JSON and exits 0", data is not None, output(proc)))
    if data is None:
        return checks

    ok, detail = has_keys(data, {
        "default_gateway", "duplicate_ips", "mtu_mismatch", "link_down",
        "dns_status", "dns_ok", "listening_ports", "insecure_services",
        "selinux_denials", "selinux_denial_count", "tls_protocol",
        "tls_cipher", "tls_issues", "firewall_open_ports", "issues",
        "recommendations",
    })
    checks.append(Check("report has every required key", ok, detail))
    checks.append(Check(
        "finds the missing default gateway and duplicate IP",
        data.get("default_gateway") == ""
        and data.get("duplicate_ips") == {"10.0.0.15": ["eth1", "eth2"]},
        f"gateway={data.get('default_gateway')!r} duplicates={data.get('duplicate_ips')!r}",
    ))
    checks.append(Check(
        "finds the down link and the MTU mismatch",
        data.get("link_down") == ["eth0"]
        and data.get("mtu_mismatch") == ["eth3"],
        f"down={data.get('link_down')!r} mtu={data.get('mtu_mismatch')!r}",
    ))
    checks.append(Check(
        "reads the failing DNS status",
        data.get("dns_status") == "SERVFAIL" and data.get("dns_ok") is False,
        f"status={data.get('dns_status')!r} ok={data.get('dns_ok')!r}",
    ))
    checks.append(Check(
        "finds telnet and FTP and keeps the local database private",
        data.get("insecure_services") == [21, 23]
        and data.get("listening_ports") == [21, 22, 23, 443, 5432],
        f"insecure={data.get('insecure_services')!r} listening={data.get('listening_ports')!r}",
    ))
    denials = data.get("selinux_denials") if isinstance(data.get("selinux_denials"), list) else []
    checks.append(Check(
        "parses both SELinux AVC denials",
        data.get("selinux_denial_count") == 2
        and {item.get("comm") for item in denials} == {"nginx", "php-fpm"}
        and {item.get("permission") for item in denials} == {"read", "open"},
        f"got {denials!r}",
    ))
    checks.append(Check(
        "detects the self-signed certificate, TLSv1, and SHA1 cipher",
        data.get("tls_protocol") == "TLSv1"
        and len(data.get("tls_issues") or []) == 3
        and any("self-signed" in issue for issue in data["tls_issues"])
        and any("TLSv1" in issue for issue in data["tls_issues"])
        and any("AES128-SHA" in issue for issue in data["tls_issues"]),
        f"protocol={data.get('tls_protocol')!r} issues={data.get('tls_issues')!r}",
    ))
    checks.append(Check(
        "finds the exposed database port",
        data.get("firewall_open_ports") == [22, 23, 3306]
        and any(item.get("category") == "firewall" for item in (data.get("issues") or [])),
        f"ports={data.get('firewall_open_ports')!r}",
    ))
    categories = {
        item.get("category") for item in (data.get("issues") or [])
        if isinstance(item, dict)
    }
    checks.append(Check(
        "covers link, routing, conflict, MTU, DNS, security, SELinux, TLS, and firewall",
        {"link", "routing", "ip-conflict", "mtu", "dns", "security", "selinux", "tls", "firewall"}
        <= categories,
        f"got {sorted(categories)!r}",
    ))
    checks.append(Check(
        "recommends one remediation per issue",
        isinstance(data.get("recommendations"), list)
        and len(data["recommendations"]) == len(data.get("issues") or []),
        f"issues={len(data.get('issues') or [])} recommendations={len(data.get('recommendations') or [])}",
    ))

    triage = mdir / "triage.md"
    checks.append(Check("triage.md exists", triage.is_file(), str(triage)))
    if triage.is_file():
        ok2, detail2 = text_contains(triage, [
            "dig", "ip route", "MTU", "duplicate", "restorecon",
            "ausearch", "openssl s_client", "ss -tulpn", "3306",
        ])
        checks.append(Check(
            "triage runbook names the diagnostic and remediation commands",
            ok2,
            detail2,
        ))
    return checks


M22 = Mission(
    id="xk503",
    num=22,
    dir_name="xk503_network_security_triage",
    title="Network and security incident triage",
    domain="Linux+ 5.3 Networking + 5.4 Security issues",
    brief="""\
MISSION 22 — Diagnose a network and security incident

`fixtures/` and `etc/resolv.conf` hold evidence from a host that cannot reach
its application: interface state, routes, dig output, sockets, SELinux AVCs,
a TLS handshake, and firewall rules.

Build `net_triage.py --root .` that prints:

  default_gateway       address after "default via", or ""
  duplicate_ips         {"<ip>": ["iface", ...]}
  mtu_mismatch          non-loopback interfaces whose MTU is not 1500
  link_down             non-loopback interfaces in state DOWN
  dns_status            status: value from dig (for example SERVFAIL)
  dns_ok                true only for NOERROR
  listening_ports       sorted TCP LISTEN ports
  insecure_services     sorted listening ports in {21, 23, 25, 80}
  selinux_denials       [{permission, comm, target_type}, ...]
  selinux_denial_count  number of AVC denials
  tls_protocol          Protocol: value from the handshake
  tls_cipher            Cipher: value
  tls_issues            self-signed, obsolete protocol, weak cipher
  firewall_open_ports   sorted dports accepted by nftables
  issues                [{severity, category, evidence, action}, ...]
  recommendations       one action per issue

Then write `triage.md` as a runbook that uses the real commands: `ip route`,
`ip addr`, `dig`, `ss -tulpn`, `ausearch`, `restorecon`, `openssl s_client`,
and names the exposed 3306 database port.

Verify with:  python3 main.py verify 22
""",
    hints=[
        "ip addr headers match r'\\d+: (\\S+): .* mtu (\\d+).* state (\\S+)'.",
        "Collect IPs into a dict of lists to find conflicts across interfaces.",
        "For SELinux, parse the braces after 'denied', comm=\"...\", and tcontext=<user>:<role>:<type>:.",
        "TLSv1, TLSv1.1, and SSLv3 are obsolete; AES128-SHA is a SHA1 cipher.",
        "ss local addresses end in :port, including [::]:443, so rsplit(':', 1) is safe.",
        "Restrict MySQL 3306 to the application subnet instead of any source.",
    ],
    solution={
        "net_triage.py": M22_SOLUTION,
        "triage.md": TRIAGE,
    },
    setup=setup_m22,
    check=check_m22,
)


MISSIONS: list[Mission] = [M20, M21, M22]
