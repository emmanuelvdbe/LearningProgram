# Module 3 — Storage: LVM, RAID, filesystems, and mounts

> **Exam objective:** Linux+ 1.3 — Given a scenario, manage storage in a Linux
> system.
> **Study time:** about 120 minutes, including the mission.
> **Mission:** `storage_audit.py` — audit LVM, mdadm state, inode usage, and
> mount policy from fixtures.

## What the exam expects

Storage is the largest single objective in Domain 1. You must be able to:

- build and extend LVM stacks: PV → VG → LV,
- create and repair RAID arrays with `mdadm`,
- create, check, and grow ext4, XFS, Btrfs, and tmpfs filesystems,
- explain inodes and why a filesystem can be “full” with free space,
- choose safe mount options in `/etc/fstab`,
- mount local and network filesystems (NFS, SMB),
- read `df`, `du`, `/proc/mounts`, `/etc/fstab`, and `/etc/mtab`.

## Block devices and partitions

Start by seeing what exists:

```bash
lsblk -f                 # tree, filesystem, UUID, mountpoint
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT
blkid                    # UUID and filesystem type for each device
sudo fdisk -l /dev/sda
sudo parted /dev/sda print
```

Partition tools:

| Tool | Notes |
|---|---|
| `fdisk` | MBR and GPT, interactive, classic |
| `gdisk` / `sgdisk` | GPT-specific, scriptable with `sgdisk` |
| `parted` | both tables, can resize, scriptable |
| `growpart` | grow a partition to fill a disk (cloud images) |
| `partprobe` | re-read the partition table without rebooting |

After changing a partition table, the kernel may still use the old one. Run
`partprobe` or reboot. Growing a disk in a VM/cloud is a two-step operation:
grow the partition (`growpart`), then grow the filesystem.

## LVM in practice

LVM inserts a flexible layer between disks and filesystems:

```
physical disk /dev/sdb
  → PV  (pvcreate /dev/sdb)          physical volume
  → VG  (vgcreate data /dev/sdb)     volume group = pool of extents
  → LV  (lvcreate -L 50G -n app data) logical volume
  → filesystem (mkfs.xfs /dev/data/app) → mount
```

### Physical volumes

```bash
sudo pvcreate /dev/sdb /dev/sdc
sudo pvs
sudo pvdisplay
sudo pvscan
sudo pvmove /dev/sdb          # evacuate a PV before removing it
sudo pvremove /dev/sdb
sudo pvresize /dev/sdb        # after growing the underlying disk
```

### Volume groups

```bash
sudo vgcreate data /dev/sdb /dev/sdc
sudo vgs
sudo vgdisplay data
sudo vgextend data /dev/sdd
sudo vgscan
sudo vgexport data            # prepare a VG to move to another host
sudo vgimport data
sudo vgremove data
```

`vgexport`/`vgimport` are how you move a set of disks to another machine
without re-creating the LVM metadata.

### Logical volumes

```bash
sudo lvcreate -L 50G -n app data
sudo lvcreate -l 100%FREE -n logs data
sudo lvs
sudo lvdisplay
sudo lvextend -L +20G /dev/data/app
sudo lvresize -l +100%FREE /dev/data/logs
sudo lvremove /dev/data/old
sudo lvchange -a n /dev/data/app     # deactivate
```

The critical rule: **grow the LV, then grow the filesystem.** Shrinking is
dangerous and not supported by XFS at all.

```bash
# ext4
sudo resize2fs /dev/data/app
# XFS (mounted)
sudo xfs_growfs /mountpoint
# Btrfs
sudo btrfs filesystem resize max /mountpoint
```

## RAID with mdadm

Software RAID is assembled by the kernel from whole disks or partitions.

```bash
sudo mdadm --create /dev/md0 --level=1 --raid-devices=2 /dev/sdb1 /dev/sdc1
cat /proc/mdstat
sudo mdadm --detail /dev/md0
sudo mdadm --manage /dev/md0 --fail /dev/sdb1
sudo mdadm --manage /dev/md0 --remove /dev/sdb1
sudo mdadm --manage /dev/md0 --add /dev/sdd1
```

`/proc/mdstat` is the quick health view. `[U_]` means one member is missing;
`[UU]` means both are up. `(F)` marks a failed member. `mdadm --detail` shows
state, rebuild progress, and UUID.

Persist the array so it assembles at boot:

```bash
sudo mdadm --detail --scan | sudo tee -a /etc/mdadm/mdadm.conf   # Debian
sudo mdadm --detail --scan | sudo tee -a /etc/mdadm.conf         # RHEL
sudo dracut -f
```

RAID levels to recognise: 0 (striping, no redundancy), 1 (mirror), 5/6
(striping with parity), 10 (mirror + stripe). RAID is not a backup.

## Filesystems

### ext4

The default on many Debian/Ubuntu systems. Mature, journaled, supports online
growth and offline shrink.

```bash
sudo mkfs.ext4 -L app /dev/data/app
sudo e2fsck -f /dev/data/app        # unmounted!
sudo resize2fs /dev/data/app
sudo tune2fs -l /dev/data/app
```

### XFS

The default on RHEL-family systems. Journaled, excellent for large files and
parallel I/O, **can only grow**, and repairs with `xfs_repair`.

```bash
sudo mkfs.xfs -L app /dev/data/app
sudo xfs_growfs /mountpoint
sudo xfs_repair /dev/data/app       # unmounted
sudo xfs_info /mountpoint
```

### Btrfs

Copy-on-write, checksums, snapshots, subvolumes, built-in RAID. Useful for
rollback and containers.

```bash
sudo mkfs.btrfs -L data /dev/data/app
sudo btrfs subvolume create /mnt/data/@app
sudo btrfs filesystem usage /mnt
sudo btrfs scrub start /mnt
sudo btrfs filesystem resize max /mnt
```

### tmpfs

RAM-backed, fast, volatile. Perfect for `/tmp`, `/run`, and container scratch
space. Size it explicitly.

```bash
sudo mount -t tmpfs -o size=2G,mode=1777 tmpfs /tmp
```

Everything in tmpfs is lost on unmount or reboot — never put persistent data
there.

## Inodes

An inode stores metadata for a file: type, permissions, owner, timestamps,
size, and pointers to data blocks. The inode table is fixed at `mkfs` time on
ext4. A filesystem with millions of tiny files can exhaust inodes while `df -h`
still shows free space.

```bash
df -h          # blocks
df -i          # inodes
```

Symptom: `No space left on device` while `df -h` says 60% used. Check `df -i`.
Fix by deleting many small files (mail queues, session files, cache
directories) or by rebuilding the filesystem with more inodes.

## Mounting

Temporary mounts:

```bash
sudo mount /dev/data/app /mnt/app
sudo mount -o ro,nosuid,nodev /dev/sdb1 /mnt/readonly
sudo umount /mnt/app
findmnt /mnt/app
cat /proc/mounts
```

Persistent mounts go in `/etc/fstab`:

```
UUID=8f3c...  /          ext4  errors=remount-ro  0 1
UUID=1a2b...  /boot      ext4  defaults          0 2
/dev/data/app /srv/app   xfs   defaults,nosuid   0 2
server:/export /mnt/nfs  nfs4  rw,soft,timeo=30  0 0
//server/share /mnt/smb  cifs  credentials=/root/.smb,uid=1000 0 0
```

Always prefer UUIDs over device names; `/dev/sdb` can become `/dev/sdc` after
a reboot. Check a new entry without rebooting:

```bash
sudo mount -a
sudo findmnt --verify
```

### Mount options that matter for the exam

| Option | Effect |
|---|---|
| `ro` / `rw` | read-only / read-write |
| `noatime` | do not update access time on every read (performance) |
| `nodev` | ignore device nodes on this filesystem |
| `nosuid` | ignore setuid/setgid bits on this filesystem |
| `noexec` | refuse to execute binaries from this mount |
| `nofail` | boot continues if the device is missing (good for data disks) |
| `remount` | change options on an already-mounted filesystem |
| `defaults` | `rw,suid,dev,exec,auto,nouser,async` |

Hardening pattern for a server: `/tmp` and `/var/tmp` get
`nodev,nosuid,noexec`; `/home` gets `nodev,nosuid`; `/boot` is `nodev,nosuid`
(and often `noexec`). `nofail` prevents a missing data disk from dropping the
system into emergency mode.

Remount without unmounting:

```bash
sudo mount -o remount,ro /srv/app
```

`autofs` mounts on demand, which is useful for home directories and NFS. It is
configured with `/etc/auto.master` and map files, not fstab.

## Network mounts

### NFS

```bash
showmount -e server
sudo mount -t nfs4 server:/export/app /mnt/app
# /etc/fstab
server:/export/app  /mnt/app  nfs4  rw,soft,timeo=30,_netdev  0 0
```

`soft` returns an error after a timeout; `hard` retries forever (can hang
processes). `_netdev` tells systemd to wait for the network.

### SMB / Samba / CIFS

```bash
sudo mount -t cifs //server/share /mnt/share \
  -o credentials=/root/.smb,uid=1000,gid=1000,vers=3.1.1
```

Keep credentials in a mode-600 file, not on the command line (visible in
`ps` and shell history).

## Performance and inspection tools

```bash
df -hT                 # filesystems with type
du -xhd1 /var | sort -h
fio --name=rw --rw=randrw --size=256M --filename=/tmp/fio.test
iostat -xz 1           # device latency and queue depth
```

`fio` measures real throughput/IOPS instead of guessing. `iostat` shows
`%util` and await time; high await with low throughput usually means a failing
disk or a saturated array.

## Mission 03 — what you build

`fixtures/` contains `lvs.txt`, `mdstat.txt`, `df_inodes.txt`, and `fstab`.
Your `storage_audit.py --fixtures fixtures` must output:

- `logical_volumes` — `{LV: VG}` from `lvs.txt`,
- `raid_state` — `degraded` if any member is marked `(F)`, otherwise
  `healthy`,
- `faulty_device` — the failed member (for example `sdc1`) or `""`,
- `inode_full` — mountpoints at 95% inodes or more,
- `unsafe_mounts` — sorted mountpoints whose options miss the policy:
  `/boot` and `/tmp` need `nodev,nosuid,noexec`; `/var` and `/home` need
  `nodev,nosuid`.

Parse real output shapes rather than hard-coding. Run
`python3 main.py verify 3`.

## Exam traps

- `df -h` full and “no space left” with free blocks → check `df -i`.
- XFS cannot shrink; do not promise `xfs_growfs` in reverse.
- `resize2fs` and `xfs_growfs` require the LV to be grown first.
- `mount -a` tests fstab but does not validate every option; use
  `findmnt --verify`.
- A missing non-essential disk without `nofail` can block boot.
- `/etc/mtab` is usually a symlink to `/proc/self/mounts` on modern systems.
- mdadm arrays need their configuration persisted or they may not assemble.

## Check yourself

1. Put the LVM commands in order to turn `/dev/sdb` into a mounted 50 GiB
   filesystem.
2. How do you grow an XFS filesystem after enlarging its LV?
3. What does `[U_]` in `/proc/mdstat` mean?
4. Which mount options would you add to `/tmp` on a hardened server?
5. Why can a filesystem report “no space left” with free blocks?
6. What is the difference between `soft` and `hard` NFS mounts?

## Going deeper

- Create a loopback-backed LVM stack in a scratch VM and extend it online.
- Break and rebuild a two-disk RAID1 array in a VM.
- Fill a small ext4 filesystem with empty files until `df -i` reports 100%.
- Compare `noatime` versus `relatime` write traffic with `iostat`.
