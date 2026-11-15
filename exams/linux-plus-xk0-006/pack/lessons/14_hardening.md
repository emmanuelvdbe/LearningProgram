# Module 14 — OS and account hardening

> **Exam objectives:** Linux+ 3.3 (given a scenario, implement OS hardening)
> and 3.4 (given a scenario, implement account hardening).
> **Study time:** about 120 minutes, including the mission.
> **Mission:** `harden.sh` — change real permissions, ACLs, sudoers, SSH
> policy, and umask on a directory tree, then verify every bit.

## What the exam expects

### OS hardening (3.3)

- file permissions and ownership, `umask`, SUID/SGID/sticky bits,
- file attributes (`chattr`, `lsattr`),
- ACLs (`setfacl`, `getfacl`),
- SELinux modes, contexts, booleans, `semanage`, `restorecon`, `ausearch`,
- AppArmor profiles,
- SSH hardening (`sshd_config`, key-only auth, banners),
- restricted shells and `rbash`,
- boot security (Secure Boot, GRUB password, kernel parameter lockdown),
- systemd sandboxing directives,
- least privilege and service accounts.

### Account hardening (3.4)

- password policy (`pam_pwquality`, `pam_faillock`, `chage`),
- lockout and expiry,
- multi-factor authentication (TOTP, hardware keys),
- sudo policy (`/etc/sudoers`, drop-ins, `visudo`),
- privileged groups (`wheel`, `sudo`),
- root login restrictions,
- account auditing and cleanup.

This module is where the security domains meet day-to-day administration.

## Permissions, revisited precisely

`ls -l` shows ten characters: type plus three triads.

```
-rwxr-x---  1 alice devs 4096 ... run.sh
│└┬┘└┬┘└┬┘
│ │  │  └ other: r-x
│ │  └ group: r-x
│ └ owner: rwx
└ type
```

Octal values: `r=4`, `w=2`, `x=1`. `750` means owner `rwx`, group `r-x`, other
none.

```bash
chmod 750 run.sh
chmod u+x,g-w,o-rwx run.sh
chown alice:devs run.sh
chgrp devs run.sh
```

Special bits:

| Bit | Octal | Meaning |
|---|---|---|
| SUID | 4000 | run as the file's owner (`/usr/bin/passwd`) |
| SGID | 2000 | run as the file's group; on a directory, new files inherit the group |
| sticky | 1000 | on a directory, only the owner may delete their files (`/tmp`) |

```bash
chmod 4755 helper        # SUID
chmod 2750 shared        # SGID directory
chmod 1777 shared        # sticky, world-writable
find / -perm -4000 -type f 2>/dev/null    # all SUID files
```

SUID binaries are a privilege-escalation surface. Every SUID root binary should
be justified; a writable SUID binary is a critical finding.

### umask

`umask` removes permission bits from newly created files and directories. A
file starts at 666, a directory at 777, and the umask is subtracted:

| umask | Files | Directories |
|---|---|---|
| 022 | 644 | 755 |
| 027 | 640 | 750 |
| 077 | 600 | 700 |

```bash
umask
umask 027
```

Set it system-wide in `/etc/profile` or `/etc/profile.d/umask.sh`, and for
services with `UMask=` in the unit. `027` is a common server default: group can
read, others get nothing.

## File attributes

`chattr` and `lsattr` set filesystem-level flags beyond permissions:

```bash
sudo chattr +i /etc/passwd       # immutable: cannot modify, delete, or rename
sudo lsattr /etc/passwd
sudo chattr -i /etc/passwd
sudo chattr +a /var/log/app.log  # append-only
```

`+i` and `+a` are strong protections against tampering, but they also block
legitimate updates and package upgrades. Note that some container/overlay
filesystems (and unprivileged environments) refuse these flags with
`Operation not permitted` — the mission deliberately avoids requiring them.

## ACLs

POSIX ACLs grant permissions to users and groups beyond the classic triad:

```bash
setfacl -m u:1001:r app/secrets.env
setfacl -m g:auditors:rx reports/
setfacl -m o::- app/secrets.env
getfacl app/secrets.env
setfacl -x u:1001 app/secrets.env      # remove one entry
setfacl -b app/secrets.env             # remove all ACL entries
```

`getfacl` output includes a `mask:` line, which caps the effective permissions
of named users/groups and the group class. `ls -l` shows a `+` after the mode
when an ACL is present. Default ACLs on a directory (`setfacl -d`) are inherited
by new files.

## SELinux

SELinux is mandatory access control in the kernel. Every process and file has
a **context**: `user:role:type:level`, for example
`system_u:object_r:httpd_sys_content_t:s0`.

Modes:

```bash
getenforce            # Enforcing, Permissive, Disabled
sestatus
sudo setenforce 0     # permissive until reboot
```

Persistent mode is in `/etc/selinux/config` (`SELINUX=enforcing`). Permissive
logs denials without blocking; use it to debug, not as a production setting.

```bash
ls -Z /var/www/html
ps -eZ | grep httpd
sudo restorecon -Rv /var/www/html     # restore default contexts
sudo semanage fcontext -a -t httpd_sys_content_t '/srv/web(/.*)?'
sudo semanage fcontext -l | grep srv/web
sudo semanage boolean -l | grep httpd
sudo setsebool -P httpd_can_network_connect on
sudo ausearch -m AVC -ts recent
sudo ausearch -m AVC -ts recent | audit2why
sudo grep AVC /var/log/audit/audit.log
```

A typical denial looks like:

```
type=AVC msg=audit(...): avc: denied { read } for pid=1234 comm="nginx"
  name="index.html" dev="sda1" ino=... scontext=system_u:system_r:httpd_t:s0
  tcontext=unconfined_u:object_r:user_home_t:s0 tclass=file permissive=0
```

Read it as: process type `httpd_t` tried to `read` a file of type
`user_home_t`. The fix is usually to relabel the file (`restorecon`, correct
`semanage fcontext`) or enable a boolean — not to disable SELinux.

AppArmor is path-based instead of label-based. Profiles live in
`/etc/apparmor.d/`; `aa-status` shows loaded profiles, `aa-complain` sets one to
complain mode.

## SSH hardening

`/etc/ssh/sshd_config` and drop-ins in `/etc/ssh/sshd_config.d/`:

```
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
X11Forwarding no
MaxAuthTries 3
AllowGroups wheel
ClientAliveInterval 300
ClientAliveCountMax 2
Banner /etc/issue.net
Protocol 2
```

- **key-only auth** removes password guessing from the threat model,
- **no root login** forces accountability through named accounts and sudo,
- **`AllowGroups wheel`** restricts SSH to an explicit group,
- **`MaxAuthTries`** slows brute force,
- **banner** provides the legal warning required by many policies.

Validate before restarting — a broken `sshd_config` can lock you out:

```bash
sudo sshd -t
sudo systemctl reload sshd
```

Keep an existing session open while testing a new configuration.

Client-side hygiene: protect private keys (`600`), use a passphrase, prefer
Ed25519, and use `ssh-agent` rather than copying keys around.

## Boot and kernel hardening

- Enable **Secure Boot** so only signed bootloaders and kernels run.
- Set a **GRUB password** so an attacker cannot edit kernel parameters at the
  console (`grub2-setpassword`).
- Restrict console access and physical ports.
- Lock down kernel tunables in `/etc/sysctl.d/`:

```
kernel.dmesg_restrict = 1
kernel.kptr_restrict = 2
kernel.sysrq = 0
net.ipv4.conf.all.rp_filter = 1
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
```

Apply with `sysctl --system` and verify with `sysctl -a`.

## sudo

`sudo` is the accountability mechanism: named users perform privileged actions
without sharing root's password.

```
# /etc/sudoers
Defaults use_pty
Defaults logfile="/var/log/sudo.log"
%wheel ALL=(ALL) ALL
%devs  ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart app
```

- `%wheel ALL=(ALL) ALL` — full sudo for the wheel group, password required.
- `NOPASSWD` removes the password prompt. It is acceptable for a narrow,
  fixed command in automation, and a finding for `ALL`.
- `use_pty` forces a pseudo-terminal, which prevents some session-hijack
  tricks.
- Always edit with `visudo` (or a drop-in in `/etc/sudoers.d/`) — it validates
  syntax before saving.
- Files in `/etc/sudoers.d/` should be mode `440` and owned by root.
- `Defaults logfile=` records every sudo command; centralize those logs.

```bash
sudo visudo -c
sudo -l
sudo -l -U alice
```

Prefer drop-ins (`/etc/sudoers.d/90-hardening`) over editing the main file, so
package updates do not conflict.

## Password policy

```
# /etc/security/pwquality.conf
minlen = 14
dcredit = -1
ucredit = -1
lcredit = -1
ocredit = -1
maxrepeat = 3
```

Plus `pam_faillock` (module 12) and `chage` aging:

```bash
sudo chage -M 90 -m 1 -W 7 alice
sudo chage -l alice
```

Multi-factor authentication:

- **TOTP** with `pam_google_authenticator` or `libpam-google-authenticator`,
- **hardware keys** (FIDO2/WebAuthn) via `pam_u2f`,
- **smartcards** via PIV/CAC and `pam_pkcs11`,
- **push** via a commercial identity provider.

MFA matters most for SSH, sudo, and administrative consoles. It does not help
if the account is shared — accountability requires unique identities.

## Restricted shells

`rbash` (restricted bash) blocks `cd`, changes to `PATH`, redirection, and
running commands with `/` in the name. It is useful for a jump account but is
not a security boundary on its own:

```bash
sudo chsh -s /bin/rbash backup
```

Stronger isolation comes from containers, `nsjail`, `bubblewrap`, or a dedicated
appliance account with no shell at all (`/usr/sbin/nologin`).

## Auditing hardening

A repeatable review:

```bash
# permissions and special bits
find / -xdev -perm -4000 -type f -ls
find / -xdev -perm -0002 -type f -ls          # world-writable files
find / -xdev -type d -perm -0002 ! -perm -1000 -ls  # world-writable dirs without sticky

# accounts
awk -F: '$3 == 0 {print}' /etc/passwd         # UID 0 accounts
awk -F: '$3 < 1000 && $7 !~ /(nologin|false)$/ {print}' /etc/passwd
getent group wheel sudo

# sudo and ssh
sudo visudo -c
sudo sshd -t
grep -R NOPASSWD /etc/sudoers /etc/sudoers.d/
grep -R 'PermitRootLogin' /etc/ssh/sshd_config /etc/ssh/sshd_config.d/

# SELinux
getenforce
sudo ausearch -m AVC -ts today
```

This is essentially what the mission's `harden.sh` fixes, in reverse.

## Mission 14 — what you build

Write an executable `harden.sh` that:

1. sets `app/secrets.env` to mode 640 and adds a read-only ACL for UID 1001
   (`setfacl -m u:1001:r app/secrets.env`),
2. sets `app/bin/run.sh` to mode 750 and removes the SUID bit from
   `bin/helper`,
3. makes `shared/` sticky and world-writable (1777) and `shared/notes.txt`
   mode 664,
4. rewrites `etc/sudoers.d/ops` without `NOPASSWD`, mode 440, and creates
   `etc/sudoers.d/90-hardening` mode 440 containing `Defaults use_pty`,
   `Defaults logfile="/var/log/sudo.log"`, and `%wheel ALL=(ALL) ALL`,
5. creates `etc/ssh/sshd_config.d/99-hardening.conf` (mode 644) with
   `PermitRootLogin no`, `PasswordAuthentication no`,
   `KbdInteractiveAuthentication no`, `X11Forwarding no`, `MaxAuthTries 3`,
   `AllowGroups wheel`,
6. creates `etc/profile.d/umask.sh` containing `umask 027`.

Start with `#!/usr/bin/env bash` and `set -euo pipefail`. Run
`python3 main.py verify 14`.

## Exam traps

- `chmod 777` is not “make it work”; it is a finding.
- SUID on a writable file is privilege escalation.
- `setfacl` is masked by the ACL `mask:` entry.
- `chattr +i` blocks package upgrades and must be removed deliberately.
- `setenforce 0` is temporary; the config file controls boot.
- `restorecon` fixes labels; `semanage fcontext` defines them.
- A `sshd_config` mistake can lock you out — always test with `sshd -t`.
- `NOPASSWD: ALL` is passwordless root.
- `umask 027` gives group read; `077` gives nothing to group or others.
- MFA on a shared account does not restore accountability.

## Check yourself

1. What are the octal values for SUID, SGID, and sticky?
2. What does `umask 027` produce for a new file and a new directory?
3. How do POSIX ACLs differ from traditional permissions?
4. What are the three SELinux modes, and which one only logs?
5. Which command relabels a directory to its default context?
6. Why is key-only SSH authentication stronger than a strong password?
7. Which sudo directive forces a pseudo-terminal, and why?
8. Which two files decide local password quality and lockout?

## Going deeper

- Harden a test VM against a CIS benchmark and record every change.
- Write an SELinux policy module with `audit2allow -M` for a custom service.
- Configure TOTP for SSH and test recovery codes.
- Audit every SUID binary on your system and justify or remove each one.
