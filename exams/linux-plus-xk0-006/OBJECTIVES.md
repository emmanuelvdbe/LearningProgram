# CompTIA Linux+ XK0-006 — objectives to module map

The official objectives document (`objectives/CompTIA Linux+ XK0-006 Exam
Objectives (5.0).pdf`) defines five domains and 29 objectives. This pack turns
them into 22 study modules, each with one written lesson and one hands-on
mission.

| Domain | Weight | Modules |
| --- | --- | --- |
| 1.0 System Management | 23% | 1–6 |
| 2.0 Services and User Management | 20% | 7–11 |
| 3.0 Security | 18% | 12–15 |
| 4.0 Automation, Orchestration, and Scripting | 17% | 16–19 |
| 5.0 Troubleshooting | 22% | 20–22 |

## Objective map

| Objective | Official wording | Module | Lesson | Mission |
| --- | --- | --- | --- | --- |
| 1.1 | Explain basic Linux concepts. | 1 · `xk101` | `01_boot_and_fhs.md` | Boot, firmware, and the filesystem hierarchy |
| 1.2 | Summarize Linux device management concepts and tools. | 2 · `xk102` | `02_devices_and_modules.md` | Kernel modules, devices, and initrd |
| 1.3 | Given a scenario, manage storage in a Linux system. | 3 · `xk103` | `03_storage.md` | Storage: LVM, RAID, filesystems, and mounts |
| 1.4 | Given a scenario, manage network services and configurations on a Linux server. | 4 · `xk104` | `04_networking.md` | Network configuration and troubleshooting tools |
| 1.5 | Given a scenario, manage a Linux system using common shell operations. | 5 · `xk105` | `05_shell_and_backup.md` | Shell operations, pipelines, and backups |
| 1.6 | Given a scenario, perform backup and restore operations for a Linux server. | 5 · `xk105` | `05_shell_and_backup.md` | Shell operations, pipelines, and backups |
| 1.7 | Summarize virtualization on Linux systems. | 6 · `xk106` | `06_virtualization.md` | Virtualization with QEMU, KVM, and libvirt |
| 2.1 | Given a scenario, manage files and directories on a Linux system. | 7 · `xk201` | `07_files_and_links.md` | Files, links, and filesystem metadata |
| 2.2 | Given a scenario, perform local account management in a Linux environment. | 8 · `xk202` | `08_accounts.md` | Local account management |
| 2.3 | Given a scenario, manage processes and jobs. | 9 · `xk203` | `09_processes_and_jobs.md` | Processes, jobs, priorities, and scheduling |
| 2.4 | Given a scenario, configure and manage software. | 10 · `xk204` | `10_packages_and_systemd.md` | Software packages and systemd services |
| 2.5 | Given a scenario, manage Linux using systemd. | 10 · `xk204` | `10_packages_and_systemd.md` | Software packages and systemd services |
| 2.6 | Given a scenario, manage applications in a container. | 11 · `xk205` | `11_containers.md` | Containers: images, volumes, and networks |
| 3.1 | Summarize authorization, authentication, and accounting methods. | 12 · `xk301` | `12_aaa_and_logging.md` | AAA, logging, and audit trails |
| 3.2 | Given a scenario, configure and implement firewalls. | 13 · `xk302` | `13_firewalls.md` | Firewalls, NAT, and forwarding |
| 3.3 | Given a scenario, apply OS hardening techniques. | 14 · `xk303` | `14_hardening.md` | OS and account hardening |
| 3.4 | Explain account hardening techniques and best practices. | 14 · `xk303` | `14_hardening.md` | OS and account hardening |
| 3.5 | Explain cryptographic concepts and technologies. | 15 · `xk304` | `15_crypto_and_compliance.md` | Cryptography, certificates, and compliance |
| 3.6 | Explain the importance of compliance and audit procedures. | 15 · `xk304` | `15_crypto_and_compliance.md` | Cryptography, certificates, and compliance |
| 4.1 | Summarize automation and orchestration use cases and techniques. | 16 · `xk401` | `16_automation_and_orchestration.md` | Automation, IaC, CI/CD, and orchestration |
| 4.2 | Given a scenario, perform automated tasks using shell scripting. | 17 · `xk402` | `17_shell_scripting.md` | Production shell scripting |
| 4.3 | Summarize Python basics used for Linux administration. | 18 · `xk403` | `18_python_administration.md` | Python administration and virtual environments |
| 4.4 | Given a scenario, implement version control using Git. | 19 · `xk404` | `19_git_and_ai.md` | Git version control and responsible AI use |
| 4.5 | Summarize best practices and responsible uses of AI. | 19 · `xk404` | `19_git_and_ai.md` | Git version control and responsible AI use |
| 5.1 | Summarize monitoring concepts and configurations. | 20 · `xk501` | `20_monitoring_and_performance.md` | Monitoring, SLOs, and performance analysis |
| 5.2 | Given a scenario, analyze and troubleshoot hardware, storage, and OS issues. | 21 · `xk502` | `21_hardware_storage_os.md` | Hardware, storage, and OS triage |
| 5.3 | Given a scenario, analyze and troubleshoot networking issues. | 22 · `xk503` | `22_network_and_security_triage.md` | Network and security incident triage |
| 5.4 | Given a scenario, analyze and troubleshoot security issues. | 22 · `xk503` | `22_network_and_security_triage.md` | Network and security incident triage |
| 5.5 | Given a scenario, analyze and troubleshoot performance issues. | 20 · `xk501` | `20_monitoring_and_performance.md` | Monitoring, SLOs, and performance analysis |

## Where objectives are combined

Seven modules intentionally merge closely related objectives:

- **5** — 1.5 shell operations and 1.6 backup/restore share one realistic
  maintenance workflow.
- **10** — 2.4 package management and 2.5 systemd both describe how software
  becomes a running service.
- **14** — 3.3 OS hardening and 3.4 account hardening are applied together in
  one `harden.sh`.
- **15** — 3.5 cryptography and 3.6 compliance/audit produce the same evidence:
  keys, hashes, banners, and a written audit record.
- **19** — 4.4 Git and 4.5 responsible AI use meet in the review checklist that
  every generated change must pass.
- **20** — 5.1 monitoring and 5.5 performance analysis share SLIs, SLOs,
  percentiles, and the diagnostic toolbox.
- **22** — 5.3 network troubleshooting and 5.4 security troubleshooting follow
  the same bottom-up evidence chain.

## Pack layout

```
exams/linux-plus-xk0-006/
    exam.json                       manifest: 5 domains, "curriculum": "pack"
    OBJECTIVES.md                   this map
    objectives/                     official PDF and extracted text
    pack/
        __init__.py                 exports MODULES, MISSIONS, lesson_path()
        syllabus.py                 22-module source of truth
        lessons/                    22 in-depth Markdown lessons
        missions/
            base.py                 shared fixture and check helpers
            domain1.py              missions 1–6   (1.0 System Management)
            domain2.py              missions 7–11  (2.0 Services/Users)
            domain3.py              missions 12–15 (3.0 Security)
            domain4.py              missions 16–19 (4.0 Automation)
            domain5.py              missions 20–22 (5.0 Troubleshooting)
```

## Study order

The modules follow the official domain order, but the fastest exam-first route
is:

1. **Foundations:** 1, 7, 8, 9 — files, accounts, processes.
2. **Systems:** 3, 4, 10, 6 — storage, network, services, virtualization.
3. **Security:** 12, 13, 14, 15 — AAA, firewalls, hardening, crypto.
4. **Automation:** 17, 18, 19, 16 — shell, Python, Git, orchestration.
5. **Troubleshooting:** 21, 22, 20 — OS, network/security, performance.
6. **Review:** 2, 5, 11 — devices, backups, containers.

Each mission is verified against real evidence: files, permission bits, JSON
schemas, Git history, TLS chains, or parsed command output. There are no
multiple-choice question banks.
