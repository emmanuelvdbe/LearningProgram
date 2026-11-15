# Module 5 — Shell operations, pipelines, and backups

> **Exam objectives:** Linux+ 1.5 (common shell operations) and 1.6 (backup and
> restore).
> **Study time:** about 120 minutes, including the mission.
> **Mission:** `bin/backup.sh` — a safe, timestamped archive-and-restore script
> with exclusions, a checksum manifest, and a verified restore.

## What the exam expects

You must be able to use the shell as a tool, not just type commands:

- environment variables (`DISPLAY`, `HOME`, `PATH`, `PS1`, `SHELL`, `USER`),
- absolute, relative, `~`, `.`, `..`, and `-` paths,
- shell startup files (`.bashrc`, `.bash_profile`, `.profile`),
- redirection and pipes (`<`, `>`, `>>`, `|`, `2>`, `<<`, `<<<`, `tee`),
- text utilities (`grep`, `sed`, `awk`, `cut`, `sort`, `uniq`, `tr`, `wc`,
  `head`, `tail`, `xargs`, `history`, `alias`, `bc`, `printf`),
- editors (`vi`/`vim`, `nano`),
- archiving (`tar`, `cpio`) and compression (`gzip`, `bzip2`, `xz`, `7-Zip`,
  `zip`/`unzip`),
- copy and imaging tools (`rsync`, `dd`, `ddrescue`),
- compressed-file readers (`zcat`, `zgrep`, `zless`).

Backup questions are scenario questions: choose the right tool, preserve
permissions, verify the restore, and do not destroy the source.

## The shell environment

```bash
printenv                 # all exported variables
echo "$HOME $USER $SHELL $PATH"
env | sort | less
```

Key variables:

| Variable | Meaning |
|---|---|
| `HOME` | the user's home directory |
| `USER` | current user name |
| `SHELL` | login shell path |
| `PATH` | colon-separated command search path |
| `PS1` | primary prompt string |
| `DISPLAY` | X11 display (empty under Wayland-only sessions) |

Set a variable for the current shell:

```bash
GREETING="hello"
echo "$GREETING"
```

Export it so child processes inherit it:

```bash
export GREETING
```

`local` inside a function keeps a variable from leaking to the caller. `set`
lists shell variables and functions; `unset` removes one.

### Shell startup files

For bash:

- **login shell:** `/etc/profile`, then `~/.bash_profile`, `~/.bash_login`,
  or `~/.profile` (first one found).
- **interactive non-login shell:** `/etc/bash.bashrc` (distribution-dependent)
  and `~/.bashrc`.
- **non-interactive shell:** reads neither by default; scripts must source what
  they need.

Put aliases and prompt changes in `~/.bashrc`; put environment variables for
login sessions in `~/.profile` or `~/.bash_profile`. Source a file manually
with `.` or `source`:

```bash
source ~/.bashrc
. ./env.sh
```

`bash -n script.sh` checks syntax without running. `bash -x script.sh` traces
each command. Both are in module 17's mission.

## Paths

```bash
pwd
cd /var/log
cd ~
cd ..
cd -
```

`~` is the current user's home; `~user` is another user's home. `.` is the
current directory and `..` is its parent. `-` returns to the previous
directory.

Security note: the current directory is not in `PATH` by default. To run a
program in it, use `./program`. Putting `.` in `PATH` lets an attacker drop a
malicious `ls` in a directory you visit.

## Redirection and pipes

```bash
command > file          # stdout to file (truncate)
command >> file         # stdout to file (append)
command 2> errors.log   # stderr only
command > out 2>&1      # both to the same file
command &> out          # bash shorthand for both
command < input         # stdin from file
command1 | command2     # stdout of one into stdin of the next
command | tee file      # show output and save it
command <<< "text"      # here-string
```

Here-documents feed a block:

```bash
cat > /etc/motd <<'EOF'
Authorized use only.
All activity is monitored.
EOF
```

Quote the delimiter (`<<'EOF'`) to prevent variable and command expansion —
important when writing configuration that contains `$`.

`tee -a` appends. `2>/dev/null` discards errors; use it deliberately, never to
hide real failures.

## Text utilities in anger

```bash
grep -rni 'error' /var/log
grep -E 'ERROR|WARN' app.log
sed -n '10,20p' file
sed -i 's/old/new/g' file
awk -F: '{print $1, $3}' /etc/passwd
cut -d: -f1 /etc/passwd
sort -t, -k2,2n data.csv
uniq -c sorted.txt
tr '[:upper:]' '[:lower:]' < file
wc -l file
head -n 20 file
tail -f /var/log/syslog
history | grep tar
alias ll='ls -alF'
```

`awk` is a small programming language. `$0` is the whole line, `$1` the first
field, `NF` the field count, and `-F` sets the field separator. `xargs` turns
standard input into arguments:

```bash
find /var/tmp -name '*.tmp' -print0 | xargs -0 rm -f
```

The `-print0`/`-0` pair handles spaces and newlines safely.

## Editors

- **vi/vim** — modal. `i` insert, `Esc` normal, `:w` write, `:q` quit,
  `:wq` write and quit, `dd` delete line, `/pattern` search, `u` undo.
- **nano** — modeless. `Ctrl+O` write, `Ctrl+X` exit, `Ctrl+K` cut line,
  `Ctrl+W` search.

You should be able to edit a file over SSH with either. Know how to quit `vi`
without saving (`:q!`) — it is a rite of passage.

## Archiving with tar

`tar` is the standard Linux archiver. Read the flags as *create/extract/list*,
*file*, *gzip*, *verbose*:

```bash
tar -czf backup.tar.gz dir/         # create gzip archive
tar -xzf backup.tar.gz -C /restore  # extract into a directory
tar -tzf backup.tar.gz              # list contents
tar -czf backup.tar.gz --exclude='*.tmp' --exclude='*/cache/*' dir/
tar -xzf backup.tar.gz --same-owner --numeric-owner
```

Rules that prevent real incidents:

- use `-C` to extract into a specific directory, never into `/` casually,
- archive relative paths (`tar -C /srv -czf ... app`) so restore does not
  overwrite system files,
- preserve ownership and permissions when restoring system data
  (`--numeric-owner`, run as root),
- exclude caches, temporary files, sockets, and database data directories you
  cannot safely snapshot.

`cpio` is older but still used for initramfs and some backup systems:

```bash
find . -print0 | cpio --null -ov --format=newc > archive.cpio
cpio -idv < archive.cpio
```

## Compression

| Tool | Command | Notes |
|---|---|---|
| gzip | `gzip file` / `gunzip file.gz` | fast, ubiquitous |
| bzip2 | `bzip2 file` / `bunzip2 file.bz2` | better ratio, slower |
| xz | `xz file` / `unxz file.xz` | best ratio, slowest |
| zip | `zip -r a.zip dir/` / `unzip a.zip` | cross-platform |
| 7-Zip | `7z a a.7z dir/` / `7z x a.7z` | strong ratio, extra package |

Read compressed logs without expanding them:

```bash
zcat app.log.gz | grep ERROR
zgrep -i error app.log.gz
zless app.log.gz
```

`sleep 5 && echo done` is not compression, but remember `&&` and `||`:

```bash
mkdir -p /backup && tar -czf /backup/app.tar.gz /srv/app
test -d /srv/app || echo "missing source"
```

## rsync

`rsync` copies only differences and can preserve almost everything:

```bash
rsync -av --delete /srv/app/ /backup/app/
rsync -avz -e ssh /srv/app/ backup@host:/backup/app/
rsync -av --dry-run --delete /srv/app/ /backup/app/
```

The trailing slash matters: `/srv/app/` means “contents of app”, while
`/srv/app` means “the directory app”. Always run `--dry-run` before a
`--delete`. `-a` implies recursive, permissions, timestamps, symlinks, and
group/owner (when run as root).

## dd and ddrescue

`dd` copies raw bytes. It is powerful and unforgiving — a swapped `if=` and
`of=` can erase a disk.

```bash
dd if=/dev/zero of=/swapfile bs=1M count=2048 status=progress
dd if=/dev/sda of=/backup/sda.img bs=4M status=progress conv=fsync
dd if=/dev/urandom of=/dev/sdb bs=1M status=progress   # destroy data
```

`ddrescue` is designed for failing disks: it copies what it can, logs progress,
and retries bad areas.

```bash
ddrescue -d -r3 /dev/sdb /backup/sdb.img /backup/sdb.mapfile
```

`status=progress` gives feedback. `conv=fsync` flushes before exit. On a live
system, image a filesystem only if it is unmounted or snapshotted; otherwise
the image may be inconsistent.

## Backup strategy

A backup is only real if you have restored it. A practical 3-2-1 rule:

- **3** copies of the data,
- **2** different media/types,
- **1** off-site (or offline/immutable).

For each job, decide:

1. **What** — configuration (`/etc`), application data, databases (use the
   database's dump tool), home directories. Not `/proc`, `/sys`, `/dev`,
   `/run`, or caches.
2. **How often** — RPO (how much data you can lose) drives the schedule.
3. **Retention** — daily/weekly/monthly, with rotation.
4. **Verification** — checksums, test restores, monitoring of job status.
5. **Security** — encrypt off-site copies; protect credentials; restrict who
   can delete backups (immutability helps against ransomware).

### Restore drill

```bash
mkdir -p /tmp/restore-test
tar -xzf /backup/app-20260101.tar.gz -C /tmp/restore-test
sha256sum -c /backup/manifest.sha256
diff -r /srv/app /tmp/restore-test/app
```

## Mission 05 — what you build

`bin/backup.sh SOURCE DEST` must:

1. start with `#!/usr/bin/env bash` and `set -euo pipefail`,
2. print usage to stderr and exit 2 for the wrong argument count or a SOURCE
   that is not a directory,
3. create DEST and `backup-YYYYmmdd-HHMMSS.tar.gz`,
4. exclude `*.tmp` and anything under `cache/`,
5. write `DEST/manifest.sha256`,
6. extract into `DEST/restore/`,
7. print `archive=`, `files=`, and `sha256=` lines.

Use `src/` as the fixture and `out/` as the destination. Run
`python3 main.py verify 5`.

## Exam traps

- `>` truncates; `>>` appends. Losing a log is usually a `>` mistake.
- `tar -czf archive.tar.gz dir` stores the path as given; use `-C` for
  predictable restores.
- Compression does not encrypt; use GPG or an encrypted filesystem.
- `dd` has no confirmation prompt. Triple-check `of=`.
- A backup job that reports success but has never been restored is a hope, not
  a backup.
- `rsync --delete` with the wrong source/target deletes the target's files.

## Check yourself

1. Which file would you edit to change the prompt for interactive shells?
2. What is the difference between `>` and `>>`, and between `2>` and `2>&1`?
3. How do you list a tarball without extracting it?
4. Why is `rsync -a --delete` dangerous without `--dry-run`?
5. Which tool would you use on a disk that is failing and cannot be read
   cleanly?
6. What does `zcat` do, and why is it safer than `gunzip` for a log you only
   want to read?

## Going deeper

- Write a backup script that rotates seven daily archives and emails a failure.
- Restore a tar archive as a different user and observe ownership errors.
- Compare `rsync -a` and `cp -a` on a tree with symlinks and hard links.
- Use `ddrescue` on a deliberately failing loop device and inspect its mapfile.
