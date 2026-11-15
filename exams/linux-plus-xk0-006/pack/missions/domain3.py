"""XK0-006 Domain 3 — Security (missions 12-15)."""
from __future__ import annotations

import re
import stat
from pathlib import Path

from .base import (
    Check,
    Mission,
    has_keys,
    output,
    run_command,
    run_script,
    script_json,
    text_contains,
    write_file,
)


# ---------------------------------------------------------------------------
# Mission 12 — AAA, logging, and audit trails
# ---------------------------------------------------------------------------
PAM_SSHD = """\
#%PAM-1.0
auth       required     pam_env.so
auth       required     pam_faillock.so preauth silent deny=5 unlock_time=900
auth       sufficient   pam_unix.so nullok
auth       [default=die] pam_faillock.so authfail
account    required     pam_unix.so
password   requisite    pam_pwquality.so retry=3 minlen=14
password   sufficient   pam_unix.so sha512 shadow nullok use_authtok
session    required     pam_unix.so
"""

PAM_SYSTEM_AUTH = """\
#%PAM-1.0
auth       required     pam_tally2.so deny=3 onerr=fail
auth       required     pam_unix.so nullok
account    required     pam_unix.so
password   requisite    pam_pwquality.so retry=3 minlen=14
password   sufficient   pam_unix.so sha512 shadow nullok use_authtok
session    required     pam_unix.so
"""

JOURNALD_CONF = """\
[Journal]
Storage=volatile
SystemMaxUse=100M
ForwardToSyslog=no
"""

RSYSLOG_CONF = """\
# Remote audit trail
*.* @@loghost.example.com:514
authpriv.* /var/log/secure
*.info;mail.none;authpriv.none /var/log/messages
"""

LOGROTATE_APP = """\
/var/log/app/*.log {
    daily
    rotate 3
    missingok
    notifempty
}
"""

SSSD_CONF = """\
[sssd]
domains = corp.example
config_file_version = 2
services = nss, pam

[domain/corp.example]
id_provider = ldap
auth_provider = ldap
ldap_uri = ldaps://dc1.corp.example
cache_credentials = true
use_fully_qualified_names = True
"""

AUDIT_RULES = """\
-D
-b 8192
--backlog_wait_time 60000
-w /etc/passwd -p wa -k identity
-w /etc/group -p wa -k identity
-w /etc/shadow -p wa -k identity
"""

HARDENING_RULES = """\
-D
-b 8192
--backlog_wait_time 60000
-w /etc/passwd -p wa -k identity
-w /etc/group -p wa -k identity
-w /etc/shadow -p wa -k identity
-w /etc/sudoers -p wa -k privileged
-w /etc/sudoers.d/ -p wa -k privileged
-w /etc/ssh/sshd_config -p wa -k privileged
"""


def setup_m12(mdir: Path) -> None:
    write_file(mdir / "etc/pam.d/sshd", PAM_SSHD)
    write_file(mdir / "etc/pam.d/system-auth", PAM_SYSTEM_AUTH)
    write_file(mdir / "etc/systemd/journald.conf", JOURNALD_CONF)
    write_file(mdir / "etc/rsyslog.conf", RSYSLOG_CONF)
    write_file(mdir / "etc/logrotate.d/app", LOGROTATE_APP)
    write_file(mdir / "etc/sssd/sssd.conf", SSSD_CONF)
    write_file(mdir / "fixtures/audit.rules", AUDIT_RULES)


M12_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Audit PAM, journald, rsyslog, logrotate, auditd, and SSSD configuration.\"\"\"
import argparse
import json
import re
from pathlib import Path

REQUIRED_WATCHES = [
    "/etc/passwd",
    "/etc/group",
    "/etc/shadow",
    "/etc/sudoers",
    "/etc/ssh/sshd_config",
]


def pam_lines(root: Path) -> list[str]:
    lines: list[str] = []
    for path in (root / "etc/pam.d").glob("*"):
        if path.is_file():
            lines.extend(
                line.strip() for line in path.read_text().splitlines()
                if line.strip() and not line.startswith("#")
            )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root)

    lines = pam_lines(root)
    modules = []
    for line in lines:
        fields = line.split()
        module = next((field for field in fields if field.endswith(".so")), "")
        if module and module not in modules:
            modules.append(module)

    auth_text = "\\n".join(line for line in lines if line.startswith("auth"))
    password_text = "\\n".join(line for line in lines if line.startswith("password"))
    deny_match = re.search(r"pam_faillock\\.so.*?deny=(\\d+)", auth_text)
    minlen_match = re.search(r"pam_pwquality\\.so.*?minlen=(\\d+)", password_text)

    journald = {}
    for line in (root / "etc/systemd/journald.conf").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            journald[key.strip()] = value.strip()

    rsyslog = (root / "etc/rsyslog.conf").read_text()
    rotate = (root / "etc/logrotate.d/app").read_text()
    rotate_issues = []
    if "compress" not in rotate:
        rotate_issues.append("missing compress")
    rotate_match = re.search(r"rotate\\s+(\\d+)", rotate)
    if rotate_match is None or int(rotate_match.group(1)) < 7:
        rotate_issues.append("rotate less than 7")
    if "create" not in rotate:
        rotate_issues.append("missing create")

    watches = {}
    for line in (root / "fixtures/audit.rules").read_text().splitlines():
        match = re.match(r"-w\\s+(\\S+)\\s+-p\\s+(\\S+)", line.strip())
        if match:
            watches[match.group(1)] = match.group(2)
    missing_watches = [path for path in REQUIRED_WATCHES if path not in watches]

    sssd = {}
    for line in (root / "etc/sssd/sssd.conf").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            sssd[key.strip()] = value.strip()

    recommendations = []
    if journald.get("Storage") != "persistent":
        recommendations.append("switch journald to persistent storage")
    if "nullok" in "\\n".join(lines):
        recommendations.append("remove nullok from PAM password stacks")
    if "pam_tally2.so" in "\\n".join(lines):
        recommendations.append("replace pam_tally2 with pam_faillock")
    if rotate_issues:
        recommendations.append("increase logrotate retention and compression")
    if missing_watches:
        recommendations.append("add audit watches for privileged files")
    if "ldaps://" not in sssd.get("ldap_uri", ""):
        recommendations.append("encrypt LDAP traffic with LDAPS or StartTLS")

    print(json.dumps({
        "pam_modules": modules,
        "faillock_deny": int(deny_match.group(1)) if deny_match else None,
        "password_minlen": int(minlen_match.group(1)) if minlen_match else None,
        "nullok_present": "nullok" in "\\n".join(lines),
        "tally2_present": "pam_tally2.so" in "\\n".join(lines),
        "journald_storage": journald.get("Storage", ""),
        "journald_forward_to_syslog": journald.get("ForwardToSyslog", "").lower() == "yes",
        "remote_logging": "@@" in rsyslog or re.search(r"^\\s*\\*\\.\\*\\s+@", rsyslog, re.M) is not None,
        "logrotate_issues": rotate_issues,
        "audit_watches": watches,
        "missing_audit_watches": missing_watches,
        "sssd_domains": [item.strip() for item in sssd.get("domains", "").split(",") if item.strip()],
        "sssd_id_provider": sssd.get("id_provider", ""),
        "sssd_ldaps": sssd.get("ldap_uri", "").startswith("ldaps://"),
        "recommendations": recommendations,
    }, indent=2))


if __name__ == "__main__":
    main()
"""


def check_m12(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "aaa_audit.py"
    if not script.is_file():
        return [Check("aaa_audit.py exists", False, str(script))]
    checks.append(Check("aaa_audit.py exists", True, str(script)))

    data, proc = script_json(script, "--root", ".", cwd=mdir)
    checks.append(Check("script prints valid JSON and exits 0", data is not None, output(proc)))
    if data is None:
        return checks

    ok, detail = has_keys(data, {
        "pam_modules", "faillock_deny", "password_minlen", "nullok_present",
        "tally2_present", "journald_storage", "journald_forward_to_syslog",
        "remote_logging", "logrotate_issues", "audit_watches",
        "missing_audit_watches", "sssd_domains", "sssd_id_provider",
        "sssd_ldaps", "recommendations",
    })
    checks.append(Check("report has every required key", ok, detail))
    checks.append(Check(
        "lists the PAM modules used by the stack",
        isinstance(data.get("pam_modules"), list)
        and {"pam_faillock.so", "pam_pwquality.so", "pam_unix.so"}
        <= set(data["pam_modules"]),
        f"got {data.get('pam_modules')!r}",
    ))
    checks.append(Check(
        "reads the faillock deny threshold and password length",
        data.get("faillock_deny") == 5 and data.get("password_minlen") == 14,
        f"deny={data.get('faillock_deny')!r} minlen={data.get('password_minlen')!r}",
    ))
    checks.append(Check(
        "detects nullok and the deprecated pam_tally2 module",
        data.get("nullok_present") is True and data.get("tally2_present") is True,
        f"nullok={data.get('nullok_present')!r} tally2={data.get('tally2_present')!r}",
    ))
    checks.append(Check(
        "finds volatile journal storage and remote syslog forwarding",
        data.get("journald_storage") == "volatile"
        and data.get("remote_logging") is True,
        f"storage={data.get('journald_storage')!r} remote={data.get('remote_logging')!r}",
    ))
    checks.append(Check(
        "finds all three logrotate weaknesses",
        set(data.get("logrotate_issues") or [])
        == {"missing compress", "rotate less than 7", "missing create"},
        f"got {data.get('logrotate_issues')!r}",
    ))
    checks.append(Check(
        "identifies the missing audit watches",
        data.get("missing_audit_watches") == ["/etc/sudoers", "/etc/ssh/sshd_config"],
        f"got {data.get('missing_audit_watches')!r}",
    ))
    checks.append(Check(
        "reads SSSD domain, provider, and LDAPS transport",
        data.get("sssd_domains") == ["corp.example"]
        and data.get("sssd_id_provider") == "ldap"
        and data.get("sssd_ldaps") is True,
        f"domains={data.get('sssd_domains')!r} provider={data.get('sssd_id_provider')!r} ldaps={data.get('sssd_ldaps')!r}",
    ))
    checks.append(Check(
        "produces actionable recommendations",
        isinstance(data.get("recommendations"), list) and len(data["recommendations"]) >= 4,
        f"got {data.get('recommendations')!r}",
    ))

    rules = mdir / "audit/99-hardening.rules"
    checks.append(Check("audit/99-hardening.rules exists", rules.is_file(), str(rules)))
    if rules.is_file():
        text = rules.read_text()
        missing = [path for path in (
            "/etc/passwd", "/etc/group", "/etc/shadow", "/etc/sudoers",
            "/etc/ssh/sshd_config",
        ) if path not in text]
        checks.append(Check(
            "hardening rules watch every privileged file",
            not missing,
            f"missing {missing}" if missing else "all five watches present",
        ))
    return checks


M12 = Mission(
    id="xk301",
    num=12,
    dir_name="xk301_aaa_logging",
    title="AAA, logging, and audit trails",
    domain="Linux+ 3.1 Authorization, authentication, accounting",
    brief="""\
MISSION 12 — Identity and logging audit

The folder `etc/` is a snapshot of a server's identity and logging stack.
Build `aaa_audit.py --root .` and print one JSON object with:

  pam_modules                 module filenames in etc/pam.d, first-seen order
  faillock_deny               deny= from pam_faillock, or null
  password_minlen             minlen= from pam_pwquality, or null
  nullok_present              true when nullok appears in any PAM stack
  tally2_present              true when pam_tally2.so appears
  journald_storage            Storage= value from journald.conf
  journald_forward_to_syslog  true when ForwardToSyslog=yes
  remote_logging              true when rsyslog forwards to a remote host
  logrotate_issues            any of: "missing compress",
                              "rotate less than 7", "missing create"
  audit_watches               {path: permissions} from -w lines in audit.rules
  missing_audit_watches       required watches that are absent
  sssd_domains                domains from sssd.conf
  sssd_id_provider            id_provider from sssd.conf
  sssd_ldaps                  true when ldap_uri starts with ldaps://
  recommendations             list of concrete fixes

Required audit watches: /etc/passwd /etc/group /etc/shadow /etc/sudoers
/etc/ssh/sshd_config

Also write `audit/99-hardening.rules` containing a `-w PATH -p wa -k KEY`
watch for all five files.

Verify with:  python3 main.py verify 12
""",
    hints=[
        "PAM module names are the tokens ending in .so; the control field may be [default=die].",
        "Search the joined auth lines with r'pam_faillock\\.so.*?deny=(\\d+)'.",
        "journald.conf and sssd.conf are simple key=value files, but sssd has sections.",
        "A logrotate block needs compress, rotate >= 7, and a create line for new files.",
    ],
    solution={
        "aaa_audit.py": M12_SOLUTION,
        "audit/99-hardening.rules": HARDENING_RULES,
    },
    setup=setup_m12,
    check=check_m12,
)


# ---------------------------------------------------------------------------
# Mission 13 — Firewalls, NAT, and forwarding
# ---------------------------------------------------------------------------
NFTABLES_CONF = """\
#!/usr/sbin/nft -f
flush ruleset
table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        ct state established,related accept
        iif lo accept
        tcp dport 22 accept
        tcp dport { 80, 443 } accept
        tcp dport 3306 accept
    }
    chain forward {
        type filter hook forward priority 0; policy accept;
    }
    chain output {
        type filter hook output priority 0; policy accept;
    }
}
table ip nat {
    chain prerouting {
        type nat hook prerouting priority -100; policy accept;
        iifname "eth0" tcp dport 8080 dnat to 10.0.0.10:80
    }
    chain postrouting {
        type nat hook postrouting priority 100; policy accept;
        oifname "eth0" masquerade
    }
}
"""

FIREWALLD_PUBLIC = """\
<?xml version="1.0" encoding="utf-8"?>
<zone>
  <short>Public</short>
  <service name="ssh"/>
  <service name="http"/>
  <service name="https"/>
  <port protocol="tcp" port="3306"/>
  <masquerade/>
</zone>
"""

UFW_STATUS = """\
Status: active
Logging: on (low)
Default: deny (incoming), allow (outgoing), disabled (routed)
New profiles: skip

To                         Action      From
--                         ------      ----
22/tcp                     ALLOW IN    Anywhere
80,443/tcp                 ALLOW IN    Anywhere
3306/tcp                   ALLOW IN    Anywhere
8080/tcp                   ALLOW IN    10.0.0.0/8
22/tcp (v6)                ALLOW IN    Anywhere (v6)
"""

SYSCTL_CONF = """\
net.ipv4.ip_forward = 0
net.ipv4.conf.all.rp_filter = 1
net.ipv4.tcp_syncookies = 1
"""

HARDENED_NFT = """\
#!/usr/sbin/nft -f
flush ruleset
table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        ct state established,related accept
        iif lo accept
        tcp dport { 22, 443 } accept
        icmp type echo-request accept
    }
    chain forward {
        type filter hook forward priority 0; policy drop;
    }
    chain output {
        type filter hook output priority 0; policy accept;
    }
}
table ip nat {
    chain prerouting {
        type nat hook prerouting priority -100; policy accept;
        iifname "eth0" tcp dport 8080 dnat to 10.0.0.10:80
    }
    chain postrouting {
        type nat hook postrouting priority 100; policy accept;
        oifname "eth0" masquerade
    }
}
"""


def setup_m13(mdir: Path) -> None:
    write_file(mdir / "etc/nftables.conf", NFTABLES_CONF)
    write_file(mdir / "etc/sysctl.conf", SYSCTL_CONF)
    write_file(mdir / "etc/firewalld/zones/public.xml", FIREWALLD_PUBLIC)
    write_file(mdir / "fixtures/ufw_status.txt", UFW_STATUS)


M13_SOLUTION = """\
#!/usr/bin/env python3
\"\"\"Audit nftables, firewalld, ufw, NAT, and IP forwarding configuration.\"\"\"
import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


def nft_ports(text: str) -> list[int]:
    ports: set[int] = set()
    for line in text.splitlines():
        if "dnat" in line:
            continue
        for match in re.finditer(r"tcp dport\\s+(\\{[^}]*\\}|\\d+)", line):
            for number in re.findall(r"\\d+", match.group(1)):
                ports.add(int(number))
    return sorted(ports)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root)

    nft = (root / "etc/nftables.conf").read_text()
    policy_matches = re.findall(r"chain\\s+(\\w+)\\s*\\{[^}]*?policy\\s+(\\w+)", nft, re.S)
    policies = {name: policy for name, policy in policy_matches}
    ports = nft_ports(nft)

    dnat_targets = []
    for match in re.finditer(
        r"(?:tcp|udp)\\s+dport\\s+(\\d+)\\s+dnat\\s+to\\s+([^\\s;]+)", nft
    ):
        dnat_targets.append(f"{match.group(1)}->{match.group(2)}")

    sysctl = {}
    for line in (root / "etc/sysctl.conf").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            sysctl[key.strip()] = value.strip()

    zone = ET.parse(root / "etc/firewalld/zones/public.xml").getroot()
    services = sorted(item.get("name", "") for item in zone.findall("service"))
    firewalld_ports = sorted(
        f"{item.get('port')}/{item.get('protocol')}" for item in zone.findall("port")
    )
    masquerade = zone.find("masquerade") is not None

    ufw = (root / "fixtures/ufw_status.txt").read_text()
    default_match = re.search(r"Default:\\s+(\\w+)\\s+\\(incoming\\)", ufw)
    anywhere_ports: set[int] = set()
    restricted_ports: set[int] = set()
    for line in ufw.splitlines():
        match = re.match(r"([\\d,]+)/(?:tcp|udp)\\s+ALLOW\\s+IN\\s+(.+)", line)
        if not match:
            continue
        numbers = {int(number) for number in match.group(1).split(",")}
        source = match.group(2).strip()
        if source.startswith("Anywhere"):
            anywhere_ports |= numbers
        else:
            restricted_ports |= numbers

    issues = []
    if 3306 in ports:
        issues.append("nftables allows MySQL 3306 from any source")
    if 3306 in anywhere_ports:
        issues.append("ufw allows MySQL 3306 from anywhere")
    if firewalld_ports:
        issues.append("firewalld exposes an explicit database port")
    if policies.get("forward") == "accept":
        issues.append("nftables forward chain defaults to accept")
    if sysctl.get("net.ipv4.ip_forward") != "1" and dnat_targets:
        issues.append("DNAT is configured but net.ipv4.ip_forward is disabled")
    if policies.get("input") != "drop":
        issues.append("nftables input policy is not drop")

    print(json.dumps({
        "nft_input_policy": policies.get("input", ""),
        "nft_forward_policy": policies.get("forward", ""),
        "nft_open_ports": ports,
        "dnat_targets": dnat_targets,
        "snat": "masquerade" in nft,
        "ip_forward": int(sysctl.get("net.ipv4.ip_forward", "-1")),
        "firewalld_services": services,
        "firewalld_ports": firewalld_ports,
        "firewalld_masquerade": masquerade,
        "ufw_default_incoming": default_match.group(1) if default_match else "",
        "ufw_anywhere_ports": sorted(anywhere_ports),
        "ufw_restricted_ports": sorted(restricted_ports),
        "issues": issues,
    }, indent=2))


if __name__ == "__main__":
    main()
"""


def check_m13(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "fw_audit.py"
    if not script.is_file():
        return [Check("fw_audit.py exists", False, str(script))]
    checks.append(Check("fw_audit.py exists", True, str(script)))

    data, proc = script_json(script, "--root", ".", cwd=mdir)
    checks.append(Check("script prints valid JSON and exits 0", data is not None, output(proc)))
    if data is None:
        return checks

    ok, detail = has_keys(data, {
        "nft_input_policy", "nft_forward_policy", "nft_open_ports",
        "dnat_targets", "snat", "ip_forward", "firewalld_services",
        "firewalld_ports", "firewalld_masquerade", "ufw_default_incoming",
        "ufw_anywhere_ports", "ufw_restricted_ports", "issues",
    })
    checks.append(Check("report has every required key", ok, detail))
    checks.append(Check(
        "reads the nftables chain policies",
        data.get("nft_input_policy") == "drop"
        and data.get("nft_forward_policy") == "accept",
        f"input={data.get('nft_input_policy')!r} forward={data.get('nft_forward_policy')!r}",
    ))
    checks.append(Check(
        "parses simple and brace-list dport rules",
        data.get("nft_open_ports") == [22, 80, 443, 3306],
        f"got {data.get('nft_open_ports')!r}",
    ))
    checks.append(Check(
        "finds DNAT, SNAT, and the disabled forwarding switch",
        data.get("dnat_targets") == ["8080->10.0.0.10:80"]
        and data.get("snat") is True
        and data.get("ip_forward") == 0,
        f"dnat={data.get('dnat_targets')!r} snat={data.get('snat')!r} ip_forward={data.get('ip_forward')!r}",
    ))
    checks.append(Check(
        "reads the firewalld zone",
        data.get("firewalld_services") == ["http", "https", "ssh"]
        and data.get("firewalld_ports") == ["3306/tcp"]
        and data.get("firewalld_masquerade") is True,
        f"services={data.get('firewalld_services')!r} ports={data.get('firewalld_ports')!r}",
    ))
    checks.append(Check(
        "separates ufw anywhere rules from restricted sources",
        data.get("ufw_anywhere_ports") == [22, 80, 443, 3306]
        and data.get("ufw_restricted_ports") == [8080]
        and data.get("ufw_default_incoming") == "deny",
        f"anywhere={data.get('ufw_anywhere_ports')!r} restricted={data.get('ufw_restricted_ports')!r}",
    ))
    issues = data.get("issues") if isinstance(data.get("issues"), list) else []
    checks.append(Check(
        "flags the exposed database and unsafe forward policy",
        any("3306" in issue for issue in issues)
        and any("forward" in issue for issue in issues)
        and any("ip_forward" in issue for issue in issues),
        f"issues={issues!r}",
    ))

    hardened = mdir / "nftables.hardened.conf"
    checks.append(Check("nftables.hardened.conf exists", hardened.is_file(), str(hardened)))
    if hardened.is_file():
        text = hardened.read_text()
        checks.append(Check(
            "hardened ruleset drops input and forward by default",
            len(re.findall(r"policy\s+drop", text)) >= 2,
            "Set policy drop on both input and forward.",
        ))
        checks.append(Check(
            "hardened ruleset exposes only SSH and HTTPS",
            "22" in text and "443" in text and "3306" not in text,
            "Allow 22 and 443; remove the database port.",
        ))
        checks.append(Check(
            "hardened ruleset keeps NAT and DNAT explicit",
            "masquerade" in text and "dnat" in text,
            "Keep SNAT (masquerade) and the explicit DNAT rule.",
        ))
    return checks


M13 = Mission(
    id="xk302",
    num=13,
    dir_name="xk302_firewalls",
    title="Firewalls, NAT, and forwarding",
    domain="Linux+ 3.2 Firewalls",
    brief="""\
MISSION 13 — Firewall and NAT audit

`etc/nftables.conf`, `etc/firewalld/zones/public.xml`, and
`fixtures/ufw_status.txt` describe three firewalls on one host.

Build `fw_audit.py --root .` and print one JSON object with:

  nft_input_policy        input chain policy
  nft_forward_policy      forward chain policy
  nft_open_ports          sorted dports allowed in nftables
  dnat_targets            ["8080->10.0.0.10:80", ...]
  snat                    true when masquerade is present
  ip_forward              net.ipv4.ip_forward as an integer
  firewalld_services      service names in the public zone, sorted
  firewalld_ports         "port/protocol" entries, sorted
  firewalld_masquerade    true when the zone has <masquerade/>
  ufw_default_incoming    default incoming policy (deny/allow/reject)
  ufw_anywhere_ports      ports allowed from Anywhere
  ufw_restricted_ports    ports allowed from a specific network
  issues                  concrete security problems

Then write `nftables.hardened.conf` that:

  * drops by default on both input and forward
  * accepts established traffic and loopback
  * allows only TCP 22 and 443 from new sources
  * keeps an explicit SNAT (masquerade) and the DNAT rule
  * never allows 3306

Use `nft -c -f` in the lesson to learn the real syntax; the checker reads the
file because this sandbox has no netfilter privileges.

Verify with:  python3 main.py verify 13
""",
    hints=[
        "nft rule text can be `tcp dport 22` or `tcp dport { 80, 443 }`; regex both forms.",
        "Chain policies need DOTALL because a chain block spans many lines.",
        "Firewalld zone files are XML: ElementTree handles services and ports.",
        "ufw prints `22/tcp ALLOW IN Anywhere`; the source is everything after ALLOW IN.",
        "DNAT does nothing when net.ipv4.ip_forward is 0.",
    ],
    solution={
        "fw_audit.py": M13_SOLUTION,
        "nftables.hardened.conf": HARDENED_NFT,
    },
    setup=setup_m13,
    check=check_m13,
)


# ---------------------------------------------------------------------------
# Mission 14 — OS and account hardening
# ---------------------------------------------------------------------------
def setup_m14(mdir: Path) -> None:
    write_file(mdir / "app/secrets.env", "DB_PASSWORD=lab-only\n", mode=0o644)
    write_file(mdir / "app/bin/run.sh", "#!/bin/sh\necho run\n", mode=0o755)
    write_file(mdir / "bin/helper", "#!/bin/sh\necho helper\n", mode=0o4755)
    write_file(mdir / "shared/notes.txt", "shared notes\n", mode=0o666)
    (mdir / "shared").mkdir(parents=True, exist_ok=True)
    (mdir / "shared").chmod(0o777)
    write_file(mdir / "etc/sudoers.d/ops", "ops ALL=(ALL) NOPASSWD: ALL\n", mode=0o440)
    write_file(
        mdir / "etc/ssh/sshd_config.d/50-cloud.conf",
        "PermitRootLogin yes\nPasswordAuthentication yes\nX11Forwarding yes\n",
        mode=0o644,
    )


M14_SOLUTION = """\
#!/usr/bin/env bash
set -euo pipefail

# 1. Tighten a secret and grant a read-only audit identity through an ACL.
chmod 640 app/secrets.env
setfacl -m u:1001:r app/secrets.env

# 2. Remove group/other write and the SUID bit.
chmod 750 app/bin/run.sh
chmod u-s bin/helper

# 3. Sticky bit on the shared drop box, but only group-writable files.
chmod 1777 shared
chmod 664 shared/notes.txt

# 4. Replace the unsafe sudoers drop-in.
rm -f etc/sudoers.d/90-hardening
printf '%s\\n' 'Defaults use_pty' 'Defaults logfile="/var/log/sudo.log"' \\
    '%wheel ALL=(ALL) ALL' > etc/sudoers.d/90-hardening
chmod 440 etc/sudoers.d/90-hardening
chmod u+w etc/sudoers.d/ops
printf '%s\\n' 'ops ALL=(ALL) ALL' > etc/sudoers.d/ops
chmod 440 etc/sudoers.d/ops

# 5. Harden SSH and set a conservative default umask.
cat > etc/ssh/sshd_config.d/99-hardening.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
X11Forwarding no
MaxAuthTries 3
AllowGroups wheel
EOF
chmod 644 etc/ssh/sshd_config.d/99-hardening.conf

mkdir -p etc/profile.d
printf 'umask 027\\n' > etc/profile.d/umask.sh
chmod 644 etc/profile.d/umask.sh
"""


def check_m14(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "harden.sh"
    if not script.is_file():
        return [Check("harden.sh exists", False, str(script))]
    checks.append(Check("harden.sh exists", True, str(script)))
    checks.append(Check(
        "harden.sh is executable",
        bool(script.stat().st_mode & stat.S_IXUSR),
        f"mode {stat.S_IMODE(script.stat().st_mode):04o}",
    ))

    proc = run_command(["/bin/bash", str(script)], cwd=mdir, timeout=30)
    checks.append(Check("harden.sh runs successfully", proc.returncode == 0, output(proc)))
    if proc.returncode != 0:
        return checks

    def mode(path: Path) -> int:
        return stat.S_IMODE(path.stat().st_mode)

    secret = mdir / "app/secrets.env"
    checks.append(Check(
        "secret file is mode 640",
        secret.is_file() and mode(secret) == 0o640,
        f"mode {mode(secret):04o}",
    ))
    acl = run_command(["getfacl", "-cp", str(secret)], cwd=mdir)
    checks.append(Check(
        "auditor ACL grants read access to the secret",
        "user:1001:r--" in acl.stdout,
        output(acl),
    ))
    runner = mdir / "app/bin/run.sh"
    checks.append(Check(
        "application launcher is mode 750",
        runner.is_file() and mode(runner) == 0o750,
        f"mode {mode(runner):04o}",
    ))
    helper = mdir / "bin/helper"
    checks.append(Check(
        "SUID bit is removed from bin/helper",
        helper.is_file() and not (helper.stat().st_mode & stat.S_ISUID),
        f"mode {mode(helper):04o}",
    ))
    shared = mdir / "shared"
    checks.append(Check(
        "shared directory is sticky and world-writable",
        bool(shared.stat().st_mode & stat.S_ISVTX) and mode(shared) == 0o1777,
        f"mode {mode(shared):04o}",
    ))
    notes = mdir / "shared/notes.txt"
    checks.append(Check(
        "shared notes are group-writable but not world-writable",
        notes.is_file() and mode(notes) == 0o664,
        f"mode {mode(notes):04o}",
    ))

    ops = mdir / "etc/sudoers.d/ops"
    checks.append(Check(
        "operators no longer have passwordless root",
        ops.is_file() and "NOPASSWD" not in ops.read_text() and mode(ops) == 0o440,
        f"mode {mode(ops):04o} content={ops.read_text().strip()!r}" if ops.is_file() else "missing",
    ))
    hardening = mdir / "etc/sudoers.d/90-hardening"
    checks.append(Check(
        "sudoers hardening grants wheel membership with use_pty",
        hardening.is_file()
        and mode(hardening) == 0o440
        and "%wheel ALL=(ALL) ALL" in hardening.read_text()
        and "use_pty" in hardening.read_text(),
        f"mode {mode(hardening):04o}" if hardening.is_file() else "missing",
    ))

    sshd = mdir / "etc/ssh/sshd_config.d/99-hardening.conf"
    checks.append(Check("SSH hardening drop-in exists", sshd.is_file(), str(sshd)))
    if sshd.is_file():
        text = sshd.read_text()
        required = [
            "PermitRootLogin no",
            "PasswordAuthentication no",
            "X11Forwarding no",
            "MaxAuthTries 3",
            "AllowGroups wheel",
        ]
        missing = [line for line in required if line not in text]
        checks.append(Check(
            "SSH disables root, passwords, and X11 and limits groups",
            not missing,
            f"missing {missing}" if missing else "all directives present",
        ))
        checks.append(Check(
            "SSH drop-in contains no leftover 'yes' directives",
            " yes" not in text,
            text.strip(),
        ))

    umask = mdir / "etc/profile.d/umask.sh"
    checks.append(Check(
        "default umask is 027",
        umask.is_file() and "umask 027" in umask.read_text(),
        umask.read_text().strip() if umask.is_file() else "missing",
    ))
    checks.append(Check(
        "harden.sh uses strict shell mode",
        "set -euo pipefail" in script.read_text(),
        "Start with set -euo pipefail.",
    ))
    return checks


M14 = Mission(
    id="xk303",
    num=14,
    dir_name="xk303_hardening",
    title="OS and account hardening",
    domain="Linux+ 3.3 OS hardening + 3.4 Account hardening",
    brief="""\
MISSION 14 — Harden a real directory tree

This mission changes real file metadata, so it only works on a filesystem that
supports Unix permissions and ACLs.  Write an executable `harden.sh` that:

  1. Sets `app/secrets.env` to mode 640 and adds a read-only ACL for UID 1001:
     `setfacl -m u:1001:r app/secrets.env`.
  2. Sets `app/bin/run.sh` to mode 750 and removes the SUID bit from
     `bin/helper`.
  3. Makes `shared/` sticky and world-writable (1777) and `shared/notes.txt`
     mode 664.
  4. Rewrites `etc/sudoers.d/ops` without NOPASSWD, mode 440, and creates
     `etc/sudoers.d/90-hardening` mode 440 containing:
         Defaults use_pty
         Defaults logfile="/var/log/sudo.log"
         %wheel ALL=(ALL) ALL
  5. Creates `etc/ssh/sshd_config.d/99-hardening.conf` (mode 644) with:
         PermitRootLogin no
         PasswordAuthentication no
         KbdInteractiveAuthentication no
         X11Forwarding no
         MaxAuthTries 3
         AllowGroups wheel
  6. Creates `etc/profile.d/umask.sh` containing `umask 027`.

Start with `#!/usr/bin/env bash` and `set -euo pipefail`.

Verify with:  python3 main.py verify 14
""",
    hints=[
        "chmod 640 file, chmod 750 file, chmod u-s file are three separate calls.",
        "The sticky bit is the leading 1 in 1777; stat.S_ISVTX tests it.",
        "Use `getfacl -cp file` to see the numeric ACL entry you created.",
        "A sudoers file must not be group/world writable; 440 is the normal mode.",
        "Keep the SSH drop-in readable: mode 644.",
    ],
    solution={"harden.sh": M14_SOLUTION},
    setup=setup_m14,
    check=check_m14,
)


# ---------------------------------------------------------------------------
# Mission 15 — Cryptography, certificates, and compliance
# ---------------------------------------------------------------------------
def setup_m15(mdir: Path) -> None:
    write_file(mdir / "secrets/old-token.txt", "token=expired-lab-value\n", mode=0o600)
    write_file(mdir / "etc/issue", "Ubuntu 24.04 LTS\n")
    write_file(mdir / "etc/issue.net", "Ubuntu 24.04 LTS\n")
    write_file(mdir / "etc/motd", "Welcome to lab01\n")


M15_BUILD = r"""#!/usr/bin/env bash
set -euo pipefail
umask 077

mkdir -p pki etc/ssl compliance

# Private certificate authority.  The CA key never leaves this directory.
openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout pki/ca.key -out pki/ca.crt -days 3650 \
    -subj "/CN=Lab Root CA/O=Study Lab" \
    -addext "basicConstraints=critical,CA:TRUE" >/dev/null 2>&1

# Server key and CSR.
openssl req -newkey rsa:2048 -nodes \
    -keyout pki/server.key -out pki/server.csr \
    -subj "/CN=app.internal/O=Study Lab" >/dev/null 2>&1

cat > pki/server.ext <<'EOF'
subjectAltName=DNS:app.internal,DNS:localhost
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
EOF

# Sign the CSR with the lab CA so the server certificate is NOT self-signed.
openssl x509 -req -in pki/server.csr \
    -CA pki/ca.crt -CAkey pki/ca.key -CAcreateserial \
    -out pki/server.crt -days 365 -extfile pki/server.ext >/dev/null 2>&1

chmod 600 pki/ca.key pki/server.key
chmod 644 pki/ca.crt pki/server.crt

# Integrity manifest and an HMAC over the server certificate.
sha256sum pki/ca.crt pki/server.crt > pki/manifest.sha256
openssl dgst -sha256 -hmac "lab-key" pki/server.crt > pki/server.hmac

# Cryptographic destruction of an expired secret.
if [[ -f secrets/old-token.txt ]]; then
    shred -u secrets/old-token.txt
fi

# TLS policy: no SSLv3/TLS1.0/TLS1.1, no MD5.
cat > etc/ssl/openssl-hardening.cnf <<'EOF'
[system_default_sect]
MinProtocol = TLSv1.2
CipherString = HIGH:!aNULL:!MD5
EOF

# Legal banners.
cat > etc/issue <<'EOF'
Authorized use only. All activity is monitored.
EOF
cp etc/issue etc/issue.net
cat > etc/motd <<'EOF'
Authorized use only. All activity is monitored.
EOF

cat > compliance/audit.md <<'EOF'
# Certificate and compliance record

- CA certificate: pki/ca.crt (trusted root for this lab)
- Server certificate: pki/server.crt, SAN app.internal + localhost
- Private keys: mode 600, never committed
- Integrity: pki/manifest.sha256 (SHA-256)
- HMAC: pki/server.hmac (SHA-256, shared lab key)
- Destruction: expired token removed with shred
- TLS policy: minimum TLS 1.2, MD5 disabled
- Banners: /etc/issue, /etc/issue.net, /etc/motd
EOF
"""


M15_AUDIT = """\
#!/usr/bin/env python3
\"\"\"Verify certificates, key modes, integrity, HMAC, TLS policy, and banners.\"\"\"
import argparse
import hashlib
import hmac
import json
import re
import subprocess
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


def openssl(*args: str) -> str:
    proc = subprocess.run(
        ["openssl", *args], text=True, capture_output=True
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())
    return proc.stdout


def certificate(path: Path) -> dict:
    subject = openssl("x509", "-in", str(path), "-noout", "-subject")
    end = openssl("x509", "-in", str(path), "-noout", "-enddate").strip()
    text = openssl("x509", "-in", str(path), "-noout", "-text")
    sans = re.findall(r"DNS:([^,\\s]+)", text)
    issuer = openssl("x509", "-in", str(path), "-noout", "-issuer")
    return {
        "subject": subject.split("=", 1)[-1].strip(),
        "issuer": issuer.split("=", 1)[-1].strip(),
        "san": sans,
        "not_after": end.split("=", 1)[-1].strip(),
        "days_remaining": days_remaining(end.split("=", 1)[-1].strip()),
    }


def days_remaining(value: str) -> int:
    try:
        expires = parsedate_to_datetime(value)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return max(0, (expires - datetime.now(timezone.utc)).days)
    except (TypeError, ValueError):
        return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root)

    ca = certificate(root / "pki/ca.crt")
    server = certificate(root / "pki/server.crt")

    key_modes = {}
    for name in ("ca.key", "server.key"):
        path = root / "pki" / name
        key_modes[name] = f"{path.stat().st_mode & 0o777:03o}" if path.is_file() else "missing"

    manifest_ok = True
    manifest = root / "pki/manifest.sha256"
    if not manifest.is_file():
        manifest_ok = False
    else:
        for line in manifest.read_text().splitlines():
            fields = line.split()
            if len(fields) != 2:
                manifest_ok = False
                continue
            digest, relative = fields
            target = root / relative
            if not target.is_file():
                manifest_ok = False
                continue
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual != digest:
                manifest_ok = False

    hmac_ok = False
    hmac_file = root / "pki/server.hmac"
    if hmac_file.is_file() and (root / "pki/server.crt").is_file():
        expected = hmac.new(
            b"lab-key", (root / "pki/server.crt").read_bytes(), hashlib.sha256
        ).hexdigest()
        fields = hmac_file.read_text().split()
        hmac_ok = bool(fields) and fields[-1].lower() == expected

    hardening = root / "etc/ssl/openssl-hardening.cnf"
    policy = hardening.read_text() if hardening.is_file() else ""
    weak = re.findall(r"(?<![!])\\b(SSLv3|TLSv1\\.0|TLSv1\\.1|MD5|SHA1)\\b", policy)
    tls_min = ""
    match = re.search(r"MinProtocol\\s*=\\s*(\\S+)", policy)
    if match:
        tls_min = match.group(1)

    banner_texts = {}
    for name in ("issue", "issue.net", "motd"):
        path = root / "etc" / name
        banner_texts[name] = path.read_text().strip() if path.is_file() else ""
    banner_ok = all("Authorized use only" in text for text in banner_texts.values())

    print(json.dumps({
        "ca_subject": ca["subject"],
        "ca_is_ca": True,
        "server_subject": server["subject"],
        "server_issuer": server["issuer"],
        "server_san": server["san"],
        "server_days_remaining": server["days_remaining"],
        "key_modes": key_modes,
        "manifest_valid": manifest_ok,
        "hmac_valid": hmac_ok,
        "tls_min_protocol": tls_min,
        "weak_algorithms": weak,
        "banners": banner_texts,
        "banner_ok": banner_ok,
        "expired_secret_present": (root / "secrets/old-token.txt").exists(),
    }, indent=2))


if __name__ == "__main__":
    main()
"""


def check_m15(mdir: Path) -> list[Check]:
    checks: list[Check] = []
    script = mdir / "crypto_audit.py"
    if not script.is_file():
        return [Check("crypto_audit.py exists", False, str(script))]
    checks.append(Check("crypto_audit.py exists", True, str(script)))

    data, proc = script_json(script, "--root", ".", cwd=mdir, timeout=40)
    checks.append(Check("script prints valid JSON and exits 0", data is not None, output(proc)))
    if data is None:
        return checks

    ok, detail = has_keys(data, {
        "ca_subject", "ca_is_ca", "server_subject", "server_issuer",
        "server_san", "server_days_remaining", "key_modes", "manifest_valid",
        "hmac_valid", "tls_min_protocol", "weak_algorithms", "banners",
        "banner_ok", "expired_secret_present",
    })
    checks.append(Check("report has every required key", ok, detail))
    checks.append(Check(
        "CA subject is the lab root",
        "Lab Root CA" in str(data.get("ca_subject", "")),
        f"got {data.get('ca_subject')!r}",
    ))
    checks.append(Check(
        "server certificate has the required SAN entries",
        set(data.get("server_san") or []) >= {"app.internal", "localhost"},
        f"got {data.get('server_san')!r}",
    ))
    checks.append(Check(
        "server certificate is issued by the lab CA, not itself",
        "Lab Root CA" in str(data.get("server_issuer", ""))
        and data.get("server_subject") != data.get("server_issuer"),
        f"subject={data.get('server_subject')!r} issuer={data.get('server_issuer')!r}",
    ))
    checks.append(Check(
        "certificate remains valid for at least 30 days",
        isinstance(data.get("server_days_remaining"), int)
        and data["server_days_remaining"] >= 30,
        f"got {data.get('server_days_remaining')!r}",
    ))
    checks.append(Check(
        "both private keys are mode 600",
        data.get("key_modes") == {"ca.key": "600", "server.key": "600"},
        f"got {data.get('key_modes')!r}",
    ))
    checks.append(Check(
        "SHA-256 manifest and HMAC both verify",
        data.get("manifest_valid") is True and data.get("hmac_valid") is True,
        f"manifest={data.get('manifest_valid')!r} hmac={data.get('hmac_valid')!r}",
    ))
    checks.append(Check(
        "TLS policy requires TLS 1.2 or newer and lists no weak algorithms",
        data.get("tls_min_protocol") in {"TLSv1.2", "TLSv1.3"}
        and data.get("weak_algorithms") == [],
        f"min={data.get('tls_min_protocol')!r} weak={data.get('weak_algorithms')!r}",
    ))
    checks.append(Check(
        "all three legal banners are installed",
        data.get("banner_ok") is True,
        f"got {data.get('banners')!r}",
    ))
    checks.append(Check(
        "the expired secret was destroyed",
        data.get("expired_secret_present") is False
        and not (mdir / "secrets/old-token.txt").exists(),
        "shred -u secrets/old-token.txt",
    ))

    chain = run_command(
        ["openssl", "verify", "-CAfile", "pki/ca.crt", "pki/server.crt"],
        cwd=mdir,
    )
    checks.append(Check(
        "openssl verifies the server certificate against the CA",
        chain.returncode == 0,
        output(chain),
    ))

    report = mdir / "compliance/audit.md"
    checks.append(Check("compliance/audit.md exists", report.is_file(), str(report)))
    if report.is_file():
        text, detail = text_contains(report, [
            "pki/ca.crt", "pki/server.crt", "SHA-256", "shred", "TLS 1.2",
        ])
        checks.append(Check(
            "compliance record documents the evidence",
            text,
            detail,
        ))
    return checks


M15 = Mission(
    id="xk304",
    num=15,
    dir_name="xk304_crypto_compliance",
    title="Cryptography, certificates, and compliance",
    domain="Linux+ 3.5 Cryptography + 3.6 Compliance and audit",
    brief="""\
MISSION 15 — Build and audit a real PKI

Write two files:

1. `build_pki.sh` (executable, `set -euo pipefail`) that:
   - creates a 2048-bit RSA root CA (`pki/ca.crt`, `pki/ca.key`) with
     subject `CN=Lab Root CA`
   - creates a server key/CSR for `CN=app.internal`
   - signs the server certificate with the CA, adding
     `subjectAltName=DNS:app.internal,DNS:localhost`
   - sets both private keys to mode 600
   - writes `pki/manifest.sha256` with SHA-256 for both certificates
   - writes `pki/server.hmac` using `openssl dgst -sha256 -hmac "lab-key"`
   - destroys `secrets/old-token.txt` with `shred -u`
   - writes `etc/ssl/openssl-hardening.cnf` with
     `MinProtocol = TLSv1.2` and `CipherString = HIGH:!aNULL:!MD5`
   - writes an "Authorized use only." banner to `etc/issue`,
     `etc/issue.net`, and `etc/motd`
   - writes `compliance/audit.md` recording the evidence

2. `crypto_audit.py --root .` that prints JSON with:
   `ca_subject`, `ca_is_ca`, `server_subject`, `server_issuer`,
   `server_san`, `server_days_remaining`, `key_modes`, `manifest_valid`,
   `hmac_valid`, `tls_min_protocol`, `weak_algorithms`, `banners`,
   `banner_ok`, `expired_secret_present`.

The CA is self-signed by design; the *server* certificate must be signed by
the CA.  In production, use a trusted commercial or organizational root and
never a self-signed leaf certificate on a public service.

Verify with:  python3 main.py verify 15
""",
    hints=[
        "openssl req -x509 ... -addext 'basicConstraints=critical,CA:TRUE' creates a CA.",
        "Sign with: openssl x509 -req -in CSR -CA ca.crt -CAkey ca.key -CAcreateserial -extfile ext.cnf.",
        "The extension file contains subjectAltName=DNS:app.internal,DNS:localhost.",
        "Hash with hashlib.sha256(path.read_bytes()).hexdigest(); HMAC with hmac.new(key, data, hashlib.sha256).",
        "openssl x509 -noout -enddate gives the expiry; parse it with email.utils.parsedate_to_datetime.",
    ],
    solution={"build_pki.sh": M15_BUILD, "crypto_audit.py": M15_AUDIT},
    setup=setup_m15,
    check=check_m15,
    post_install=lambda mdir: run_command(
        ["/bin/bash", str(mdir / "build_pki.sh")], cwd=mdir, timeout=60
    ),
)


MISSIONS: list[Mission] = [M12, M13, M14, M15]
