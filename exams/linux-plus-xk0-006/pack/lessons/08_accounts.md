# Module 8 — Local account management

> **Exam objective:** Linux+ 2.2 — Given a scenario, perform local account
> management in a Linux environment.
> **Study time:** about 100 minutes, including the mission.
> **Mission:** `user_audit.py` — audit a frozen `/etc/passwd`, `/etc/shadow`,
> and `/etc/group` snapshot and emit a safe provisioning plan.

## What the exam expects

You must be able to create, modify, lock, expire, and delete local accounts,
and explain every field in the account files:

- add: `useradd`, `adduser`, `groupadd`,
- modify: `usermod`, `passwd`, `chsh`, `groupmod`,
- delete: `userdel`, `deluser`, `groupdel`,
- lock and expire: `passwd -l`, `usermod -L`, `chage`,
- list and inspect: `getent passwd`, `id`, `groups`, `who`, `w`, `whoami`,
  `last`, `lastlog`,
- profile templates: `/etc/profile`, `/etc/skel`,
- account files: `/etc/passwd`, `/etc/shadow`, `/etc/group`,
- identifiers: UID, GID, EUID, EGID,
- user, system, and service accounts and their UID ranges.

Account management is also a security topic (3.4): weak passwords, shared
accounts, and root logins are findings.

## The account files

### `/etc/passwd`

World-readable, colon-separated, one line per account:

```
alice:x:1001:1001:Alice Example:/home/alice:/bin/bash
│     │ │    │    │             │           └ login shell
│     │ │    │    │             └ home directory
│     │ │    │    └ GECOS/comment
│     │ │    └ primary GID
│     │ └ UID
│     └ password placeholder (x means “see /etc/shadow”)
└ user name
```

### `/etc/shadow`

Root-only, one line per account:

```
alice:$6$...:19000:0:99999:7:::
│     │      │     │ │     │ └ inactive, expire, reserved
│     │      │     │ │     └ warning days
│     │      │     │ └ max days between changes
│     │      │     └ min days between changes
│     │      └ last change (days since 1970-01-01)
│     └ password hash: $6$ = SHA-512; ! or * = locked/no login
└ user name
```

A password field beginning with `!` is locked. `*` is a common placeholder for
accounts that must never log in. An empty field is a serious finding.

### `/etc/group`

```
wheel:x:10:alice,bob
│     │ │  └ supplementary members
│     │ └ GID
│     └ password placeholder
└ group name
```

The **primary** group comes from `/etc/passwd`; groups here add supplementary
membership. `id alice` shows both.

## UID and GID ranges

| Range | Typical use |
|---|---|
| 0 | root |
| 1–999 | system/service accounts (daemons) |
| 1000+ | regular interactive users |

Distributions differ slightly (`SYS_UID_MIN`/`UID_MIN` in `/etc/login.defs`).
The exam expects the idea: service accounts exist to own daemons and files,
not for humans to log in. A service account with `/bin/bash` and a UID below
1000 is a finding.

Identifiers:

- **UID** — the numeric identity of the user.
- **GID** — the primary group identity.
- **EUID** — the effective UID used for permission checks (differs from the
  real UID after `sudo` or a setuid program).
- **EGID** — the effective GID.

```bash
id
id -u
id -g
id -G
sudo id -u          # 0 after sudo
```

## Creating accounts

### `useradd` — low level and scriptable

```bash
sudo useradd -m -s /bin/bash -c "Alice Example" -U alice
sudo useradd -r -s /usr/sbin/nologin -d /var/lib/app svcapp
sudo useradd -u 1500 -g users -G wheel,devs -m -s /bin/bash bob
```

Important options:

| Option | Meaning |
|---|---|
| `-m` | create the home directory from `/etc/skel` |
| `-M` | do not create a home directory |
| `-s` | login shell |
| `-u` | explicit UID |
| `-g` | primary group |
| `-G` | supplementary groups |
| `-d` | home directory path |
| `-c` | comment/GECOS |
| `-r` | system account |
| `-e` | expiry date (`YYYY-MM-DD`) |
| `-U` / `-N` | create / do not create a same-name group |

`useradd` creates the account but does **not** set a password in one step;
use `passwd alice` (or `chpasswd` in automation).

### `adduser` — interactive wrapper

Debian/Ubuntu's `adduser` is friendlier: it prompts for a password, creates the
home directory, and sets sensible defaults.

```bash
sudo adduser alice
sudo adduser --system --group --no-create-home svcapp
```

On RHEL-family systems `adduser` is usually a symlink to `useradd`.

### Groups

```bash
sudo groupadd devs
sudo groupadd -g 1500 ops
sudo groupmod -n developers devs
sudo groupdel oldgroup
```

`groupdel` fails if the group is a user's primary group. Move the user first.

## Modifying accounts

```bash
sudo usermod -aG wheel alice        # append a supplementary group
sudo usermod -s /usr/sbin/nologin svcapp
sudo usermod -L alice               # lock (prefix password with !)
sudo usermod -U alice               # unlock
sudo usermod -e 2026-12-31 alice    # expiry date
sudo usermod -d /srv/alice -m alice # move home
sudo chsh -s /bin/zsh alice
```

**`usermod -aG` versus `usermod -G`:** `-G` replaces the entire supplementary
group list. Forgetting `-a` silently removes the user from every other group.
This is one of the most common production mistakes.

## Passwords, locking, and expiry

```bash
sudo passwd alice
sudo passwd -l alice       # lock
sudo passwd -u alice       # unlock
sudo passwd -e alice       # force change at next login (expire)
sudo passwd -S alice       # status: LK, PS, NP
```

`chage` manages aging:

```bash
sudo chage -l alice
sudo chage -M 90 -m 1 -W 7 alice
sudo chage -d 0 alice          # force change now
sudo chage -E 2026-12-31 alice # account expiry
```

`chage -l` prints last change, password expires, account expires, minimum,
maximum, and warning days. Service accounts should be locked and expired.

## Listing and inspecting

```bash
getent passwd
getent passwd alice
getent group wheel
id alice
groups alice
who
w
whoami
last -n 10
lastlog
```

`getent` follows `nsswitch.conf`, so it also shows LDAP/SSSD users — unlike
`cat /etc/passwd`. Use it in scripts that must work with central identity.

`last` reads `/var/log/wtmp`; `lastlog` shows the last login per account.
`who` and `w` show current sessions; `w` also shows load and idle time.

## User profile templates

When a home directory is created, `useradd -m` copies `/etc/skel`. Put default
dotfiles there:

```bash
ls -la /etc/skel
# .bash_logout .bash_profile .bashrc .profile
```

System-wide startup files:

- `/etc/profile` — login shells, all users.
- `/etc/profile.d/*.sh` — modular additions (umask, aliases, PATH).
- `/etc/bash.bashrc` — interactive shells (Debian).
- `/etc/bashrc` — interactive shells (RHEL).

Order for a bash login shell: `/etc/profile` → `~/.bash_profile` (or
`~/.bash_login`, `~/.profile`). For an interactive non-login shell:
`/etc/bash.bashrc` → `~/.bashrc`.

Do not put secrets in profile files; they are readable and often copied into
images.

## Deleting accounts

```bash
sudo userdel alice          # leaves the home directory
sudo userdel -r alice       # removes home and mail spool
sudo deluser --remove-home alice   # Debian wrapper
```

Before deleting an account, decide what happens to:

- files it owns (`find / -uid <uid>`),
- running processes (`ps -u alice`),
- cron jobs (`/var/spool/cron/`),
- mail, databases, and application data,
- audit requirements (many standards require disabling, not deleting).

The safe pattern is usually: lock → remove from groups → terminate sessions →
archive home → delete or reassign ownership.

## Service accounts

A service account owns a daemon and its files and must not be usable for
interactive login:

```bash
sudo useradd -r -s /usr/sbin/nologin -d /var/lib/myapp -M myapp
sudo chown -R myapp:myapp /var/lib/myapp
```

Use `/usr/sbin/nologin` (or `/bin/false`) as the shell. Check for daemons still
running as root — that is a hardening finding (module 14).

## Mission 08 — what you build

`etc/passwd`, `etc/shadow`, and `etc/group` are a snapshot; `home/` has only
some directories. Your `user_audit.py --root .` must print:

- `duplicate_uids` — `{uid: [users]}` for shared UIDs,
- `interactive_service_accounts` — UIDs below 1000 (except root) with a login
  shell,
- `locked_accounts` — shadow entries whose password starts with `!`,
- `expired_accounts` — accounts where last change + max days is before today,
- `missing_homes` — regular users (UID ≥ 1000) without a home directory,
- `wheel_members` — members of `wheel`,
- `provision_commands` — one `useradd` line per entry in `new_users.txt`:
  `useradd -u UID -g GROUP -m -s SHELL NAME` for a normal shell and
  `... -M ...` for a nologin shell.

This is a dry-run plan; never execute `useradd` from the audit. Run
`python3 main.py verify 8`.

## Exam traps

- `usermod -G` replaces group membership; add `-a`.
- `userdel` without `-r` leaves the home directory behind.
- A locked password (`!`) is not the same as an expired account.
- `getent` sees directory users; `cat /etc/passwd` does not.
- `id` shows the *effective* identity after `sudo`.
- Service accounts should have nologin shells and no password.

## Check yourself

1. Which field of `/etc/shadow` marks an account as locked?
2. How do you add a user to `wheel` without removing their other groups?
3. What does `chage -d 0` do?
4. Which command shows the last login for every account?
5. Why is `/usr/sbin/nologin` preferable to `/bin/bash` for a daemon account?
6. What is the difference between UID and EUID?

## Going deeper

- Create a user, add them to a group, lock them, and inspect every field with
  `getent` and `chage -l`.
- Populate `/etc/skel` with a `.vimrc` and verify it is copied to a new home.
- Compare `useradd` behaviour on Debian and RHEL-family systems.
- Find all files owned by a UID with `find / -uid 1001 -ls`.
