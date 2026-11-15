# Module 1 — Boot, firmware, and the filesystem hierarchy

> **Exam objective:** Linux+ 1.1 — Explain basic Linux concepts.
> **Study time:** about 90 minutes, including the mission.
> **Mission:** `fhs_audit.py` — inspect an unpacked root filesystem and report
> what is present, which distribution family it is, and how it boots.

## What the exam expects

Objective 1.1 is broad on purpose. You must be able to explain, in order:

1. the firmware → bootloader → kernel → initrd → init/systemd chain,
2. where GRUB keeps its configuration and how kernel parameters are passed,
3. what an initrd is for and how it is rebuilt,
4. what PXE is and which services make it work,
5. the purpose of every top-level Filesystem Hierarchy Standard directory,
6. server architectures, distribution families, GUI layers, and licensing.

Those ideas show up again in nearly every later domain: a broken boot is a
troubleshooting question (5.2), an initrd module is a device question (1.2),
and `/etc` versus `/var` matters for hardening and backups.

## The boot chain, step by step

A modern x86_64 server with UEFI behaves like this:

```
power on
  → UEFI firmware (POST, hardware inventory, Secure Boot policy)
  → EFI System Partition: /boot/efi/EFI/<vendor>/grubx64.efi
  → GRUB2 loads its configuration and menu
  → GRUB loads the kernel image and the initrd into RAM
  → kernel decompresses, initialises drivers, mounts the initrd as /
  → initrd finds the real root (LVM, RAID, encrypted, network) and pivots
  → kernel executes /sbin/init → systemd
  → systemd reaches the default target and starts units
```

On older BIOS systems the same path starts with the MBR, then the GRUB boot
image in the gap before the first partition (`/boot/grub2/` or
`/boot/grub/`). The acronyms differ, the stages do not.

### Firmware: BIOS versus UEFI

| | Legacy BIOS | UEFI |
|---|---|---|
| Partition table | MBR (2 TiB limit) | GPT (practically unlimited) |
| Boot code | first 512 bytes + gap | files on a FAT32 EFI System Partition |
| Secure Boot | no | yes — only signed bootloaders/kernels |
| Configuration | setup screens | NVRAM entries, `efibootmgr` |

Secure Boot is part of objective 3.3 as well: it verifies the signature of the
bootloader and kernel so an attacker cannot replace them with a rootkit. Check
it with `mokutil --sb-state` or `bootctl status`.

### GRUB2 configuration

Never edit the generated file directly. The real sources are:

| File | Purpose |
|---|---|
| `/etc/default/grub` | user settings: timeout, default entry, kernel command line |
| `/etc/grub.d/*` | scripts that generate menu entries in numeric order |
| `/boot/grub2/grub.cfg` (RPM) | generated menu on RHEL-family systems |
| `/boot/grub/grub.cfg` (Debian) | generated menu on Debian/Ubuntu |

Regenerate after a change:

```bash
# Debian/Ubuntu
sudo update-grub
# RHEL/Fedora
sudo grub2-mkconfig -o /boot/grub2/grub.cfg
```

Key settings in `/etc/default/grub`:

```bash
GRUB_TIMEOUT=5
GRUB_DEFAULT=0
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"
GRUB_CMDLINE_LINUX="console=ttyS0,115200"
```

`GRUB_CMDLINE_LINUX_DEFAULT` is the command line for normal boots;
`GRUB_CMDLINE_LINUX` applies to every entry, including rescue. Common
parameters you should recognise:

- `root=UUID=...` — which filesystem is the real root,
- `ro` / `rw` — mount root read-only first (fsck needs this) or read-write,
- `init=/bin/bash` — emergency shell without systemd,
- `systemd.unit=rescue.target` — single-user rescue,
- `rd.break` — stop in the initramfs (RHEL password-reset trick),
- `nomodeset` — skip kernel mode setting when the GPU driver fails,
- `quiet`, `splash`, `console=...`.

### The kernel and its parameters

The kernel is a compressed image (`/boot/vmlinuz-<version>`). At boot it reads
parameters from GRUB and exposes them at runtime:

```bash
cat /proc/cmdline
uname -r                 # running kernel version
uname -a                 # kernel, host, architecture, build
ls /boot                 # kernels, initrds, config, System.map
```

Runtime tunables that are not boot parameters live in `/proc/sys` and are set
with `sysctl` (see module 10).

### initrd / initramfs

The initrd is a small, temporary root filesystem loaded with the kernel. It
contains the storage, filesystem, encryption, and network drivers needed to
find and mount the *real* root. Without it, a kernel cannot open an LVM volume,
assemble a RAID array, unlock LUKS, or mount an NFS root.

```bash
lsinitrd /boot/initramfs-$(uname -r).img | head    # RHEL-family
lsinitramfs /boot/initrd.img-$(uname -r) | head    # Debian-family
```

Rebuild tools (objective 1.2):

```bash
sudo dracut -f /boot/initramfs-$(uname -r).img $(uname -r)
sudo mkinitrd -f /boot/initrd.img-$(uname -r) $(uname -r)   # older/SUSE
sudo update-initramfs -u                                   # Debian wrapper
```

If you add a driver or change the root storage stack, rebuild the initrd
*before* rebooting. A missing driver in the initrd is the classic cause of
`Kernel panic - not syncing: VFS: Unable to mount root fs`.

### PXE

Preboot Execution Environment boots a machine over the network. The firmware
gets an address over DHCP, downloads a boot file over TFTP, and that loader
(kernel + initrd, or an iPXE script) starts the installer or a diskless image.

Components:

- **DHCP** with `next-server` and `filename` options (or proxyDHCP),
- **TFTP** serving `pxelinux.0`, GRUB EFI images, kernels, and initrds,
- optional **HTTP/NFS** for the installer tree and kickstart file,
- **UEFI HTTP Boot** as a modern alternative to TFTP.

PXE plus Kickstart/cloud-init is how fleets are installed unattended
(objective 4.1).

## Filesystem Hierarchy Standard (FHS)

The FHS is why a script written on Ubuntu usually works on Rocky Linux. The
top-level directories have precise meanings:

| Path | Contents and purpose |
|---|---|
| `/` | root of the hierarchy; the filesystem mounted here |
| `/bin` | essential user commands; usually a symlink to `/usr/bin` |
| `/boot` | kernel, initrd, GRUB files; often its own partition |
| `/dev` | device nodes managed by udev: disks, terminals, `/dev/null` |
| `/etc` | host-specific configuration; no binaries, no variable data |
| `/home` | user home directories (often a separate filesystem) |
| `/lib` | shared libraries and kernel modules; symlink to `/usr/lib` |
| `/proc` | virtual filesystem exposing kernel and process state |
| `/sbin` | essential system binaries; symlink to `/usr/sbin` |
| `/tmp` | scratch space, world-writable, wiped on reboot (often tmpfs) |
| `/usr` | shareable, read-only user data: binaries, libraries, docs |
| `/var` | variable data: logs, spools, caches, databases, containers |

Also worth knowing: `/run` (runtime state since boot), `/srv` (service data),
`/opt` (add-on software), `/mnt` and `/media` (temporary and removable mounts),
`/sys` (device and driver model).

Why it matters operationally:

- `/var` grows; `/usr` should be read-only. Mounting `/usr` read-only and
  `/var` with `nodev,nosuid` is a hardening technique.
- `/tmp` needs `nodev,nosuid,noexec` on a server.
- Backups normally cover `/etc`, `/var`, `/home`, and application data — not
  `/proc`, `/sys`, `/dev`, or `/run`.
- `noexec` on `/home` stops users running downloaded binaries.

## Server architectures

- **x86** — 32-bit Intel/AMD; legacy only.
- **x86_64 / AMD64** — the dominant server architecture.
- **AArch64** — 64-bit ARM; common in cloud (Graviton, Ampere) and edge.
- **RISC-V** — open instruction set, growing in embedded and research.

Userspace binaries are architecture-specific. `uname -m` reports the running
architecture, `lscpu` gives details (module 2), and package repositories are
built per architecture.

## Distribution families

| Family | Package tooling | Examples |
|---|---|---|
| RPM | `dnf`, `yum`, `rpm`, `.repo` files | RHEL, Rocky, Alma, Fedora, openSUSE/SLES |
| Debian | `apt`, `dpkg`, `/etc/apt/sources.list*` | Debian, Ubuntu, Mint |

The split affects file locations (`/etc/sysconfig` versus `/etc/default`),
service names (`httpd` versus `apache2`), SELinux versus AppArmor defaults, and
which package manager commands you use. Later modules cover both.

## The GUI stack

A Linux desktop is layered:

1. **Display server / compositor** — X Server (`Xorg`) or **Wayland**.
2. **Display manager** — the login screen: GDM, SDDM, LightDM.
3. **Window manager / compositor** — Mutter (GNOME), KWin (KDE), Xfwm, i3.
4. **Desktop environment and applications** — GNOME, KDE Plasma, XFCE.

Servers usually run without a GUI (`multi-user.target`), which reduces attack
surface. `systemctl get-default` shows the selected target.

## Software licensing

- **Open source** — source available and redistributable under an OSI licence
  (MIT, Apache-2.0, BSD).
- **Free software** — the FSF's four freedoms: run, study, share, modify.
- **Copyleft** — derivative works must keep the same licence; the GPL is the
  canonical example. Linking GPL code into a proprietary product has legal
  consequences.
- **Proprietary** — closed source, licensed per seat or per core.

You do not need legal advice for the exam, but you must recognise the terms and
know that licence compliance is part of the software supply chain (3.6).

## Commands to keep at your fingertips

```bash
uname -a                    # kernel, hostname, arch
cat /proc/cmdline           # kernel command line
ls /boot                    # kernels and initrds
grub2-mkconfig --help       # RPM-family regeneration
update-grub --help          # Debian-family regeneration
lsinitrd /boot/initramfs-*.img | less
systemctl get-default
efibootmgr -v               # UEFI boot entries
```

## Mission 01 — what you build

`rootfs/` is an unpacked server image. Your `fhs_audit.py --root rootfs`
must derive, without hard-coding:

- which required FHS directories are **present** and which are **missing**,
- the **distribution family** (`debian` when `/etc/debian_version` exists,
  otherwise `rpm`),
- the newest `/boot/vmlinuz-*` **kernel** version and the newest
  `/boot/initrd.img-*` filename,
- `GRUB_TIMEOUT` as an integer and `GRUB_CMDLINE_LINUX_DEFAULT` without quotes
  from `/etc/default/grub`,
- the architecture from `/etc/arch`.

The mission rewards reading real files with `pathlib`, `glob`, and simple
parsing rather than guessing. Run `python3 main.py verify 1` when ready.

## Exam traps

- `/bin`, `/sbin`, and `/lib` are usually symlinks on modern systems; the FHS
  still expects the names.
- GRUB's generated config is not the file to edit; edit `/etc/default/grub`.
- The initrd is not the root filesystem. It is a temporary bridge to it.
- `quiet` does not mean “no logs”; it only suppresses console messages.
- PXE needs DHCP *and* a file transfer service; DHCP alone is not enough.

## Check yourself

1. Which file do you edit to add `nomodeset` permanently?
2. What is the difference between `GRUB_CMDLINE_LINUX` and
   `GRUB_CMDLINE_LINUX_DEFAULT`?
3. Why can a system with a perfectly good root filesystem still panic with
   “Unable to mount root fs”?
4. Which FHS directories should never be backed up, and why?
5. What does Secure Boot verify, and where is the bootloader stored on a UEFI
   system?
6. Which command regenerates GRUB on RHEL versus Ubuntu?

## Going deeper

- Read `man 7 hier` for the authoritative FHS description.
- Inspect your own `/etc/default/grub` and compare it with `/proc/cmdline`.
- Boot a VM with `rd.break` or `init=/bin/bash` and observe the difference
  between the initramfs and the real root (module 6 shows the VM commands).
- Trace a real boot with `systemd-analyze` and `systemd-analyze blame`.
