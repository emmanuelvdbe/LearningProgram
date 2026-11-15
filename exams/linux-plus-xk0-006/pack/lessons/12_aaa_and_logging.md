# Module 12 — AAA, logging, and audit trails

> **Exam objective:** Linux+ 3.1 — Summarize authorization, authentication,
> and accounting methods.
> **Study time:** about 100 minutes, including the mission.
> **Mission:** `aaa_audit.py` — audit PAM, journald, rsyslog, logrotate,
> auditd, and SSSD configuration, then write a hardening audit rule file.

## What the exam expects

**AAA** means:

- **Authentication** — proving who you are (password, key, certificate, MFA).
- **Authorization** — deciding what you may do (groups, sudo, Polkit, SELinux,
  file permissions).
- **Accounting** — recording what you did (journald, rsyslog, auditd, wtmp,
  lastlog).

The technologies named in objective 3.1:

- **PAM** — Pluggable Authentication Modules,
- **Polkit** — fine-grained authorization for privileged D-Bus services,
- **SSSD** / **Winbind** — bridging to LDAP, Kerberos, and Active Directory,
- **LDAP**, **Kerberos**, **Samba**,
- **Logging** — `journalctl`, `rsyslog`, `logrotate`, `/var/log`,
- **System audit** — `auditd` and `audit.rules`.

## PAM

PAM is a stack of shared libraries that every login-capable program calls. The
program (`login`, `sshd`, `sudo`, `su`, `passwd`, `cron`) names a service file
in `/etc/pam.d/`.

```
# /etc/pam.d/sshd
auth       required     pam_env.so
auth       required     pam_faillock.so preauth
auth       substack     password-auth
auth       include      postlogin
account    required     pam_nologin.so
account    include      password-auth
password   include      password-auth
session    required     pam_selinux.so close
session    required     pam_loginuid.so
session    include      password-auth
```

Each line is:

```
type       control      module            arguments
```

- **type:** `auth`, `account`, `password`, `session`.
- **control:** `required`, `requisite`, `sufficient`, `optional`, `include`,
  `substack`, or a bracketed `[success=ok new_authtok_reqd=done ...]`.
- **module:** the `.so` file in `/lib/security/` or `/usr/lib64/security/`.
- **arguments:** module-specific (`deny=5`, `minlen=14`, `nullok`, `try_first_pass`).

### Common modules

| Module | Purpose |
|---|---|
| `pam_unix.so` | classic `/etc/shadow` authentication |
| `pam_faillock.so` | lock after N failures (`deny=`, `unlock_time=`) |
| `pam_tally2.so` | older failure counter (deprecated) |
| `pam_pwquality.so` | password strength (`minlen=`, `dcredit=`, `ucredit=`) |
| `pam_pwhistory.so` | prevent password reuse (`remember=`) |
| `pam_limits.so` | apply `/etc/security/limits.conf` |
| `pam_mkhomedir.so` | create home directories on first login |
| `pam_sss.so` | authentication via SSSD |
| `pam_winbind.so` | authentication via Samba/Winbind |
| `pam_google_authenticator.so` | TOTP multi-factor |
| `pam_access.so` | host/user access rules (`/etc/security/access.conf`) |
| `pam_nologin.so` | block logins when `/etc/nologin` exists |
| `pam_selinux.so` | set the SELinux context on login |

### Stack semantics

- `required` — must succeed; failure is remembered and reported after the
  whole stack runs.
- `requisite` — must succeed immediately; failure stops the stack.
- `sufficient` — success is enough to authenticate (if no earlier `required`
  failed).
- `optional` — failure is ignored unless it is the only module.
- `include` — pull in another stack.
- `substack` — like include, but failures are confined to the substack.

Example password policy:

```
password   requisite    pam_pwquality.so retry=3 minlen=14
password   sufficient   pam_unix.so sha512 shadow nullok use_authtok
password   required     pam_pwhistory.so remember=5
```

`nullok` allows empty passwords — a serious finding. Weak `minlen`, missing
`pam_faillock`, and `pam_tally2` still in use are all issues the mission asks
you to detect.

Check the effective rules instead of guessing:

```bash
grep -v '^#' /etc/pam.d/common-password
authselect current                 # RHEL family
authselect select sssd with-faillock
pam-auth-update                    # Debian family
```

## Polkit

Polkit authorizes privileged actions on the system bus. Rules live in
`/usr/share/polkit-1/rules.d/` (vendor) and `/etc/polkit-1/rules.d/`
(administrator, higher priority). They are JavaScript:

```javascript
polkit.addRule(function(action, subject) {
    if (action.id == "org.freedesktop.systemd1.manage-units" &&
        subject.isInGroup("wheel")) {
        return polkit.Result.YES;
    }
});
```

Inspect with `pkaction`, `pkcheck`, and `journalctl -u polkit`. A permissive
Polkit rule that grants `YES` to all users for `manage-units` is equivalent to
passwordless root for service management.

## SSSD, LDAP, Kerberos, Samba

**SSSD** caches directory and Kerberos credentials and exposes users through
NSS and PAM:

```ini
# /etc/sssd/sssd.conf
[sssd]
domains = corp.example
config_file_version = 2
services = nss, pam

[domain/corp.example]
id_provider = ldap
auth_provider = ldap
ldap_uri = ldaps://dc1.corp.example
ldap_search_base = dc=corp,dc=example
cache_credentials = true
use_fully_qualified_names = True
```

```bash
systemctl status sssd
sss_cache -E
getent passwd alice@corp.example
id alice@corp.example
kinit alice@CORP.EXAMPLE
klist
```

- **LDAP** — directory of users, groups, and attributes. Always use LDAPS
  (636) or StartTLS; plain LDAP exposes credentials.
- **Kerberos** — ticket-based authentication. `kinit` gets a TGT, `klist` shows
  it, and services accept it if their keytab is present.
- **Samba / Winbind** — SMB file sharing and AD integration. `winbind` can
  supply users and groups instead of SSSD.
- **`nsswitch.conf`** decides the lookup order: `passwd: files sss`.

`use_fully_qualified_names`, `ldap_uri` starting with `ldaps://`, and a
working `sss_cache` are the details the mission checks.

## journald

`systemd-journald` collects logs from the kernel, services, and stdout into a
binary journal.

```bash
journalctl                     # all
journalctl -b                  # this boot
journalctl -b -1               # previous boot
journalctl -u sshd             # one unit
journalctl -f                  # follow
journalctl -p err..alert       # priority range
journalctl --since '1 hour ago' --until now
journalctl _UID=1001
journalctl -k                  # kernel only
journalctl --disk-usage
journalctl --vacuum-time=14d
```

Configuration in `/etc/systemd/journald.conf`:

```ini
[Journal]
Storage=persistent
SystemMaxUse=2G
ForwardToSyslog=yes
Compress=yes
```

- `Storage=persistent` keeps logs in `/var/log/journal` across reboots;
  `volatile` keeps them in `/run/log/journal` and loses them on reboot.
- `ForwardToSyslog=yes` sends everything to rsyslog as well, which is required
  if you rely on rsyslog rules or remote forwarding.
- `SystemMaxUse` caps disk usage.

## rsyslog

`rsyslog` routes messages by facility and severity:

```
# /etc/rsyslog.conf
authpriv.*                /var/log/secure
*.info;mail.none;authpriv.none;cron.none   /var/log/messages
*.* @@loghost.example.com:514             # TCP forwarding
*.* @loghost.example.com:514              # UDP forwarding
```

- `authpriv` covers authentication messages; `kern` covers the kernel.
- `@@` is TCP, `@` is UDP. TCP with TLS (`omfwd` with `StreamDriver`) is the
  production choice.
- Remote logging is a security control: an attacker who owns the host cannot
  erase logs held elsewhere.
- Reload with `systemctl restart rsyslog` (or `HUP`) after a change.

```bash
logger -p authpriv.notice "test message"
logger -t myapp "hello"
```

`logger` is how you inject a test line into the local and remote pipeline.

## logrotate

Log files must be rotated, compressed, and deleted on a schedule:

```
# /etc/logrotate.d/app
/var/log/app/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 app app
    sharedscripts
    postrotate
        systemctl reload app >/dev/null 2>&1 || true
    endscript
}
```

Key directives:

| Directive | Effect |
|---|---|
| `daily` / `weekly` / `monthly` | rotation frequency |
| `rotate N` | keep N old files |
| `compress` | gzip old files |
| `delaycompress` | compress one cycle later (for processes still writing) |
| `missingok` | no error if the file is absent |
| `notifempty` | skip empty files |
| `create mode owner group` | recreate the file with correct ownership |
| `copytruncate` | copy then truncate (for apps that cannot reopen) |
| `postrotate` | command to run after rotation |

A missing `compress`, `rotate` below 7, or missing `create` are the issues the
mission detects. Test a config without waiting:

```bash
sudo logrotate -d /etc/logrotate.d/app     # debug, no changes
sudo logrotate -f /etc/logrotate.d/app     # force a rotation
```

`logrotate` is usually driven by a systemd timer (`logrotate.timer`) rather
than cron.

## auditd

`auditd` records security-relevant events at the kernel level. Rules live in
`/etc/audit/rules.d/*.rules` and are compiled into `/etc/audit/audit.rules`.

```
-D
-b 8192
--backlog_wait_time 60000
-w /etc/passwd -p wa -k identity
-w /etc/group -p wa -k identity
-w /etc/shadow -p wa -k identity
-w /etc/sudoers -p wa -k privileged
-w /etc/ssh/sshd_config -p wa -k privileged
-a always,exit -F arch=b64 -S execve -F euid=0 -k root_exec
```

- `-w PATH -p wa -k KEY` watches a file for **w**rite and **a**ttribute
  changes and tags events with `KEY`.
- `-b` sets the backlog buffer; a full buffer drops events (look for “lost” in
  `ausearch`/`aureport`).
- `-D` deletes existing rules; without it, new rules append.

```bash
sudo auditctl -l
sudo augenrules --load
sudo systemctl restart auditd
sudo ausearch -k identity -i
sudo ausearch -m AVC -ts recent
sudo aureport --summary
sudo aureport -au
sudo auditctl -s
```

`auditd` answers “who changed `/etc/shadow`?” and is a compliance requirement
in most benchmarks (CIS, PCI-DSS, STIG). SELinux denials (`AVC`) are also
logged here.

## Accounting and login records

```bash
last          # /var/log/wtmp — successful logins
lastb         # /var/log/btmp — failed logins (root only)
lastlog       # last login per account
who           # current sessions
w             # sessions plus load and idle
ac -p         # per-user connect time
faillock --user alice
```

`faillock` shows the failure counter that `pam_faillock` maintains. Persistent
records are a compliance deliverable: retention, integrity, and off-host
copies.

## Mission 12 — what you build

`etc/` is a snapshot of a server's identity and logging stack.
`aaa_audit.py --root .` must print:

- `pam_modules` — module filenames in `etc/pam.d`, first-seen order,
- `faillock_deny` — `deny=` from `pam_faillock` (or null),
- `password_minlen` — `minlen=` from `pam_pwquality` (or null),
- `nullok_present` — true when `nullok` appears anywhere,
- `tally2_present` — true when `pam_tally2.so` appears,
- `journald_storage` — `Storage=` from `journald.conf`,
- `journald_forward_to_syslog` — true when `ForwardToSyslog=yes`,
- `remote_logging` — true when rsyslog forwards to a remote host,
- `logrotate_issues` — any of `missing compress`, `rotate less than 7`,
  `missing create`,
- `audit_watches` — `{path: permissions}` from `-w` lines,
- `missing_audit_watches` — required watches that are absent
  (`/etc/passwd`, `/etc/group`, `/etc/shadow`, `/etc/sudoers`,
  `/etc/ssh/sshd_config`),
- `sssd_domains`, `sssd_id_provider`, `sssd_ldaps`,
- `recommendations` — concrete fixes.

Also write `audit/99-hardening.rules` with a `-w PATH -p wa -k KEY` watch for
all five files. Run `python3 main.py verify 12`.

## Exam traps

- `required` does not stop the stack; `requisite` does.
- `nullok` means an empty password is accepted.
- `journald` with `Storage=volatile` loses logs on reboot.
- `@` is UDP forwarding, `@@` is TCP.
- `logrotate` without `compress` wastes space; without `create` the service may
  lose write access after rotation.
- `auditctl -l` shows runtime rules; they are lost on reboot unless written to
  `/etc/audit/rules.d/`.
- `-w` does not recurse into a directory by default; watch the directory itself
  or use a syscall rule.
- Plain LDAP sends credentials in clear text.

## Check yourself

1. What is the difference between the `auth`, `account`, `password`, and
   `session` PAM types?
2. Which PAM control flag stops evaluation immediately on failure?
3. Where does `journald` store persistent logs, and which setting enables
   persistence?
4. How do you forward logs to a remote host over TCP, and why prefer TCP over
   UDP?
5. Which `logrotate` directives prevent a service from losing write access?
6. What does `-w /etc/shadow -p wa -k identity` record?
7. Which SSSD setting proves that directory traffic is encrypted?
8. Which command shows failed login attempts per user?

## Going deeper

- Add `pam_faillock` to a test VM and lock yourself out (then recover from a
  console).
- Send logs to a second VM with rsyslog over TLS and confirm the receiver holds
  them after deleting the sender's copy.
- Write an auditd rule for privilege escalation (`execve` with `euid=0`) and
  trigger it with `sudo`.
- Run `logrotate -d` on every file in `/etc/logrotate.d/` and explain each
  directive.
