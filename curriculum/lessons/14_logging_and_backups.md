# Module 14 — Logging, tarfile, and retention: a backup tool

## Why this matters for Linux+

Backups are a Linux+ storage objective and a real operational necessity. A
backup script must be boring: timestamped archives, a log of what happened, a
bounded number of copies, and a dry-run so you can review it before it runs
under `cron` or a systemd timer.

This module builds that tool. It combines several earlier skills: argparse,
pathlib, tarfile, logging, timestamps, and retention.

## `print` is not logging

For a one-off script, `print` is fine. For an unattended tool you need:

- timestamps,
- severity levels,
- a destination that is not the terminal,
- the ability to turn verbosity up or down.

The `logging` module gives you all four.

## Logging basics

```python
import logging

logging.basicConfig(
    filename="/var/log/backup.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

logging.info("backup started")
logging.warning("retention removed an archive")
logging.error("could not write archive")
```

Levels, from most to least severe:

```text
CRITICAL > ERROR > WARNING > INFO > DEBUG > NOTSET
```

`level=logging.INFO` means INFO and above are recorded; DEBUG is dropped. Use
DEBUG for detail you want only while troubleshooting.

`basicConfig` is convenient but global. In a reusable module or a tool that may
be imported, create a named logger:

```python
logger = logging.getLogger("linuxplus.backup")
logger.setLevel(logging.INFO)
handler = logging.FileHandler(log_path, encoding="utf-8")
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)
```

If you call the same function twice in one process, avoid duplicate handlers:

```python
for old in list(logger.handlers):
    logger.removeHandler(old)
```

Why `encoding="utf-8"`? Log messages may contain non-ASCII hostnames or paths.
The default encoding depends on the environment.

## `tarfile`

Create a compressed archive:

```python
import tarfile

with tarfile.open(archive, "w:gz") as tar:
    tar.add(path, arcname=relative_path)
```

Modes:

| Mode | Meaning |
|---|---|
| `w` | uncompressed tar |
| `w:gz` | gzip-compressed |
| `w:bz2` | bzip2 |
| `w:xz` | xz |
| `r:gz` | read a gzip archive |

Critical detail: `arcname`. Without it, `tar.add("/srv/data/file")` stores the
**absolute** path (or a `./` prefix depending on the version), and restoring it
can write outside the destination. Always store paths relative to the source:

```python
for path in source.rglob("*"):
    if path.is_file():
        tar.add(path, arcname=str(path.relative_to(source)))
```

Read an archive:

```python
with tarfile.open(archive, "r:gz") as tar:
    print(tar.getnames())
    member = tar.extractfile("a.txt")
    if member:
        print(member.read().decode("utf-8"))
```

### Security warning

Never extract an untrusted archive without checking member paths. A malicious
member named `../../etc/passwd` can escape the destination. In Python 3.12+,
`tarfile` has extraction filters (`filter="data"`). Prefer them. This mission
only creates archives, but the habit matters.

## Timestamps in filenames

```python
from datetime import datetime

name = f"backup-{datetime.now():%Y%m%d-%H%M%S}.tar.gz"
```

Using a sortable format (`YYYYmmdd-HHMMSS`) gives you:

- chronological sorting by name,
- easy retention (“keep the newest N”),
- no spaces or colons that complicate shell scripts.

Local time is fine for human-facing backups. If you need to coordinate across
time zones, use UTC (`datetime.now(timezone.utc)`) and say so.

Two backups in the same second collide. For a human-run tool that is unlikely;
for a loop, add microseconds or use `tempfile`/a counter.

## Retention

Backups grow without bound unless you delete old ones. A simple policy:

```python
archives = sorted(destination.glob("backup-*.tar.gz"), key=lambda p: p.name)
while len(archives) > keep:
    oldest = archives.pop(0)
    oldest.unlink()
```

Why sort by name? Because the timestamp format sorts lexicographically in
chronological order. Why `pop(0)`? Because the oldest is first.

More sophisticated policies (grandfather-father-son, daily/weekly/monthly)
belong in a real backup system. The principle is the same: define the policy,
implement it explicitly, log every deletion.

## Dry-run

```python
if args.dry_run:
    print(f"WOULD ARCHIVE {len(files)} files from {source} to {archive}")
    return 0
```

A dry-run must not create the destination directory, the archive, or the log
file. “Mostly dry” is a bug. Test it by comparing directory listings before and
after.

## Atomicity

A backup that is interrupted mid-write leaves a corrupt archive. A more robust
approach:

1. write to a temporary file in the destination,
2. fsync and close,
3. `os.replace(tmp, final)` (atomic on the same filesystem).

This mission does not require it, but it is the next step for production use.
If a `.tar.gz` exists, a monitoring check may assume it is complete.

## Scheduling: cron vs systemd timers

**cron** entry:

```cron
# m h dom mon dow command
30 2 * * * /usr/local/bin/backup.py /srv /var/backups --keep 7 >> /var/log/backup-cron.log 2>&1
```

**systemd timer** (`backup.service` + `backup.timer`):

```ini
# /etc/systemd/system/backup.service
[Unit]
Description=Nightly backup

[Service]
Type=oneshot
User=backup
ExecStart=/usr/local/bin/backup.py /srv /var/backups --keep 7
```

```ini
# /etc/systemd/system/backup.timer
[Unit]
Description=Run backup nightly

[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and inspect:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now backup.timer
systemctl list-timers --all
journalctl -u backup.service --since today
```

Why systemd timers? They integrate with the journal, dependencies, resource
limits, and missed-run handling (`Persistent=true`). cron is simpler and
ubiquitous. Know both for the exam.

## Exit codes

- 0: backup created and retention applied,
- 1: backup failed (I/O error),
- 2: usage error (missing source, bad `--keep`).

Logging and exit codes serve different audiences: humans read the log, cron and
systemd read the status. Provide both.

## Guided walkthrough

```bash
cd "$(python3 main.py doctor | sed -n 's/^  \[ok\] Lab: //p' | head -1)" 2>/dev/null || true
mkdir -p 14_backup_tool
cd 14_backup_tool
mkdir -p demo-src/sub demo-dest
echo one > demo-src/a.txt
echo two > demo-src/sub/b.txt
```

Experiment with `tarfile`:

```bash
python3 - <<'PY'
import tarfile
with tarfile.open("demo.tar.gz", "w:gz") as tar:
    tar.add("demo-src/a.txt", arcname="a.txt")
    tar.add("demo-src/sub/b.txt", arcname="sub/b.txt")
with tarfile.open("demo.tar.gz", "r:gz") as tar:
    print(tar.getnames())
PY
tar -tzf demo.tar.gz
```

Then implement `backup.py` and exercise it:

```bash
python3 backup.py demo-src demo-dest --dry-run
python3 backup.py demo-src demo-dest --keep 2
ls -l demo-dest
cat demo-dest/backup.log
python3 - <<'PY'
import tarfile, pathlib
archive = sorted(pathlib.Path("demo-dest").glob("backup-*.tar.gz"))[-1]
with tarfile.open(archive) as tar:
    print(tar.getnames())
PY
```

Verify:

```bash
python3 main.py verify 14
```

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| `tar.add(abs_path)` without `arcname` | absolute paths in archive | relative `arcname` |
| No retention | disk fills | keep newest N |
| Deleting before creating | data loss | create, verify, then prune |
| Dry-run creates the log/dir | not actually dry | return before side effects |
| No log file | nothing to investigate | logging.FileHandler |
| Using `datetime.now()` for durations | clock jumps | `perf_counter()` |
| Catching every exception and exiting 0 | silent failure | catch, log, non-zero |
| Trusting an archive without reading it | corrupt backup unnoticed | open and list/test |
| Backup stored on the same disk | no disaster recovery | document the off-host copy |

## Mission checklist

- [ ] `14_backup_tool/backup.py` exists.
- [ ] Creates `backup-YYYYmmdd-HHMMSS.tar.gz` under the destination.
- [ ] Archive members are relative to the source.
- [ ] `--keep N` retains only the newest N archives.
- [ ] Writes INFO lines to the log (archive name, file count).
- [ ] `--dry-run` creates nothing and says `WOULD`.
- [ ] Missing source exits 2 with stderr, no traceback.

Then run:

```bash
python3 main.py verify 14
```

## Extra practice

1. Add a manifest JSON with file sizes and SHA256 hashes.
2. Write to a temporary file and `os.replace` for atomicity.
3. Add `--exclude` patterns and `--compress {gz,xz}`.
4. Verify the archive by reopening it and checking every member.
5. Add `--prune-only` to apply retention without creating a backup.
6. Create the systemd timer in a user unit (`systemctl --user`) and run it.
7. Restore a single file with `tar -xzf archive path/to/file`.
