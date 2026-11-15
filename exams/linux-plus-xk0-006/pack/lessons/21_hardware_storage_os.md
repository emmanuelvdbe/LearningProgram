# Module 21 — Hardware, storage, and OS triage

> **Exam objective:** Linux+ 5.2 — Given a scenario, analyze and troubleshoot
> hardware, storage, and Linux OS issues.
> **Study time:** about 110 minutes, including the mission.
> **Mission:** `os_triage.py` — turn a bundle of dmesg, df, free, systemctl,
> SMART, dpkg, and GRUB evidence into prioritized findings plus a runbook.

## What the exam expects

Recognize the symptom, name the confirming command, and state the fix, for:

| Area | Symptoms |
|---|---|
| Kernel / boot | kernel panic, `VFS: Unable to mount root fs`, initrd problems |
| Storage | filesystem corruption, I/O errors, filesystem full, inode exhaustion, partition not writable |
| Memory | OOM kill, swapping, memory leak |
| Services | failed systemd unit, restart loop |
| Hardware | SMART failure, degraded RAID, overheating |
| Packages | dependency failure, `dpkg`/`rpm` lock, broken upgrade |
| Bootloader | GRUB misconfiguration, missing entry, bad `root=` |
| Security | segfault, unauthorized process, SELinux denial (module 22) |

The method is always the same: **evidence → hypothesis → confirmation →
remediation → prevention**. Never restart first and investigate later.

## A triage method

1. **Scope** — one host or many? Since when? What changed?
2. **Collect** — `dmesg`, journal, `df`, `free`, `systemctl --failed`,
   `smartctl`, package state, boot config.
3. **Classify severity** — data loss or outage = critical; degrading = high;
   cosmetic = low.
4. **Confirm** the cause with a second source.
5. **Fix** the smallest change that restores service.
6. **Record** the evidence and the fix in a runbook.
7. **Prevent** — monitoring, limits, automation, tests.

The mission's output is exactly this structure: `findings` with `severity`,
`area`, `symptom`, `evidence`, and `action`, sorted critical first.

## Kernel panic

A panic means the kernel cannot continue. Common causes:

- `VFS: Unable to mount root fs on unknown-block(0,0)` — wrong `root=` UUID,
  missing storage driver in the initrd, or an unassembled LVM/RAID/LUKS stack,
- a buggy module or driver,
- corrupted filesystem mounted as root,
- hardware failure (bad RAM, failing disk).

```bash
dmesg -T | tail -100
journalctl -k -b -1            # previous boot's kernel log
cat /proc/cmdline
lsinitrd /boot/initramfs-$(uname -r).img | grep -E 'lvm|raid|dm-'
blkid                          # confirm UUIDs
```

Remediation:

- boot an older kernel from the GRUB menu,
- boot rescue/installer media and `chroot` into the system,
- fix `/etc/default/grub` or `/etc/fstab` UUIDs, then regenerate GRUB and the
  initrd,
- rebuild the initrd with the missing driver (`dracut --add-drivers`),
- test RAM with `memtest86+` if panics are random.

`requires_reboot` is true when a panic or corruption is found: the running
kernel state is not trustworthy.

## Filesystem corruption and I/O errors

```
EXT4-fs error (device sda1): ext4_lookup: deleted inode referenced: 1042
blk_update_request: I/O error, dev sdb, sector 12345 op 0x0:(READ)
```

- `EXT4-fs error` / `XFS ... corruption` — metadata inconsistency. Unmount and
  run `fsck -f` (ext) or `xfs_repair` (XFS). Never fsck a mounted read-write
  filesystem.
- `I/O error` on a device — the disk or cable is failing. Check
  `smartctl -a /dev/sdb`, replace the disk, restore from backup or rebuild the
  array.
- A read-only remount after an error is a safety measure
  (`errors=remount-ro`); fix the filesystem before remounting read-write.

```bash
sudo umount /dev/sdb1
sudo fsck -f /dev/sdb1
sudo xfs_repair /dev/sdb1
sudo smartctl -a /dev/sdb
sudo smartctl -t short /dev/sdb
cat /proc/mdstat
```

## Filesystem full and inode exhaustion

Two different “no space left on device” conditions:

```bash
df -h        # blocks
df -i        # inodes
```

- **Blocks full** — data or logs consumed the space. Find the consumers with
  `du -xhd1 /`, `du -xhd1 /var | sort -h`, and `lsof +L1` for deleted-but-open
  files.
- **Inodes full** — millions of tiny files (mail queue, sessions, cache,
  container layers). `df -h` looks fine; `df -i` is at 100%.

Remediation:

- rotate and compress logs (module 12),
- delete stale files and caches,
- truncate a runaway log (`: > /var/log/app.log`) rather than deleting an open
  file,
- extend the LV and grow the filesystem (module 3),
- for inode exhaustion, remove the small-file source or rebuild with more
  inodes.

## Memory pressure and OOM

```
Out of memory: Killed process 4242 (java) total-vm:8291440kB, anon-rss:6100000kB
```

```bash
free -h
cat /proc/meminfo | grep -E 'MemTotal|MemAvailable|Swap'
vmstat 1 5
ps -eo pid,rss,%mem,cmd --sort=-rss | head
sudo journalctl -k | grep -i 'out of memory'
systemd-cgtop
```

`MemAvailable` under ~5% of total is memory pressure. Sustained `si`/`so` in
`vmstat` is swapping. The OOM killer chooses by `oom_score`, which is heavily
influenced by memory use.

Fixes:

- find the leak (`pidstat -r`, heap profiling, restart cadence),
- cap the service (`MemoryMax=` in systemd, container memory limits),
- add swap for burst absorption (not as a substitute for RAM),
- add RAM or scale horizontally,
- protect critical services with `OOMScoreAdjust=-1000` (use sparingly).

## Failed systemd units

```bash
systemctl --failed
systemctl status app.service
journalctl -u app.service -b --no-pager
systemctl cat app.service
systemd-analyze verify /etc/systemd/system/app.service
```

Common causes: wrong `ExecStart` path, missing `User=`, permission denied on a
file, a dependency that did not start, a port already in use, or a config
syntax error in the application itself.

Fixes: correct the unit or app config, add `Restart=on-failure` and
`RestartSec=`, fix ordering with `After=`/`Requires=`, then
`systemctl daemon-reload && systemctl restart app`.

## SMART and hardware health

```bash
sudo smartctl -a /dev/sdb
sudo smartctl -H /dev/sdb
sudo smartctl -t long /dev/sdb
```

Attributes that matter:

| ID | Attribute | Meaning |
|---|---|---|
| 5 | Reallocated_Sector_Ct | sectors remapped; rising is bad |
| 187 | Reported_Uncorrect | uncorrectable errors |
| 188 | Command_Timeout | disk not responding in time |
| 197 | Current_Pending_Sector | sectors waiting for reallocation |
| 198 | Offline_Uncorrectable | bad sectors found offline |
| 199 | UDMA_CRC_Error_Count | cable/controller errors |

`FAILING_NOW` in the `WHEN_FAILED` column is an immediate replacement. A
`PASSED` overall result with a rising reallocated count is a warning, not a
clean bill.

RAID:

```bash
cat /proc/mdstat
sudo mdadm --detail /dev/md0
```

A degraded array (`[U_]`) must be repaired before the second disk fails.

## Package dependency failures

```
dpkg: error processing package app-server:amd64 (--configure):
 dependency problems - leaving unconfigured
```

```bash
sudo dpkg --configure -a
sudo apt --fix-broken install
sudo dnf check
sudo dnf distro-sync
sudo rpm -Va
sudo dnf history
```

Common causes: an interrupted upgrade, a held/pinned package, a third-party
repository with a conflicting version, or a missing dependency. Fix the
dependency or remove the conflicting package; do not force-install over a
broken state without understanding it.

## GRUB misconfiguration

Symptoms: the system drops to `grub>` or `grub rescue>`, boots the wrong
kernel, or panics because `root=` is wrong.

```bash
cat /boot/grub2/grub.cfg          # RHEL family
cat /boot/grub/grub.cfg           # Debian family
grep -E 'GRUB_DEFAULT|GRUB_TIMEOUT|GRUB_CMDLINE' /etc/default/grub
sudo grub-script-check /boot/grub/grub.cfg
sudo grub2-mkconfig -o /boot/grub2/grub.cfg
sudo update-grub
```

Check:

- `GRUB_DEFAULT` is a valid index or saved entry; an index beyond the number
  of `menuentry` blocks selects nothing,
- every `linux` line has a valid `root=` (UUID or device) or relies on the
  generated one,
- the kernel and initrd files named in the entry exist in `/boot`,
- the GRUB environment (`grubenv`) is consistent.

Recovery: at the GRUB prompt, set `root=` and `linux`/`initrd` manually, boot,
then regenerate the configuration. Keep a rescue kernel and a live USB.

## Partition not writable

- The filesystem is mounted read-only (error recovery or `ro` option):
  `findmnt /mountpoint`, `mount -o remount,rw`.
- The disk is full or inodes are exhausted: `df -h`, `df -i`.
- SELinux/AppArmor denies the write: `ausearch -m AVC -ts recent`.
- The underlying device is read-only or failed: `blockdev --getro /dev/sdb`,
  `dmesg`.
- Permissions/ACLs: `ls -ld`, `getfacl`.

## Building the runbook

A runbook is the durable output of an incident. For each area it should say:

1. **Symptom** — what the operator sees.
2. **Confirm** — the exact commands and what to look for.
3. **Fix** — the safe remediation steps.
4. **Verify** — how to prove it is fixed.
5. **Prevent** — the monitoring or configuration change that stops a repeat.

The mission's `runbook.md` is a compact version of this, naming the real
commands: `dmesg`, `journalctl`, `smartctl`, `fsck`, `grub-script-check`,
`dpkg --configure -a`.

## Mission 21 — what you build

`fixtures/` contains dmesg, df, df -i, free, systemctl, SMART, dpkg, and GRUB
evidence from one broken server. `os_triage.py --root .` must print:

- `findings` — ordered list of `{severity, area, symptom, evidence, action}`,
- `critical_count`,
- `requires_reboot` — true when the kernel panicked or corruption was found,
- `filesystems_full` — mounts at 95% or more,
- `inodes_full` — mounts at 95% inodes or more,
- `memory_pressure` — true when `MemAvailable` is under 5% of total,
- `swap_total_kib`,
- `failed_units`,
- `smart_failures` — devices reporting `FAILING_NOW`,
- `package_issues` — true when dpkg reports dependency problems,
- `grub_issues` — detected default-entry and `root=` problems,
- `recommendations` — prioritized remediation steps.

Recognize at minimum: kernel panic, filesystem corruption, OOM kill,
block-device I/O error, filesystem full, inode exhaustion, failed systemd unit,
SMART failure, package dependency failure, and GRUB misconfiguration. Sort
critical findings before high findings.

Also write `runbook.md` explaining how to confirm and fix each area with the
real commands. Run `python3 main.py verify 21`.

## Exam traps

- Restarting before collecting evidence destroys the logs you need.
- `df -h` full is not the same as `df -i` full.
- `fsck` on a mounted read-write filesystem can make corruption worse.
- A `PASSED` SMART summary can still hide a failing disk; read the attributes.
- `systemctl restart` on a failed unit does not fix a bad `ExecStart`.
- A wrong `root=` UUID looks identical to a missing initrd driver.
- `dpkg --configure -a` is the first step for a broken Debian package state,
  not a reinstall.
- A read-only remount is a symptom of an I/O error, not the cause.
- A reboot clears volatile evidence; capture it first.

## Check yourself

1. Which log shows what happened during the *previous* boot?
2. What are the two ways a filesystem can report “no space left”?
3. Which SMART attributes indicate an imminent disk failure?
4. How do you confirm that a systemd unit failed and why?
5. What is the difference between `grub-script-check` and `update-grub`?
6. Which command repairs a broken dpkg dependency state?
7. Why is `fsck` unsafe on a mounted filesystem?
8. What makes an incident “requires reboot”?

## Going deeper

- Boot a VM with a deliberately wrong `root=` and recover from the GRUB prompt.
- Fill a small filesystem with empty files until inodes are exhausted, then
  repair it.
- Break a unit's `ExecStart` and practise the full triage loop.
- Read a real `smartctl -a` report and explain every failing attribute.
