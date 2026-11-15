# Module 7 — Files, links, and filesystem metadata

> **Exam objective:** Linux+ 2.1 — Given a scenario, manage files and
> directories on a Linux system.
> **Study time:** about 80 minutes, including the mission.
> **Mission:** `file_audit.sh` — create links, find large files and broken
> symlinks, and classify block and character devices.

## What the exam expects

This objective is the daily vocabulary of a Linux administrator:

- navigation and file operations: `cd`, `pwd`, `ls`, `cp`, `mv`, `rm`,
  `mkdir`, `rmdir`, `touch`,
- inspection: `file`, `stat`, `diff`, `sdiff`, `find`, `locate`, `lsof`,
- links: symbolic and hard,
- device types in `/dev`: block, character, and special character devices.

The exam asks scenario questions (“which command shows…”, “what happens to the
link if…”) rather than trivia. Understand inodes and you can answer most of
them.

## Navigation and basic operations

```bash
pwd
ls -la
ls -lh --time-style=long-iso
cd /var/log
cd ~
cd -
mkdir -p /srv/app/{bin,conf,data}
touch /srv/app/.keep
cp -a /srv/app /backup/app        # preserve mode, owner, timestamps, links
mv old.txt new.txt
rm -i file
rm -rf /tmp/scratch               # no confirmation; be certain
rmdir emptydir                    # only empty directories
```

`cp -a` is the archive form: recursive plus preserve permissions, ownership,
timestamps, and symlinks. `mv` within one filesystem renames the inode; across
filesystems it copies and deletes.

`ls -l` output is worth reading precisely:

```
-rw-r--r-- 1 alice devs 4096 Nov 14 10:00 app.conf
│└┬┘└┬┘└┬┘ │  │    │    │    │           └ name
│ │  │  │  │  │    │    │    └ modification time
│ │  │  │  │  │    │    └ size in bytes
│ │  │  │  │  │    └ group
│ │  │  │  │  └ owner
│ │  │  │  └ hard-link count
│ │  │  └ other permissions
│ │  └ group permissions
│ └ owner permissions
└ file type: - regular, d directory, l symlink, b block, c character,
             p FIFO, s socket
```

## `file`, `stat`, and `diff`

```bash
file app.conf
file /dev/sda
stat app.conf
stat -c '%n %s %i %a %U:%G' app.conf
diff -u old.conf new.conf
sdiff old.conf new.conf
diff -r /srv/app /backup/app
```

`file` identifies content by magic bytes, not by extension. `stat` gives the
inode number, size, permissions in octal, timestamps, and link count. `diff`
compares text; `sdiff` shows a side-by-side view.

## Inodes and hard links

An inode stores everything about a file except its name: type, permissions,
owner, group, size, timestamps, and pointers to data blocks. A directory maps
names to inode numbers.

```bash
ls -li
# 131072 -rw-r--r-- 2 alice devs 12 Nov 14 10:00 config.ini
# 131072 -rw-r--r-- 2 alice devs 12 Nov 14 10:00 config.hard
```

Both names share inode 131072 and the link count is 2. A **hard link** is
another name for the same inode:

```bash
ln existing newname
```

Properties of hard links:

- same inode, same data, same permissions,
- deleting one name does not delete the data until the link count reaches 0,
- cannot cross filesystems,
- cannot normally link to a directory (only root can, and it breaks the tree),
- the link count in `ls -l` counts hard links, not symlinks.

A **symbolic link** is a small file containing a path:

```bash
ln -s releases/v2 data/current
ln -sfn releases/v3 data/current    # replace atomically
readlink data/current
ls -l data/current                  # lrwxrwxrwx ... -> releases/v2
```

Properties of symlinks:

- separate inode with its own permissions (usually 777, ignored on Linux),
- can cross filesystems and point to directories,
- can be relative or absolute,
- a broken symlink still exists (the *target* is missing), so `cat` fails but
  `ls -l` shows the link,
- changing the target is a one-line operation — perfect for releases.

Relative symlinks survive a directory move; absolute symlinks do not. Prefer
relative targets inside an application tree.

## Finding files

### `find`

`find` walks the tree and evaluates expressions:

```bash
find /var -name '*.log'
find /var -type f -size +100M
find /var -type f -mtime +30
find /srv -type l -xtype l            # broken symlinks
find /srv -perm -4000 -type f         # SUID files
find /srv -user alice -ls
find /srv -name '*.tmp' -delete
find /srv -type f -print0 | xargs -0 sha256sum
```

`-xtype l` is the trick for broken symlinks: `-type l` matches all symlinks,
while `-xtype l` matches links whose target is of type “link” in the resolved
sense — i.e. does not resolve to a real file.

### `locate`

`locate` searches a prebuilt database (`/var/lib/mlocate/mlocate.db`):

```bash
sudo updatedb
locate nginx.conf
locate -i readme
```

It is fast but can be stale. `find` is authoritative and slower.

### `lsof`

`lsof` lists open files, including sockets and deleted-but-open files:

```bash
lsof /var/log/app.log
lsof -p 1234
lsof -u alice
lsof +D /srv/app
lsof -i :443
```

A deleted file still held open by a process consumes disk space until the
process closes it — a classic “df is full but du disagrees” incident.

## Devices in `/dev`

Linux exposes hardware as files. The leading character in `ls -l` tells you
the type:

- `b` — **block device**: random access in fixed-size blocks (disks,
  partitions, loop devices, LVM volumes). Examples: `/dev/sda`, `/dev/vda`,
  `/dev/nvme0n1`, `/dev/mapper/data-app`.
- `c` — **character device**: byte-stream access (terminals, serial ports,
  `/dev/null`, `/dev/zero`, `/dev/random`).
- **special character devices**: `/dev/null` (discards), `/dev/zero` (infinite
  zeros), `/dev/random` and `/dev/urandom` (random bytes), `/dev/tty`,
  `/dev/console`.

```bash
ls -l /dev/sda /dev/null /dev/tty1
# brw-rw---- 1 root disk 8, 0 ... /dev/sda
# crw-rw-rw- 1 root root 1, 3 ... /dev/null
# crw--w---- 1 root tty  4, 1 ... /dev/tty1
```

The two numbers are the **major** and **minor** device numbers. The major
selects the driver, the minor selects the instance. `udev` creates and names
these nodes from kernel events.

Device nodes are not portable across systems in the same way files are. Do not
copy `/dev` into a backup; recreate it with `mknod` or let udev do it.

## Putting it together

A safe cleanup job:

```bash
find /var/tmp -xdev -type f -mtime +7 -print0 |
  xargs -0 -r rm -f
```

- `-xdev` stays on one filesystem,
- `-mtime +7` selects files older than seven days,
- `-print0` / `-0` handles odd filenames,
- `-r` avoids running `rm` with no arguments.

## Mission 07 — what you build

Create an executable `file_audit.sh` that, from the mission directory:

1. makes `data/current` a relative symlink to `releases/v2`,
2. makes `data/config.hard` a hard link to
   `data/releases/v2/config.ini`,
3. writes `reports/large.txt` with every regular file under `data/` larger
   than 1 MiB, sorted,
4. writes `reports/devices.txt` with `block /dev/sda` or `char /dev/null`
   lines derived from `devices/ls-l.txt`,
5. writes `reports/broken.txt` with broken symlinks under `links/`.

Use `ln -s`, `ln`, `find`, `-printf`, `read`, parameter expansion
(`${file##*/}`), and `find -xtype l`. Run `python3 main.py verify 7`.

## Exam traps

- A hard link is not a copy; editing one name changes every name.
- A symlink's permissions are not used when accessing the target.
- `rm` on a symlink removes the link, not the target.
- `-type l` is not the same as `-xtype l`.
- `du` and `df` can disagree when a deleted file is still open.
- Device nodes are recreated by udev; they are not normal files.

## Check yourself

1. How many inodes does a file with two hard links have?
2. Can a hard link cross filesystems? Can a symlink?
3. Which `find` expression finds a symlink whose target is missing?
4. What is the difference between a block and a character device? Give one
   example of each.
5. Why does a relative symlink survive moving the whole application directory?
6. Which command shows which process holds a deleted log file open?

## Going deeper

- Create a file, hard-link it, symlink it, then delete the original and observe
  the link count and contents.
- Compare `du -sh` and `df -h` after deleting a large file that a process still
  holds open (module 9 shows how to find the PID).
- Use `find -printf` to build a report of size, mode, and owner.
- Read `man 7 inode` and `man 7 symlink`.
