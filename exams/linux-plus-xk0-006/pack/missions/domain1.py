"""XK0-006 Domain 1 — System Management (missions 1-6)."""
from __future__ import annotations

import json
import os
import stat
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
# Mission 01 — Boot, firmware, and the filesystem hierarchy
# ---------------------------------------------------------------------------
def setup_m01(mdir: Path) -> None:
    root = mdir / "rootfs"
    for relative in (
        "bin",
        "etc/default",
        "etc/systemd/system",
        "boot",
        "dev",
        "home",
        "proc",
        "tmp",
        "usr/bin",
        "usr/lib",
        "var/log",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    write_file(root / "etc/os-release", 'ID=ubuntu\nVERSION_ID="24.04"\nNAME="Ubuntu"\n')
    write_file(root / "etc/arch", "x86_64\n")
    write_file(
        root / "etc/default/grub",
        'GRUB_TIMEOUT=5\nGRUB_CMDLINE_LINUX_DEFAULT="quiet splash mitigations=auto"\n',
    )
    write_file(root / "boot/vmlinuz-6.8.0-31-generic", "kernel image fixture\n")
    write_file(root / "boot/initrd.img-6.8.0-31-generic", "initrd fixture\n")
    write_file(root / "etc/fstab", "UUID=1111 / ext4 defaults 0 1\n")
    # /lib and /sbin are deliberately absent: the audit must catch them.


M01_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Audit a mounted root filesystem and the boot configuration around it.\"\"\"
import argparse
import json
from pathlib import Path

REQUIRED = ["/", "/bin", "/boot", "/dev", "/etc", "/home", "/lib",
            "/proc", "/sbin", "/tmp", "/usr", "/var"]


def read_os_release(root: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    path = root / "etc/os-release"
    if path.is_file():
        for line in path.read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"')
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="rootfs")
    args = parser.parse_args()
    root = Path(args.root)

    present = [name for name in REQUIRED if (root / name.lstrip("/")).exists()]
    missing = [name for name in REQUIRED if name not in present]

    os_release = read_os_release(root)
    family = "debian" if os_release.get("ID", "").lower() in {
        "debian", "ubuntu", "linuxmint", "pop"
    } else "rpm"

    boot = root / "boot"
    kernels = sorted(p.name for p in boot.glob("vmlinuz-*"))
    initrds = sorted(p.name for p in boot.glob("initrd.img-*"))
    kernel = kernels[-1].removeprefix("vmlinuz-") if kernels else ""
    initrd = initrds[-1] if initrds else ""

    grub: dict[str, str] = {}
    grub_path = root / "etc/default/grub"
    if grub_path.is_file():
        for line in grub_path.read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                grub[key.strip()] = value.strip().strip('"')

    try:
        timeout = int(grub.get("GRUB_TIMEOUT", "0"))
    except ValueError:
        timeout = 0

    arch_path = root / "etc/arch"
    arch = arch_path.read_text().strip() if arch_path.is_file() else ""

    print(json.dumps({
        "present": present,
        "missing": missing,
        "distro_family": family,
        "kernel": kernel,
        "initrd": initrd,
        "grub_timeout": timeout,
        "cmdline": grub.get("GRUB_CMDLINE_LINUX_DEFAULT", ""),
        "arch": arch,
    }, indent=2))


if __name__ == "__main__":
    main()
"""


def check_m01(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "fhs_audit.py"
    if not script.is_file():
        return [Check("fhs_audit.py exists", False, str(script))]
    checks.append(Check("fhs_audit.py exists", True, str(script)))

    data, proc = script_json(script, "--root", "rootfs", cwd=mdir)
    checks.append(Check("script prints valid JSON and exits 0", data is not None, output(proc)))
    if data is None:
        return checks

    ok, detail = has_keys(data, {
        "present", "missing", "distro_family", "kernel", "initrd",
        "grub_timeout", "cmdline", "arch",
    })
    checks.append(Check("report has every required key", ok, detail))
    checks.append(Check(
        "detects the two missing FHS directories",
        data.get("missing") == ["/lib", "/sbin"],
        f"got {data.get('missing')!r}",
    ))
    checks.append(Check(
        "classifies Ubuntu as Debian-family",
        data.get("distro_family") == "debian",
        f"got {data.get('distro_family')!r}",
    ))
    checks.append(Check(
        "finds the newest kernel image",
        data.get("kernel") == "6.8.0-31-generic",
        f"got {data.get('kernel')!r}",
    ))
    checks.append(Check(
        "finds the matching initrd",
        data.get("initrd") == "initrd.img-6.8.0-31-generic",
        f"got {data.get('initrd')!r}",
    ))
    checks.append(Check(
        "parses GRUB_TIMEOUT as an integer",
        data.get("grub_timeout") == 5,
        f"got {data.get('grub_timeout')!r}",
    ))
    checks.append(Check(
        "keeps the kernel command line",
        "mitigations=auto" in str(data.get("cmdline", "")),
        f"got {data.get('cmdline')!r}",
    ))
    checks.append(Check(
        "reports the architecture",
        data.get("arch") == "x86_64",
        f"got {data.get('arch')!r}",
    ))
    return checks


M01 = Mission(
    id="xk101",
    num=1,
    dir_name="xk101_boot_fhs",
    title="Boot, firmware, and the filesystem hierarchy",
    domain="Linux+ 1.1 Basic Linux concepts",
    brief="""\
MISSION 01 — Boot and filesystem audit

A server image has been unpacked into `rootfs/`.  Build `fhs_audit.py` so it
takes `--root rootfs` and prints one JSON object with these keys:

  present          sorted list of FHS directories that exist
  missing          sorted list of missing FHS directories
  distro_family    "debian" for Debian/Ubuntu-family, otherwise "rpm"
  kernel           version from the newest boot/vmlinuz-* file
  initrd           filename of the newest boot/initrd.img-*
  grub_timeout     GRUB_TIMEOUT as an integer
  cmdline          GRUB_CMDLINE_LINUX_DEFAULT without quotes
  arch             contents of rootfs/etc/arch

Required FHS entries: / /bin /boot /dev /etc /home /lib /proc /sbin /tmp
/usr /var

Do not hard-code the fixture answers: derive them from the files.

Verify with:  python3 main.py verify 1
""",
    hints=[
        "Path(root) / name.lstrip('/') turns '/etc' into rootfs/etc.",
        "glob('vmlinuz-*') gives you filenames; remove the vmlinuz- prefix for the version.",
        "os-release values may be quoted. Strip both the newline and the double quotes.",
    ],
    solution={"fhs_audit.py": M01_SOLUTION},
    setup=setup_m01,
    check=check_m01,
)


# ---------------------------------------------------------------------------
# Mission 02 — Kernel modules, devices, and initrd
# ---------------------------------------------------------------------------
def setup_m02(mdir: Path) -> None:
    fixtures = mdir / "fixtures"
    write_file(
        fixtures / "lsmod.txt",
        "Module                  Size  Used by\n"
        "e1000e                245760  0\n"
        "kvm_intel             380928  0\n"
        "kvm                  1146880  1 kvm_intel\n"
        "nvidia             56631296  2\n",
    )
    write_file(
        fixtures / "lspci.txt",
        "00:02.0 VGA compatible controller: Intel Corporation UHD Graphics 630 (rev 02)\n"
        "02:00.0 Ethernet controller: Intel Corporation I219-LM (rev 02)\n",
    )
    write_file(
        fixtures / "dmesg.txt",
        "[    0.000000] Linux version 6.8.0-31-generic\n"
        "[    2.113000] e1000e 0000:02:00.0: firmware: direct-loading firmware e1000e/d-3.ko\n"
        "[    4.552000] e1000e: probe of 0000:02:00.0 failed with error -5\n"
        "[    5.001000] EXT4-fs (sda1): mounted filesystem\n",
    )
    write_file(
        fixtures / "lscpu.txt",
        "Architecture:            x86_64\n"
        "Model name:              Intel(R) Core(TM) i7-8700 CPU @ 3.20GHz\n"
        "Flags:                   fpu vme sse sse2 vmx aes\n",
    )
    write_file(
        fixtures / "modinfo_e1000e.txt",
        "filename:       /lib/modules/6.8.0-31-generic/kernel/drivers/net/ethernet/intel/e1000e/e1000e.ko.zst\n"
        "license:        GPL v2\n"
        "depends:        \n",
    )
    write_file(
        fixtures / "initrd.ls",
        "kernel/x86/microcode/GenuineIntel.bin\n"
        "lib/modules/6.8.0-31-generic/kernel/drivers/net/ethernet/intel/e1000e/e1000e.ko.zst\n"
        "usr/lib/systemd/systemd\n",
    )


M02_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Read command fixtures and report module, device, CPU, and initrd facts.\"\"\"
import argparse
import json
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", default="fixtures")
    args = parser.parse_args()
    fixtures = Path(args.fixtures)

    lsmod = (fixtures / "lsmod.txt").read_text().splitlines()
    modules = [line.split()[0] for line in lsmod[1:] if line.split()]

    pci = (fixtures / "lspci.txt").read_text().splitlines()
    gpu = next((line.split()[0] for line in pci if "VGA" in line), "")
    nic = next((line.split()[0] for line in pci if "Ethernet" in line), "")

    dmesg = (fixtures / "dmesg.txt").read_text().splitlines()
    errors = [line for line in dmesg if re.search(r"failed|error", line, re.I)]

    lscpu = {}
    for line in (fixtures / "lscpu.txt").read_text().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            lscpu[key.strip()] = value.strip()
    flags = set(lscpu.get("Flags", "").split())
    virt = "vt-x" if "vmx" in flags else "amd-v" if "svm" in flags else "none"

    modinfo = {}
    for line in (fixtures / "modinfo_e1000e.txt").read_text().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            modinfo[key.strip()] = value.strip()

    initrd = (fixtures / "initrd.ls").read_text().splitlines()

    print(json.dumps({
        "loaded_modules": modules,
        "gpu_pci": gpu,
        "nic_pci": nic,
        "module_errors": errors,
        "cpu_arch": lscpu.get("Architecture", ""),
        "virtualization": virt,
        "initrd_has_e1000e": any("e1000e.ko" in line for line in initrd),
        "e1000e_license": modinfo.get("license", ""),
    }, indent=2))


if __name__ == "__main__":
    main()
"""


def check_m02(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "device_audit.py"
    if not script.is_file():
        return [Check("device_audit.py exists", False, str(script))]
    checks.append(Check("device_audit.py exists", True, str(script)))

    data, proc = script_json(script, "--fixtures", "fixtures", cwd=mdir)
    checks.append(Check("script prints valid JSON and exits 0", data is not None, output(proc)))
    if data is None:
        return checks

    ok, detail = has_keys(data, {
        "loaded_modules", "gpu_pci", "nic_pci", "module_errors", "cpu_arch",
        "virtualization", "initrd_has_e1000e", "e1000e_license",
    })
    checks.append(Check("report has every required key", ok, detail))
    checks.append(Check(
        "lists all loaded kernel modules",
        data.get("loaded_modules") == ["e1000e", "kvm_intel", "kvm", "nvidia"],
        f"got {data.get('loaded_modules')!r}",
    ))
    checks.append(Check(
        "identifies the GPU and NIC PCI addresses",
        data.get("gpu_pci") == "00:02.0" and data.get("nic_pci") == "02:00.0",
        f"gpu={data.get('gpu_pci')!r} nic={data.get('nic_pci')!r}",
    ))
    errors = data.get("module_errors")
    checks.append(Check(
        "keeps the failing e1000e probe from dmesg",
        isinstance(errors, list) and any("probe of 0000:02:00.0 failed" in line for line in errors),
        f"got {errors!r}",
    ))
    checks.append(Check(
        "reports x86_64 and VT-x support",
        data.get("cpu_arch") == "x86_64" and data.get("virtualization") == "vt-x",
        f"arch={data.get('cpu_arch')!r} virt={data.get('virtualization')!r}",
    ))
    checks.append(Check(
        "finds e1000e in the initrd",
        data.get("initrd_has_e1000e") is True,
        f"got {data.get('initrd_has_e1000e')!r}",
    ))
    checks.append(Check(
        "reports the module license",
        data.get("e1000e_license") == "GPL v2",
        f"got {data.get('e1000e_license')!r}",
    ))
    return checks


M02 = Mission(
    id="xk102",
    num=2,
    dir_name="xk102_devices",
    title="Kernel modules, devices, and initrd",
    domain="Linux+ 1.2 Device management",
    brief="""\
MISSION 02 — Device and module audit

`fixtures/` contains realistic output from `lsmod`, `lspci`, `dmesg`, `lscpu`,
`modinfo`, and `lsinitrd`.  Build `device_audit.py --fixtures fixtures` that
prints one JSON object with:

  loaded_modules      module names from lsmod, in file order
  gpu_pci             PCI address of the VGA controller
  nic_pci             PCI address of the Ethernet controller
  module_errors       dmesg lines containing failed/error (case-insensitive)
  cpu_arch            Architecture from lscpu
  virtualization      "vt-x" for vmx, "amd-v" for svm, else "none"
  initrd_has_e1000e   true when e1000e.ko appears in initrd.ls
  e1000e_license      license line from modinfo

Derive every value from the fixtures.  Do not type the answers in.

Verify with:  python3 main.py verify 2
""",
    hints=[
        "lsmod's first line is a header; slice with [1:].",
        "PCI addresses are the first whitespace-separated field of each lspci line.",
        "lscpu uses key: value lines; split each line once on ':'.",
    ],
    solution={"device_audit.py": M02_SOLUTION},
    setup=setup_m02,
    check=check_m02,
)


# ---------------------------------------------------------------------------
# Mission 03 — Storage: LVM, RAID, filesystems, and mounts
# ---------------------------------------------------------------------------
def setup_m03(mdir: Path) -> None:
    fixtures = mdir / "fixtures"
    write_file(
        fixtures / "lvs.txt",
        "  LV   VG  Attr       LSize  Pool Origin Data%  Meta%  Move Log Cpy%Sync Convert\n"
        "  root vg0 -wi-ao---- 20.00g\n"
        "  data vg0 -wi-ao---- 29.00g\n",
    )
    write_file(
        fixtures / "mdstat.txt",
        "Personalities : [raid1]\n"
        "md0 : active raid1 sdb1[0] sdc1[1](F)\n"
        "      104857600 blocks super 1.2 [2/1] [_U]\n",
    )
    write_file(
        fixtures / "df_inodes.txt",
        "Filesystem      Inodes  IUsed   IFree IUse% Mounted on\n"
        "/dev/vg0-root  1310720 1310720       0  100% /\n"
        "/dev/sda1        65536     100   65436    1% /boot\n",
    )
    write_file(
        fixtures / "fstab",
        "UUID=aaa /     ext4  defaults          0 1\n"
        "UUID=bbb /boot ext4  defaults          0 2\n"
        "UUID=ccc /var  xfs   defaults          0 2\n"
        "UUID=ddd /tmp  tmpfs defaults          0 0\n"
        "UUID=eee /home ext4  defaults          0 2\n",
    )


M03_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Audit LVM, RAID, inode pressure, and mount hardening from fixtures.\"\"\"
import argparse
import json
import re
from pathlib import Path

POLICY = {
    "/boot": {"nodev", "nosuid", "noexec"},
    "/tmp": {"nodev", "nosuid", "noexec"},
    "/var": {"nodev", "nosuid"},
    "/home": {"nodev", "nosuid"},
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", default="fixtures")
    args = parser.parse_args()
    fixtures = Path(args.fixtures)

    volumes: dict[str, str] = {}
    for line in (fixtures / "lvs.txt").read_text().splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2:
            volumes[fields[0]] = fields[1]

    mdstat = (fixtures / "mdstat.txt").read_text()
    faulty = re.findall(r"(\\S+)\\[\\d+\\]\\(F\\)", mdstat)
    raid_state = "degraded" if faulty else "healthy"

    inode_full = []
    for line in (fixtures / "df_inodes.txt").read_text().splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 6:
            try:
                percent = int(fields[4].rstrip("%"))
            except ValueError:
                continue
            if percent >= 95:
                inode_full.append(fields[5])

    unsafe = []
    for line in (fixtures / "fstab").read_text().splitlines():
        fields = line.split()
        if len(fields) < 4 or line.strip().startswith("#"):
            continue
        mountpoint = fields[1]
        options = set(fields[3].split(","))
        needed = POLICY.get(mountpoint, set())
        if not needed <= options:
            unsafe.append(mountpoint)

    print(json.dumps({
        "logical_volumes": volumes,
        "raid_state": raid_state,
        "faulty_device": faulty[0] if faulty else "",
        "inode_full": inode_full,
        "unsafe_mounts": sorted(unsafe),
    }, indent=2))


if __name__ == "__main__":
    main()
"""


def check_m03(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "storage_audit.py"
    if not script.is_file():
        return [Check("storage_audit.py exists", False, str(script))]
    checks.append(Check("storage_audit.py exists", True, str(script)))

    data, proc = script_json(script, "--fixtures", "fixtures", cwd=mdir)
    checks.append(Check("script prints valid JSON and exits 0", data is not None, output(proc)))
    if data is None:
        return checks

    ok, detail = has_keys(data, {
        "logical_volumes", "raid_state", "faulty_device", "inode_full",
        "unsafe_mounts",
    })
    checks.append(Check("report has every required key", ok, detail))
    checks.append(Check(
        "maps each logical volume to its volume group",
        data.get("logical_volumes") == {"root": "vg0", "data": "vg0"},
        f"got {data.get('logical_volumes')!r}",
    ))
    checks.append(Check(
        "marks the RAID array degraded and names the failed member",
        data.get("raid_state") == "degraded" and data.get("faulty_device") == "sdc1",
        f"state={data.get('raid_state')!r} faulty={data.get('faulty_device')!r}",
    ))
    checks.append(Check(
        "finds the inode-exhausted filesystem",
        data.get("inode_full") == ["/"],
        f"got {data.get('inode_full')!r}",
    ))
    checks.append(Check(
        "flags the mount options that violate policy",
        data.get("unsafe_mounts") == ["/boot", "/home", "/tmp", "/var"],
        f"got {data.get('unsafe_mounts')!r}",
    ))
    return checks


M03 = Mission(
    id="xk103",
    num=3,
    dir_name="xk103_storage",
    title="Storage: LVM, RAID, filesystems, and mounts",
    domain="Linux+ 1.3 Storage management",
    brief="""\
MISSION 03 — Storage audit

Build `storage_audit.py --fixtures fixtures`.  It reads:

  fixtures/lvs.txt         logical volumes
  fixtures/mdstat.txt      software RAID state
  fixtures/df_inodes.txt   inode usage
  fixtures/fstab           mount policy

Print one JSON object with:

  logical_volumes   {"<LV>": "<VG>", ...} from lvs.txt
  raid_state        "degraded" if an md member is marked (F), else "healthy"
  faulty_device     the failed member (for example "sdc1"), or ""
  inode_full        mountpoints at 95% inodes or more
  unsafe_mounts     sorted mountpoints whose options miss policy

Mount policy:

  /boot  nodev,nosuid,noexec
  /tmp   nodev,nosuid,noexec
  /var   nodev,nosuid
  /home  nodev,nosuid

Verify with:  python3 main.py verify 3
""",
    hints=[
        "lvs.txt columns are LV and VG; skip the header line.",
        "The mdstat member pattern is name[0](F) — a regular expression is natural here.",
        "fstab fields are device, mountpoint, fstype, options, dump, pass.",
    ],
    solution={"storage_audit.py": M03_SOLUTION},
    setup=setup_m03,
    check=check_m03,
)


# ---------------------------------------------------------------------------
# Mission 04 — Network configuration and tools
# ---------------------------------------------------------------------------
def setup_m04(mdir: Path) -> None:
    etc = mdir / "etc"
    fixtures = mdir / "fixtures"
    write_file(
        etc / "hosts",
        "127.0.0.1 localhost\n"
        "10.10.20.15 db.internal db\n"
        "10.10.20.16 web.internal web\n",
    )
    write_file(
        etc / "resolv.conf",
        "nameserver 10.10.20.2\n"
        "nameserver 1.1.1.1\n"
        "search corp.example\n",
    )
    write_file(etc / "nsswitch.conf", "hosts: files dns\n")
    write_file(
        fixtures / "ip_addr.txt",
        "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN\n"
        "    inet 127.0.0.1/8 scope host lo\n"
        "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9000 qdisc mq state UP\n"
        "    inet 10.10.20.15/24 brd 10.10.20.255 scope global eth0\n"
        "3: eth1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP\n"
        "    inet 10.10.20.15/24 brd 10.10.20.255 scope global eth1\n"
        "4: eth2: <BROADCAST,MULTICAST> mtu 1500 qdisc mq state DOWN\n",
    )
    write_file(
        fixtures / "ip_route.txt",
        "default via 10.10.20.1 dev eth0 proto static\n"
        "10.10.20.0/24 dev eth0 proto kernel scope link src 10.10.20.15\n",
    )
    write_file(
        fixtures / "ss.txt",
        "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
        "LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\n"
        "LISTEN 0 128 127.0.0.1:5432 0.0.0.0:*\n"
        "LISTEN 0 128 [::]:443 [::]:*\n",
    )


M04_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Read network fixtures and report configuration and conflicts.\"\"\"
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

    hosts = {}
    for line in (root / "etc/hosts").read_text().splitlines():
        fields = line.split()
        if len(fields) >= 2 and not line.startswith("#"):
            for name in fields[1:]:
                hosts[name] = fields[0]

    resolv = {}
    for line in (root / "etc/resolv.conf").read_text().splitlines():
        fields = line.split()
        if len(fields) >= 2:
            resolv.setdefault(fields[0], []).append(fields[1])

    nsswitch = {}
    for line in (root / "etc/nsswitch.conf").read_text().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            nsswitch[key.strip()] = value.strip()

    interfaces: dict[str, dict[str, str]] = {}
    current = ""
    duplicate_ips: dict[str, list[str]] = {}
    for line in (fixtures / "ip_addr.txt").read_text().splitlines():
        match = re.match(r"\\d+: (\\S+): .* mtu (\\d+)", line)
        if match:
            current = match.group(1)
            interfaces[current] = {"mtu": match.group(2)}
            continue
        match = re.search(r"inet (\\d+\\.\\d+\\.\\d+\\.\\d+)/", line)
        if match and current:
            ip = match.group(1)
            interfaces[current]["ip"] = ip
            duplicate_ips.setdefault(ip, []).append(current)

    default_gateway = ""
    for line in (fixtures / "ip_route.txt").read_text().splitlines():
        if line.startswith("default "):
            match = re.search(r"via (\\S+)", line)
            if match:
                default_gateway = match.group(1)

    ports = []
    for line in (fixtures / "ss.txt").read_text().splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 4 and fields[0] == "LISTEN":
            ports.append(int(fields[3].rsplit(":", 1)[1]))

    print(json.dumps({
        "default_gateway": default_gateway,
        "dns_servers": resolv.get("nameserver", []),
        "search_domains": resolv.get("search", []),
        "hosts_resolution": nsswitch.get("hosts", ""),
        "db_internal": hosts.get("db.internal", ""),
        "mtu_mismatch": [name for name, data in interfaces.items()
                         if data.get("mtu") != "1500" and name != "lo"],
        "duplicate_ips": {ip: names for ip, names in duplicate_ips.items()
                          if len(names) > 1},
        "listening_ports": sorted(ports),
    }, indent=2))


if __name__ == "__main__":
    main()
"""


def check_m04(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "net_audit.py"
    if not script.is_file():
        return [Check("net_audit.py exists", False, str(script))]
    checks.append(Check("net_audit.py exists", True, str(script)))

    data, proc = script_json(script, "--root", ".", cwd=mdir)
    checks.append(Check("script prints valid JSON and exits 0", data is not None, output(proc)))
    if data is None:
        return checks

    ok, detail = has_keys(data, {
        "default_gateway", "dns_servers", "search_domains", "hosts_resolution",
        "db_internal", "mtu_mismatch", "duplicate_ips", "listening_ports",
    })
    checks.append(Check("report has every required key", ok, detail))
    checks.append(Check(
        "finds the default gateway",
        data.get("default_gateway") == "10.10.20.1",
        f"got {data.get('default_gateway')!r}",
    ))
    checks.append(Check(
        "reads both DNS servers and the search domain",
        data.get("dns_servers") == ["10.10.20.2", "1.1.1.1"]
        and data.get("search_domains") == ["corp.example"],
        f"dns={data.get('dns_servers')!r} search={data.get('search_domains')!r}",
    ))
    checks.append(Check(
        "reads the hosts resolution order",
        data.get("hosts_resolution") == "files dns",
        f"got {data.get('hosts_resolution')!r}",
    ))
    checks.append(Check(
        "resolves db.internal from /etc/hosts",
        data.get("db_internal") == "10.10.20.15",
        f"got {data.get('db_internal')!r}",
    ))
    checks.append(Check(
        "finds the non-standard MTU",
        data.get("mtu_mismatch") == ["eth0"],
        f"got {data.get('mtu_mismatch')!r}",
    ))
    checks.append(Check(
        "finds the duplicate IP on eth0 and eth1",
        data.get("duplicate_ips") == {"10.10.20.15": ["eth0", "eth1"]},
        f"got {data.get('duplicate_ips')!r}",
    ))
    checks.append(Check(
        "lists listening TCP ports in order",
        data.get("listening_ports") == [22, 443, 5432],
        f"got {data.get('listening_ports')!r}",
    ))
    return checks


M04 = Mission(
    id="xk104",
    num=4,
    dir_name="xk104_network",
    title="Network configuration and troubleshooting tools",
    domain="Linux+ 1.4 Network services and configuration",
    brief="""\
MISSION 04 — Network configuration audit

Build `net_audit.py --root .`.  Read:

  etc/hosts  etc/resolv.conf  etc/nsswitch.conf
  fixtures/ip_addr.txt  fixtures/ip_route.txt  fixtures/ss.txt

Print one JSON object with:

  default_gateway   IPv4 address after "default via"
  dns_servers       nameserver addresses in order
  search_domains    search domains in order
  hosts_resolution  value of the hosts: line in nsswitch.conf
  db_internal       address for db.internal from /etc/hosts
  mtu_mismatch      non-loopback interfaces whose MTU is not 1500
  duplicate_ips     {"<ip>": ["iface", ...]} for IPs on more than one interface
  listening_ports   sorted TCP ports from LISTEN rows

The fixture deliberately contains an MTU mismatch and an IP conflict.

Verify with:  python3 main.py verify 4
""",
    hints=[
        "Parse ip_addr.txt line by line: interface lines start with a number and colon.",
        "Collect IPs in a dict of lists first, then keep the entries with more than one interface.",
        "ss local addresses look like 0.0.0.0:22 or [::]:443; rsplit(':', 1) gets the port.",
    ],
    solution={"net_audit.py": M04_SOLUTION},
    setup=setup_m04,
    check=check_m04,
)


# ---------------------------------------------------------------------------
# Mission 05 — Shell operations, pipelines, and backups
# ---------------------------------------------------------------------------
def setup_m05(mdir: Path) -> None:
    src = mdir / "src"
    write_file(src / "app.conf", "port=8080\n")
    write_file(src / "data/a.txt", "alpha\n")
    write_file(src / "data/b.txt", "bravo\n")
    write_file(src / "data/cache/c.bin", "cache\n")
    write_file(src / "logs/run.log", "started\n")
    write_file(src / "scratch.tmp", "temporary\n")


M05_SOLUTION = """\
#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: backup.sh SOURCE DEST" >&2
    exit 2
fi

src=$1
dest=$2

if [[ ! -d "$src" ]]; then
    echo "not a directory: $src" >&2
    exit 2
fi

mkdir -p "$dest"
stamp=$(date +%Y%m%d-%H%M%S)
archive="$dest/backup-$stamp.tar.gz"
files=$(find "$src" -type f ! -name '*.tmp' ! -path '*/cache/*' | wc -l)

tar -czf "$archive" --exclude='*.tmp' --exclude='*/cache/*' -C "$src" .
sha256sum "$archive" > "$dest/manifest.sha256"
mkdir -p "$dest/restore"
tar -xzf "$archive" -C "$dest/restore"

echo "archive=$archive"
echo "files=$files"
echo "sha256=$(sha256sum "$archive" | awk '{print $1}')"
"""


def check_m05(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "bin/backup.sh"
    if not script.is_file():
        return [Check("bin/backup.sh exists", False, str(script))]
    checks.append(Check("bin/backup.sh exists", True, str(script)))
    checks.append(Check(
        "script is executable",
        bool(script.stat().st_mode & stat.S_IXUSR),
        f"mode {script.stat().st_mode & 0o7777:04o}",
    ))

    text = script.read_text(encoding="utf-8", errors="replace")
    checks.append(Check(
        "uses strict shell mode (set -euo pipefail)",
        "set -euo pipefail" in text,
        "Start the script with set -euo pipefail.",
    ))

    dest = mdir / "out"
    proc = run_command(["/bin/bash", str(script), "src", "out"], cwd=mdir, timeout=30)
    checks.append(Check("backup runs successfully", proc.returncode == 0, output(proc)))
    if proc.returncode != 0:
        return checks

    archives = sorted(dest.glob("backup-*.tar.gz"))
    checks.append(Check("creates a timestamped .tar.gz archive", len(archives) == 1,
                        f"found {[p.name for p in archives]}"))
    if len(archives) != 1:
        return checks
    archive = archives[0]

    listing = run_command(
        ["/bin/sh", "-c", f"tar -tzf '{archive}'"], cwd=mdir, timeout=20
    )
    names = listing.stdout
    checks.append(Check(
        "archive contains normal files",
        all(name in names for name in ("app.conf", "data/a.txt", "data/b.txt")),
        output(listing),
    ))
    checks.append(Check(
        "archive excludes *.tmp and cache files",
        "scratch.tmp" not in names and "cache/c.bin" not in names,
        f"listing:\n{names}",
    ))

    manifest = dest / "manifest.sha256"
    checks.append(Check("writes manifest.sha256", manifest.is_file(), str(manifest)))
    if manifest.is_file():
        fields = manifest.read_text().split()
        expected = run_command(
            ["/bin/sh", "-c", f"sha256sum '{archive}'"], cwd=mdir
        )
        checks.append(Check(
            "manifest records the archive SHA-256",
            bool(fields) and fields[0] in expected.stdout,
            f"manifest={fields[:1]!r} actual={expected.stdout.split()[:1]!r}",
        ))

    restore = dest / "restore"
    checks.append(Check(
        "restores the archive into out/restore",
        (restore / "app.conf").is_file() and (restore / "data/a.txt").is_file(),
        f"restore contents: {sorted(p.name for p in restore.iterdir()) if restore.is_dir() else 'missing'}",
    ))
    checks.append(Check(
        "prints archive, file count, and checksum",
        "archive=" in proc.stdout and "files=" in proc.stdout and "sha256=" in proc.stdout,
        output(proc),
    ))

    bad = run_command(["/bin/bash", str(script)], cwd=mdir, timeout=10)
    checks.append(Check(
        "missing arguments exit 2 with usage",
        bad.returncode == 2 and "usage" in bad.stderr.lower(),
        output(bad),
    ))
    return checks


M05 = Mission(
    id="xk105",
    num=5,
    dir_name="xk105_backup",
    title="Shell operations, pipelines, and backups",
    domain="Linux+ 1.5 Shell operations + 1.6 Backup and restore",
    brief="""\
MISSION 05 — Safe backup and restore script

Build an executable `bin/backup.sh SOURCE DEST` that:

  1. Starts with `#!/usr/bin/env bash` and `set -euo pipefail`.
  2. Prints a usage message to stderr and exits 2 when it does not get
     exactly two arguments or SOURCE is not a directory.
  3. Creates DEST and a timestamped archive named `backup-YYYYmmdd-HHMMSS.tar.gz`.
  4. Excludes `*.tmp` and anything under a `cache/` directory.
  5. Writes `DEST/manifest.sha256` containing the archive checksum.
  6. Extracts the archive into `DEST/restore/`.
  7. Prints exactly these keys (one per line): archive=..., files=..., sha256=...

The fixture source is `src/`; use `out/` as the destination while testing.

This combines shell expansion, pipelines, redirection, tar, compression, and
restore verification — the core of objectives 1.5 and 1.6.

Verify with:  python3 main.py verify 5
""",
    hints=[
        "mkdir -p \"$dest\" and stamp=$(date +%Y%m%d-%H%M%S) get you started.",
        "tar --exclude='*.tmp' --exclude='*/cache/*' -czf \"$archive\" -C \"$src\" .",
        "sha256sum \"$archive\" > \"$dest/manifest.sha256\" records the checksum.",
    ],
    solution={"bin/backup.sh": M05_SOLUTION},
    setup=setup_m05,
    check=check_m05,
)


# ---------------------------------------------------------------------------
# Mission 06 — Virtualization
# ---------------------------------------------------------------------------
WEB_XML = """\
<domain type='kvm'>
  <name>web01</name>
  <memory unit='MiB'>4096</memory>
  <vcpu>4</vcpu>
  <os><type arch='x86_64'>hvm</type></os>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='/var/lib/libvirt/images/web01.qcow2'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='bridge'><source bridge='br0'/></interface>
  </devices>
</domain>
"""

DB_XML = """\
<domain type='kvm'>
  <name>db01</name>
  <memory unit='MiB'>1024</memory>
  <vcpu>2</vcpu>
  <os><type arch='x86_64'>hvm</type></os>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='/var/lib/libvirt/images/db01.qcow2'/>
      <target dev='sda' bus='sata'/>
    </disk>
    <interface type='network'><source network='default'/></interface>
  </devices>
</domain>
"""


def setup_m06(mdir: Path) -> None:
    write_file(mdir / "vms/web01.xml", WEB_XML)
    write_file(mdir / "vms/db01.xml", DB_XML)
    write_file(
        mdir / "fixtures/snapshots.txt",
        "web01 base 2026-01-10 10:00:00 +0000\n"
        "web01 pre-upgrade 2026-02-01 10:00:00 +0000\n"
    )


M06_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Audit libvirt domain XML and snapshot inventory.\"\"\"
import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

MIN_MEMORY = {"web01": 2048, "db01": 2048}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="vms")
    parser.add_argument("--snapshots", default="fixtures/snapshots.txt")
    args = parser.parse_args()

    snapshots: dict[str, list[str]] = {}
    for line in Path(args.snapshots).read_text().splitlines():
        fields = line.split()
        if len(fields) >= 2:
            snapshots.setdefault(fields[0], []).append(fields[1])

    vms = {}
    issues = []
    for path in sorted(Path(args.dir).glob("*.xml")):
        root = ET.parse(path).getroot()
        name = (root.findtext("name") or path.stem).strip()
        memory = int((root.findtext("memory") or "0").strip())
        vcpus = int((root.findtext("vcpu") or "0").strip())
        disk = root.find(".//disk")
        bus = ""
        source = ""
        if disk is not None:
            bus = disk.findtext("target") or ""
            disk_bus = disk.find("target")
            if disk_bus is not None:
                bus = disk_bus.get("bus", "")
            disk_source = disk.find("source")
            if disk_source is not None:
                source = (
                    disk_source.get("file")
                    or disk_source.get("dev")
                    or disk_source.get("volume")
                    or ""
                )
        interface = root.find(".//interface")
        net_type = interface.get("type", "") if interface is not None else ""
        net_source = ""
        if interface is not None:
            source_el = interface.find("source")
            if source_el is not None:
                net_source = (
                    source_el.get("bridge")
                    or source_el.get("network")
                    or source_el.get("dev")
                    or ""
                )
        snapshots_for_vm = snapshots.get(name, [])
        vms[name] = {
            "memory_mib": memory,
            "vcpus": vcpus,
            "disk_bus": bus,
            "disk_source": source,
            "network_type": net_type,
            "network_source": net_source,
            "domain_type": root.get("type", ""),
            "snapshots": snapshots_for_vm,
        }
        if bus != "virtio":
            issues.append(f"{name}: disk bus is {bus or 'missing'}, expected virtio")
        minimum = MIN_MEMORY.get(name, 2048)
        if memory < minimum:
            issues.append(f"{name}: memory {memory} MiB is below {minimum} MiB")
        if not snapshots_for_vm:
            issues.append(f"{name}: no snapshots")

    print(json.dumps({"vms": vms, "issues": issues}, indent=2))


if __name__ == "__main__":
    main()
"""


def check_m06(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "vm_audit.py"
    if not script.is_file():
        return [Check("vm_audit.py exists", False, str(script))]
    checks.append(Check("vm_audit.py exists", True, str(script)))

    data, proc = script_json(
        script, "--dir", "vms", "--snapshots", "fixtures/snapshots.txt", cwd=mdir
    )
    checks.append(Check("script prints valid JSON and exits 0", data is not None, output(proc)))
    if data is None:
        return checks

    ok, detail = has_keys(data, {"vms", "issues"})
    checks.append(Check("report has vms and issues", ok, detail))
    vms = data.get("vms") if isinstance(data.get("vms"), dict) else {}
    checks.append(Check(
        "inventories both domains",
        set(vms) == {"web01", "db01"},
        f"got {sorted(vms)}",
    ))
    web = vms.get("web01", {})
    checks.append(Check(
        "web01 uses 4096 MiB, 4 vCPUs, VirtIO, and a bridge",
        web.get("memory_mib") == 4096
        and web.get("vcpus") == 4
        and web.get("disk_bus") == "virtio"
        and web.get("network_type") == "bridge"
        and web.get("network_source") == "br0",
        f"web01={web!r}",
    ))
    db = vms.get("db01", {})
    checks.append(Check(
        "db01 uses a NAT network and has no snapshots",
        db.get("network_type") == "network"
        and db.get("network_source") == "default"
        and db.get("snapshots") == [],
        f"db01={db!r}",
    ))
    issues = data.get("issues") if isinstance(data.get("issues"), list) else []
    checks.append(Check(
        "flags the SATA disk on db01",
        any("db01" in item and "virtio" in item for item in issues),
        f"issues={issues!r}",
    ))
    checks.append(Check(
        "flags db01's undersized memory",
        any("db01" in item and "memory" in item for item in issues),
        f"issues={issues!r}",
    ))
    checks.append(Check(
        "flags that db01 has no snapshots",
        any("db01" in item and "snapshot" in item for item in issues),
        f"issues={issues!r}",
    ))
    checks.append(Check(
        "does not invent issues for web01",
        not any("web01" in item for item in issues),
        f"issues={issues!r}",
    ))
    return checks


M06 = Mission(
    id="xk106",
    num=6,
    dir_name="xk106_virtualization",
    title="Virtualization with QEMU, KVM, and libvirt",
    domain="Linux+ 1.7 Virtualization",
    brief="""\
MISSION 06 — VM inventory and hygiene audit

`vms/` contains two libvirt domain XML files. `fixtures/snapshots.txt`
contains `virsh snapshot-list` output.

Build `vm_audit.py --dir vms --snapshots fixtures/snapshots.txt` that prints:

  vms     {name: {memory_mib, vcpus, disk_bus, disk_source,
                  network_type, network_source, domain_type, snapshots}}
  issues  list of policy problems

Policy:
  * every disk must use the VirtIO bus
  * every VM needs at least 2048 MiB of RAM
  * every VM needs at least one snapshot
  * an issue string must name the VM and the reason

Read the XML with xml.etree.ElementTree — do not hard-code the values.

Verify with:  python3 main.py verify 6
""",
    hints=[
        "ET.parse(path).getroot() then root.findtext('name'), root.findtext('memory').",
        "The disk bus is the bus attribute on the <target> element.",
        "An <interface> has type='bridge' or type='network'; its <source> carries bridge= or network=.",
    ],
    solution={"vm_audit.py": M06_SOLUTION},
    setup=setup_m06,
    check=check_m06,
)


MISSIONS: list[Mission] = [M01, M02, M03, M04, M05, M06]
