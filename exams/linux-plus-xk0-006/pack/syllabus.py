"""Module map for CompTIA Linux+ XK0-006.

Every official objective (1.1 through 5.5) is represented. Related objectives
are grouped when the same lab exercises both ideas, but no objective is
dropped.  Each module has one written lesson and one inspectable mission.
"""
from __future__ import annotations

MODULES: list[dict] = [
    # ------------------------------------------------------------------
    # 1.0 System Management — 23%
    # ------------------------------------------------------------------
    {
        "num": 1,
        "id": "xk101",
        "part": "Part I — System Management",
        "title": "Boot, firmware, and the filesystem hierarchy",
        "lesson": "01_boot_and_fhs.md",
        "domain": "Linux+ 1.1 Basic Linux concepts",
        "summary": "Boot chain, GRUB and kernel parameters, initrd, PXE, FHS, architectures, distributions, GUI stacks, licensing.",
        "minutes": 90,
    },
    {
        "num": 2,
        "id": "xk102",
        "part": "Part I — System Management",
        "title": "Kernel modules, devices, and initrd",
        "lesson": "02_devices_and_modules.md",
        "domain": "Linux+ 1.2 Device management",
        "summary": "lsmod/modprobe/modinfo, dmesg, dmidecode, lspci/lsusb/lscpu, module dependencies, dracut and initrd contents.",
        "minutes": 90,
    },
    {
        "num": 3,
        "id": "xk103",
        "part": "Part I — System Management",
        "title": "Storage: LVM, RAID, filesystems, and mounts",
        "lesson": "03_storage.md",
        "domain": "Linux+ 1.3 Storage management",
        "summary": "PVs, VGs, LVs, mdadm, ext4/xfs/btrfs/tmpfs, fsck and resize tools, inodes, fstab options, NFS/SMB mounts.",
        "minutes": 120,
    },
    {
        "num": 4,
        "id": "xk104",
        "part": "Part I — System Management",
        "title": "Network configuration and troubleshooting tools",
        "lesson": "04_networking.md",
        "domain": "Linux+ 1.4 Network services and configuration",
        "summary": "hosts, resolv.conf, nsswitch.conf, NetworkManager, Netplan, ip, ss, dig, curl, tcpdump, MTU and routing checks.",
        "minutes": 100,
    },
    {
        "num": 5,
        "id": "xk105",
        "part": "Part I — System Management",
        "title": "Shell operations, pipelines, and backups",
        "lesson": "05_shell_and_backup.md",
        "domain": "Linux+ 1.5 Shell operations + 1.6 Backup and restore",
        "summary": "Variables, redirection, here-docs, pipelines, text utilities, tar/cpio/rsync, compression, manifests, restore drills.",
        "minutes": 120,
    },
    {
        "num": 6,
        "id": "xk106",
        "part": "Part I — System Management",
        "title": "Virtualization with QEMU, KVM, and libvirt",
        "lesson": "06_virtualization.md",
        "domain": "Linux+ 1.7 Virtualization",
        "summary": "Hypervisors, VirtIO, disk image operations, VM states, cloning, snapshots, migrations, virtual network types, virsh.",
        "minutes": 90,
    },
    # ------------------------------------------------------------------
    # 2.0 Services and User Management — 20%
    # ------------------------------------------------------------------
    {
        "num": 7,
        "id": "xk201",
        "part": "Part II — Services and User Management",
        "title": "Files, links, and filesystem metadata",
        "lesson": "07_files_and_links.md",
        "domain": "Linux+ 2.1 Files and directories",
        "summary": "File utilities, hard vs. symbolic links, inodes, stat, find/locate, lsof, diff, file types, block and character devices.",
        "minutes": 80,
    },
    {
        "num": 8,
        "id": "xk202",
        "part": "Part II — Services and User Management",
        "title": "Local account management",
        "lesson": "08_accounts.md",
        "domain": "Linux+ 2.2 Local accounts",
        "summary": "useradd/adduser, usermod, passwd, chage, groups, passwd/shadow/group, UID ranges, skel and profile templates.",
        "minutes": 100,
    },
    {
        "num": 9,
        "id": "xk203",
        "part": "Part II — Services and User Management",
        "title": "Processes, jobs, priorities, and scheduling",
        "lesson": "09_processes_and_jobs.md",
        "domain": "Linux+ 2.3 Processes and jobs",
        "summary": "/proc, ps, top, pstree, strace, process states, nice/renice, ulimit, job control, signals, cron and at.",
        "minutes": 100,
    },
    {
        "num": 10,
        "id": "xk204",
        "part": "Part II — Services and User Management",
        "title": "Software packages and systemd services",
        "lesson": "10_packages_and_systemd.md",
        "domain": "Linux+ 2.4 Software + 2.5 systemd",
        "summary": "dnf/apt, repositories and GPG, pip/npm/cargo, alternatives, service configuration, units, targets, timers, systemctl.",
        "minutes": 110,
    },
    {
        "num": 11,
        "id": "xk205",
        "part": "Part II — Services and User Management",
        "title": "Containers: images, volumes, and networks",
        "lesson": "11_containers.md",
        "domain": "Linux+ 2.6 Containers",
        "summary": "Docker/Podman/containerd/runC, Dockerfiles, layers and tags, volumes, networks, port mapping, privileged mode.",
        "minutes": 110,
    },
    # ------------------------------------------------------------------
    # 3.0 Security — 18%
    # ------------------------------------------------------------------
    {
        "num": 12,
        "id": "xk301",
        "part": "Part III — Security",
        "title": "AAA, logging, and audit trails",
        "lesson": "12_aaa_and_logging.md",
        "domain": "Linux+ 3.1 Authorization, authentication, accounting",
        "summary": "PAM, Polkit, SSSD, LDAP, Kerberos, Samba, journald, rsyslog, logrotate, auditd rules and log review.",
        "minutes": 100,
    },
    {
        "num": 13,
        "id": "xk302",
        "part": "Part III — Security",
        "title": "Firewalls, NAT, and forwarding",
        "lesson": "13_firewalls.md",
        "domain": "Linux+ 3.2 Firewalls",
        "summary": "firewalld zones and rich rules, ufw, nftables and iptables, NAT/PAT/DNAT/SNAT, stateful filtering, IP forwarding.",
        "minutes": 100,
    },
    {
        "num": 14,
        "id": "xk303",
        "part": "Part III — Security",
        "title": "OS and account hardening",
        "lesson": "14_hardening.md",
        "domain": "Linux+ 3.3 OS hardening + 3.4 Account hardening",
        "summary": "sudoers, file attributes, permissions, ACLs, SELinux, SSH hardening, restricted shells, password policy, MFA.",
        "minutes": 120,
    },
    {
        "num": 15,
        "id": "xk304",
        "part": "Part III — Security",
        "title": "Cryptography, certificates, and compliance",
        "lesson": "15_crypto_and_compliance.md",
        "domain": "Linux+ 3.5 Cryptography + 3.6 Compliance and audit",
        "summary": "GPG and LUKS2, TLS, WireGuard, hashing, certificate trust, AIDE, rkhunter, CVEs, secure destruction, banners.",
        "minutes": 120,
    },
    # ------------------------------------------------------------------
    # 4.0 Automation, Orchestration, and Scripting — 17%
    # ------------------------------------------------------------------
    {
        "num": 16,
        "id": "xk401",
        "part": "Part IV — Automation, Orchestration, and Scripting",
        "title": "Automation, IaC, CI/CD, and orchestration",
        "lesson": "16_automation_and_orchestration.md",
        "domain": "Linux+ 4.1 Automation and orchestration",
        "summary": "Ansible and Puppet models, OpenTofu, cloud-init/Kickstart, CI/CD and GitOps, Kubernetes objects, Compose.",
        "minutes": 110,
    },
    {
        "num": 17,
        "id": "xk402",
        "part": "Part IV — Automation, Orchestration, and Scripting",
        "title": "Production shell scripting",
        "lesson": "17_shell_scripting.md",
        "domain": "Linux+ 4.2 Shell scripting",
        "summary": "Expansion, quoting, functions, conditionals, loops, numeric/string tests, regex, IFS, exit codes, safe defaults.",
        "minutes": 120,
    },
    {
        "num": 18,
        "id": "xk403",
        "part": "Part IV — Automation, Orchestration, and Scripting",
        "title": "Python administration and virtual environments",
        "lesson": "18_python_administration.md",
        "domain": "Linux+ 4.3 Python basics",
        "summary": "venv, pip, packages and modules, data structures, pathlib/json/argparse, PEP 8, idempotent administration tools.",
        "minutes": 120,
    },
    {
        "num": 19,
        "id": "xk404",
        "part": "Part IV — Automation, Orchestration, and Scripting",
        "title": "Git version control and responsible AI use",
        "lesson": "19_git_and_ai.md",
        "domain": "Linux+ 4.4 Git + 4.5 AI best practices",
        "summary": "Git objects and workflow, branches, merge/rebase, tags, stash/reset, .gitignore, AI review and prompt discipline.",
        "minutes": 100,
    },
    # ------------------------------------------------------------------
    # 5.0 Troubleshooting — 22%
    # ------------------------------------------------------------------
    {
        "num": 20,
        "id": "xk501",
        "part": "Part V — Troubleshooting",
        "title": "Monitoring, SLOs, and performance analysis",
        "lesson": "20_monitoring_and_performance.md",
        "domain": "Linux+ 5.1 Monitoring + 5.5 Performance",
        "summary": "SLI/SLO/SLA, SNMP, health checks, log aggregation, thresholds, swapping, CPU/IO wait, latency and packet loss.",
        "minutes": 120,
    },
    {
        "num": 21,
        "id": "xk502",
        "part": "Part V — Troubleshooting",
        "title": "Hardware, storage, and OS triage",
        "lesson": "21_hardware_storage_os.md",
        "domain": "Linux+ 5.2 Hardware, storage, and OS issues",
        "summary": "Kernel panic, corruption, disk and inode exhaustion, GRUB failures, package conflicts, systemd units, memory leaks.",
        "minutes": 110,
    },
    {
        "num": 22,
        "id": "xk503",
        "part": "Part V — Troubleshooting",
        "title": "Network and security incident triage",
        "lesson": "22_network_and_security_triage.md",
        "domain": "Linux+ 5.3 Networking + 5.4 Security issues",
        "summary": "DNS, DHCP, routing, MTU, bonding, IP conflicts, dual stack, SELinux denials, certs, exposed services, ciphers.",
        "minutes": 120,
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
