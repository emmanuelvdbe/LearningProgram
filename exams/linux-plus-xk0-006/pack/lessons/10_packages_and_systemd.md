# Module 10 — Software packages and systemd services

> **Exam objectives:** Linux+ 2.4 (given a scenario, manage software
> configurations) and 2.5 (given a scenario, manage and configure systemd
> services).
> **Study time:** about 110 minutes, including the mission.
> **Mission:** `pkg_audit.py` — audit dpkg package state, repository trust,
> failed units, and service hardening.

## What the exam expects

### Packages

- RPM family: `rpm`, `dnf`, `yum`, repository files in `/etc/yum.repos.d/`,
  `dnf config-manager`, GPG key import, `dnf history`.
- Debian family: `dpkg`, `apt`, `/etc/apt/sources.list` and
  `sources.list.d/`, `apt-key` (deprecated) → signed-by keyrings,
  `apt-mark`.
- Language package managers: `pip`, `npm`, `cargo`, `gem`, `composer`.
- Third-party repositories, pinning/hold, dependency resolution,
  `alternatives`, `update-alternatives`.
- Configuration files: `.conf`, `.ini`, `.yaml`/`.yml`, `.json`, `.xml`, `.env`.

### systemd

- unit types: `.service`, `.socket`, `.timer`, `.target`, `.mount`,
  `.automount`, `.path`, `.slice`, `.scope`,
- unit file sections: `[Unit]`, `[Service]`, `[Install]`,
- `systemctl` verbs: `start`, `stop`, `restart`, `reload`, `enable`,
  `disable`, `mask`, `status`, `is-active`, `list-units`, `list-unit-files`,
  `daemon-reload`, `cat`, `edit`,
- targets and the default target,
- timers and `OnCalendar=`,
- journald integration (`journalctl -u`),
- resource limits and sandboxing directives.

## Package management, both families

### Debian family

```bash
sudo apt update                 # refresh package lists
sudo apt upgrade                # upgrade installed packages
sudo apt full-upgrade           # allow removals for dependency changes
sudo apt install nginx
sudo apt remove nginx           # keep config files
sudo apt purge nginx            # remove config too
sudo apt autoremove             # remove unused dependencies
apt list --installed
apt-cache policy nginx
apt-cache show nginx
dpkg -l
dpkg -L nginx                   # files owned by a package
dpkg -S /usr/sbin/nginx         # which package owns a file
dpkg -s nginx                   # status
sudo dpkg -i ./package.deb
sudo apt -f install             # fix dependencies after dpkg -i
```

`apt-mark hold nginx` pins a package; `apt-mark unhold` releases it. Pinning
with `/etc/apt/preferences.d/` controls which repository wins when several
provide the same package.

### RPM family

```bash
sudo dnf check-update
sudo dnf upgrade
sudo dnf install nginx
sudo dnf remove nginx
dnf list installed
dnf info nginx
dnf provides /usr/sbin/nginx
rpm -qa
rpm -ql nginx
rpm -qf /usr/sbin/nginx
sudo rpm -ivh ./package.rpm
sudo dnf install ./package.rpm   # resolves dependencies
sudo dnf history
sudo dnf history undo 12
```

A repository file:

```ini
[app]
name=Internal App Repository
baseurl=https://repo.internal.example/app/$basearch
enabled=1
gpgcheck=1
gpgkey=https://repo.internal.example/keys/app.asc
repo_gpgcheck=1
```

`gpgcheck=1` verifies package signatures against the imported key. `https` plus
a pinning key is the minimum for a third-party repository; a plain `http`
`baseurl` with `gpgcheck=0` is a supply-chain hole.

### Signature verification

```bash
sudo rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-...
rpm -qp --qf '%{SIGPGP:pgpsig}\n' package.rpm
apt-key list                    # legacy trust store
ls /etc/apt/trusted.gpg.d/      # modern keyrings
```

Modern `apt` sources use `signed-by=`:

```
deb [signed-by=/etc/apt/keyrings/app.gpg] https://repo.example/app stable main
```

## Language package managers

```bash
python3 -m venv --without-pip .venv
pip install -r requirements.txt
pip freeze > requirements.txt
npm install
npm ci
cargo build --release
gem install bundler
```

Rules that matter in production:

- pin exact versions (`PyYAML==6.0.2`), never `latest`,
- use lock files (`package-lock.json`, `Cargo.lock`, `poetry.lock`),
- install into an isolated environment, not the system interpreter,
- verify checksums or signatures where the ecosystem supports it,
- scan dependencies for known CVEs (module 15).

## `alternatives`

Several programs can satisfy one command. `update-alternatives` manages the
symlinks:

```bash
update-alternatives --display java
sudo update-alternatives --config java
sudo update-alternatives --install /usr/bin/editor editor /usr/bin/vim 50
```

On RHEL family the same idea exists as `alternatives`.

## Configuration file formats

| Format | Example | Parser |
|---|---|---|
| INI | `key=value`, `[section]` | `configparser` |
| YAML | indentation, `-` lists | `PyYAML`, `yq` |
| JSON | braces, quotes | `json`, `jq` |
| XML | tags and attributes | `ElementTree`, `xmllint` |
| ENV | `KEY=value` lines | `dotenv`, shell `source` |
| Key-value | `sshd_config` style | `sshd -T`, custom parser |

Validate before reloading: `nginx -t`, `sshd -t`, `named-checkconf`,
`apachectl configtest`, `visudo -c`, `yamllint`, `jq empty file.json`,
`xmllint --noout file.xml`.

## unit types and where they live

| Path | Meaning |
|---|---|
| `/usr/lib/systemd/system/` | units shipped by packages |
| `/etc/systemd/system/` | administrator overrides and custom units (highest priority) |
| `/run/systemd/system/` | runtime units |
| `/usr/lib/systemd/user/` | per-user units |

Never edit a unit in `/usr/lib`; it is replaced on upgrade. Use
`systemctl edit` (drop-in in `/etc/systemd/system/<unit>.d/override.conf`) or
copy the unit and edit the copy.

## Anatomy of a service unit

```ini
[Unit]
Description=Example application
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=app
Group=app
WorkingDirectory=/srv/app
EnvironmentFile=/etc/app/app.env
ExecStart=/srv/app/venv/bin/python /srv/app/server.py
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5
LimitNOFILE=8192
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Key directives:

- **`Type=`** — `simple` (default), `forking`, `oneshot`, `notify`, `idle`.
  `Type=simple` means the process started by `ExecStart` is the service.
- **`Restart=`** — `no`, `on-failure`, `always`, `on-abnormal`.
- **`User=`/`Group=`** — drop privileges. A service without `User=` runs as
  root.
- **`Environment=`/`EnvironmentFile=`** — configuration without editing the
  unit.
- **`After=`/`Wants=`/`Requires=`** — ordering and dependency.
- **`WantedBy=`** — which target pulls the unit in when enabled.

Sandboxing directives (also objective 3.3): `NoNewPrivileges`,
`ProtectSystem`, `ProtectHome`, `PrivateTmp`, `PrivateDevices`,
`ProtectKernelTunables`, `ProtectControlGroups`, `RestrictAddressFamilies`,
`SystemCallFilter`, `ReadOnlyPaths`, `InaccessiblePaths`.

## The systemctl workflow

```bash
systemctl status sshd
sudo systemctl start sshd
sudo systemctl stop sshd
sudo systemctl restart sshd
sudo systemctl reload sshd        # re-read config, keep connections
sudo systemctl enable sshd        # start at boot
sudo systemctl enable --now sshd
sudo systemctl disable sshd
sudo systemctl mask cups          # prevent any start, even as a dependency
sudo systemctl unmask cups
systemctl is-active sshd
systemctl is-enabled sshd
systemctl list-units --type=service --state=running
systemctl list-unit-files --state=enabled
systemctl --failed
systemctl cat sshd
sudo systemctl edit sshd
sudo systemctl daemon-reload      # after editing any unit file
systemctl show -p Restart sshd
```

Rules:

- Reboot the service with `restart`, not `start`, after editing a unit.
- `reload` only works if the service implements it.
- Masking is stronger than disabling: a masked unit cannot be started as a
  dependency either.
- `daemon-reload` is required after changing unit files, not after changing a
  program's own config.

## Targets

A target is a group of units, the systemd replacement for runlevels.

| Target | Roughly equivalent to |
|---|---|
| `poweroff.target` | runlevel 0 |
| `rescue.target` | single-user |
| `multi-user.target` | runlevel 3, no GUI |
| `graphical.target` | runlevel 5 |
| `reboot.target` | runlevel 6 |

```bash
systemctl get-default
sudo systemctl set-default multi-user.target
sudo systemctl isolate rescue.target
systemd-analyze
systemd-analyze blame
systemd-analyze critical-chain
```

## Timers

A timer replaces cron with logging and dependency handling:

```ini
# /etc/systemd/system/backup.timer
[Unit]
Description=Daily backup

[Timer]
OnCalendar=*-*-* 02:15:00
Persistent=true
Unit=backup.service

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl enable --now backup.timer
systemctl list-timers --all
systemd-analyze calendar '*-*-* 02:15:00'
journalctl -u backup.service
```

`Persistent=true` runs a missed job after boot — the systemd equivalent of
`anacron`.

## Logging for services

```bash
journalctl -u sshd -b
journalctl -u sshd --since '1 hour ago'
journalctl -p err -b
journalctl -f
```

`StandardOutput=journal` is the default. Do not redirect to a file in the unit
unless you also handle rotation; journald already rotates via
`/etc/systemd/journald.conf`.

## Mission 10 — what you build

`pkg_audit.py --root .` reads the fixtures and prints:

- `installed_packages` — lines with `install ok installed`,
- `config_only_packages` — lines with `deinstall ok config-files`,
- `untrusted_repos` — repository lines that are not `https` **and** have no
  `signed-by=` option,
- `failed_units` — units marked `failed` in `systemctl_failed.txt`,
- `unit_issues` — `{unit file: [issues]}` where every service must set
  `Restart=` and must set `User=` (running as root is an issue).

The package fixture uses real `dpkg -l` syntax; the unit files use real
systemd syntax. Run `python3 main.py verify 10`.

## Exam traps

- `apt remove` keeps configuration; `apt purge` deletes it.
- `dnf` resolves dependencies; `rpm -i` does not.
- `gpgcheck=0` or plain `http` means packages can be tampered with.
- Editing a unit under `/usr/lib` is overwritten by the next package update.
- `systemctl start` after editing a unit may keep old state; use `restart`.
- `enable` does not start; `start` does not enable.
- `mask` beats `disable`.
- A service with no `User=` runs as root.
- `daemon-reload` is not the same as `restart`.

## Check yourself

1. Which command shows which package owns `/usr/sbin/nginx` on each family?
2. What is the difference between `apt remove` and `apt purge`?
3. Where should administrator unit overrides live?
4. What does `WantedBy=multi-user.target` do?
5. How do you run a job daily at 02:15 with systemd, and what makes it catch
   up after downtime?
6. Which directives would you add to stop a service from writing outside its
   data directory?
7. What does `systemctl mask` do that `disable` does not?

## Going deeper

- Write a unit for a small Python service, sandbox it with `ProtectSystem`
  and `PrivateTmp`, and verify with `systemd-analyze security`.
- Convert a cron job to a timer and confirm `Persistent=true` behaviour by
  stopping the machine over the scheduled time.
- Add a third-party apt repository with a `signed-by` keyring and then break
  the key to see the failure.
- Use `apt-mark hold` and `dnf versionlock` to pin a package and observe an
  upgrade being blocked.
