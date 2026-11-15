# Module 22 — Network and security incident triage

> **Exam objectives:** Linux+ 5.3 (given a scenario, troubleshoot common
> network issues) and 5.4 (given a scenario, troubleshoot and resolve security
> issues).
> **Study time:** about 120 minutes, including the mission.
> **Mission:** `net_triage.py` — correlate interface, route, DNS, socket,
> SELinux, TLS, and firewall evidence into prioritized findings plus a
> `triage.md` runbook.

## What the exam expects

### Network (5.3)

- DNS and name resolution, DHCP, default gateway and routing,
- link state, duplex, MTU, jumbo frames, packet loss, jitter, latency,
- bonding/teaming, VLANs, bridges,
- duplicate IP addresses, ARP issues,
- IPv4/IPv6 dual stack,
- firewall and NAT effects,
- interface configuration (NetworkManager, Netplan, `ip`).

### Security (5.4)

- SELinux denials and contexts, AppArmor,
- certificate errors and expiry,
- exposed services and weak protocols,
- weak ciphers and obsolete TLS,
- unauthorized processes and persistence,
- brute-force attempts and account lockouts,
- file integrity and audit evidence.

The two domains meet constantly: “the app is unreachable” can be a down link,
a missing route, a DNS failure, a firewall rule, an SELinux denial, or an
expired certificate. The job is to **discriminate**, not to guess.

## A layered triage method

Work from the bottom up, because a higher layer cannot work if a lower one is
broken:

```
1. Link        ip link / ethtool          is the interface up with carrier?
2. Address     ip addr                    does it have the right IP, no conflict?
3. Route       ip route / ip route get    is there a path to the destination?
4. Name        dig / getent / resolvectl  does the name resolve?
5. Port        ss -tulpn / nc -vz         is something listening and reachable?
6. TLS         openssl s_client           is the handshake valid and modern?
7. Policy      nft/firewalld/ufw, SELinux does policy allow the traffic?
8. Application app logs / health endpoint is the app itself healthy?
```

Stop at the first layer that fails; everything above it is noise until it is
fixed.

## Link and interface state

```bash
ip -br addr
ip link
ip -s link
ethtool eth0
ethtool -S eth0
```

- `state UP` and `LOWER_UP` — administratively up and carrier detected.
- `state DOWN` — interface disabled or no carrier. `ip link set eth0 up`.
- `NO-CARRIER` — cable, switch port, or SFP problem.
- `speed`/`duplex` mismatch — a classic cause of slow, lossy links. Modern
  autonegotiation usually handles it; a hard-coded 100/full on one side and
  autoneg on the other does not.

```bash
dmesg | grep -i eth0
journalctl -k | grep -i link
nmcli device status
```

## MTU and black holes

The MTU is the largest IP packet an interface sends. Ethernet is 1500; jumbo
frames are 9000. A mismatch causes small packets (ping, DNS, TCP handshake) to
work while large packets (TLS, file transfer) silently disappear.

```bash
ip link show eth3 | grep mtu
ping -M do -s 1472 10.0.0.1    # 1472 + 28 = 1500
ping -M do -s 8972 10.0.0.1    # jumbo test
tracepath 10.0.0.1             # path MTU discovery
```

Fixes: set a consistent MTU (`ip link set eth3 mtu 1500`), enable
`net.ipv4.tcp_mtu_probing=1`, or fix the switch/router configuration. A host
with MTU 9000 on a 1500 network is a classic incident.

## Addresses, duplicates, and ARP

```bash
ip addr
ip neigh
arping -D -I eth1 10.0.0.15    # duplicate address detection
```

A **duplicate IP** appears as the same address on two interfaces or two hosts.
Symptoms: intermittent connectivity, ARP flapping, sessions resetting. Find it
with `ip addr` and `arping`, then remove one (`ip addr del 10.0.0.15/24 dev
eth2`) and fix the DHCP reservation or static config.

ARP spoofing looks similar but is malicious: one MAC claims another host's IP.
Detection needs `arpwatch`, switch port security, or dynamic ARP inspection.

## Routing

```bash
ip route
ip route get 10.0.1.20
ip -6 route
sysctl net.ipv4.ip_forward
```

- No `default via` — no route off the local subnet.
- Wrong gateway — traffic leaves but never returns.
- Asymmetric routing — replies take a different path and are dropped by a
  stateful firewall.
- Missing return route on the destination network.

```bash
ip route add default via 10.0.0.1
ip route del default
ip route replace default via 10.0.0.1 dev eth1
```

Persist with NetworkManager (`nmcli`) or Netplan, not `ip`, which is
temporary. `ip route get` is the definitive answer to “which interface and
source address will this packet use?”.

## DNS

```bash
cat /etc/resolv.conf
cat /etc/nsswitch.conf
getent hosts app.internal
dig app.internal
dig @10.0.0.53 app.internal
dig +trace app.internal
resolvectl status
resolvectl query app.internal
```

Status codes in `dig`:

| Status | Meaning |
|---|---|
| `NOERROR` | the query was answered (may still be NXDOMAIN for the name) |
| `NXDOMAIN` | the name does not exist |
| `SERVFAIL` | the resolver failed — broken zone, DNSSEC failure, unreachable upstream |
| `REFUSED` | the server refuses to answer (ACL) |
| `TIMEOUT` | no response — firewall, dead server, wrong address |

`SERVFAIL` points at the resolver or the zone, not at the client's `/etc/hosts`.
Check the configured nameserver, test it directly with `dig @server`, and
verify UDP/TCP 53 is allowed. `getent` follows `nsswitch.conf`; `dig` does not.

## Sockets and exposed services

```bash
ss -tulpn
ss -tan state established
ss -s
lsof -i :443
nc -vz app.internal 443
```

A listening socket on `0.0.0.0` or `[::]` is reachable from every interface; on
`127.0.0.1` it is local-only. Inventory every listening port and ask whether it
should be exposed.

**Insecure services** to flag immediately:

| Port | Service | Why |
|---|---|---|
| 21 | FTP | clear-text credentials |
| 23 | Telnet | clear-text session |
| 25 | SMTP (open relay) | abuse, spam |
| 80 | HTTP | clear text; redirect to 443 |
| 3306 | MySQL | should never be internet-facing |
| 5432 | PostgreSQL | restrict to the app subnet |
| 6379 | Redis | often unauthenticated |

Replace FTP with SFTP, Telnet with SSH, HTTP with HTTPS, and bind databases to
private interfaces or localhost.

## SELinux denials

```
type=AVC msg=audit(...): avc: denied { read } for pid=1234 comm="nginx"
  name="index.html" scontext=system_u:system_r:httpd_t:s0
  tcontext=unconfined_u:object_r:user_home_t:s0 tclass=file permissive=0
```

Read the fields:

- `denied { read }` — the permission,
- `comm="nginx"` — the process,
- `scontext` — the process type (`httpd_t`),
- `tcontext` — the target type (`user_home_t`),
- `tclass=file` — the object class.

```bash
sudo ausearch -m AVC -ts recent
sudo ausearch -m AVC -ts recent | audit2why
sudo sealert -a /var/log/audit/audit.log
sudo restorecon -Rv /var/www/html
sudo semanage fcontext -a -t httpd_sys_content_t '/srv/web(/.*)?'
sudo setsebool -P httpd_can_network_connect on
```

The fix is to correct the label or enable the right boolean, not to disable
SELinux. `audit2allow -M mymodule` generates a policy module as a last resort;
it must be reviewed, because it can grant more than intended.

Because `setenforce 0` hides the problem, a denial in `permissive=0` (enforcing)
is the real blocker; in permissive mode the access succeeds but the denial is
still logged.

## TLS and certificates

```bash
openssl s_client -connect app.internal:443 -servername app.internal
openssl s_client -connect app.internal:443 -tls1_2
echo | openssl s_client -connect app.internal:443 2>/dev/null | \
  openssl x509 -noout -subject -issuer -dates
```

Findings:

- `self-signed certificate` (`verify error:num=18`) — no trusted chain,
- `certificate has expired` — renew and reload the service,
- `Protocol : TLSv1` or `TLSv1.1` — obsolete, upgrade to 1.2+,
- weak cipher (RC4, 3DES, NULL, EXPORT, MD5) — remove from the cipher list,
- hostname mismatch — the certificate lacks a matching SAN.

Fix at the server: valid CA-issued certificate, `MinProtocol = TLSv1.2`,
modern cipher list, automated renewal, and a reload that actually picks up the
new certificate.

## Firewalls and policy

```bash
sudo nft list ruleset
sudo firewall-cmd --list-all
sudo ufw status verbose
sudo iptables -L -n -v
ss -tulpn
```

A port can be listening and still unreachable because:

- the host firewall drops it,
- a network ACL or security group blocks it,
- NAT/port forwarding is wrong or `ip_forward` is off,
- the service binds only to localhost,
- SELinux denies the bind (`httpd_can_network_bind`).

Confirm from both ends: `nc -vz` from the client and `tcpdump` on the server to
see whether packets arrive.

## Security incident signals

- unexpected listening ports or new services,
- processes running from `/tmp`, `/dev/shm`, or a user's home,
- new cron jobs, systemd units, or `authorized_keys` entries,
- repeated auth failures and lockouts (`faillock`, `lastb`),
- AIDE/integrity alerts,
- outbound connections to unknown hosts,
- SUID changes and modified system binaries (`rpm -Va`, `debsums`).

```bash
sudo ss -tupn
ps -eo pid,user,etime,cmd --sort=-etime | head
crontab -l; ls /etc/cron.*
sudo find / -xdev -newer /etc/hostname -type f 2>/dev/null | head
sudo ausearch -m AVC,USER_AUTH -ts today
sudo lastb | head
```

If compromise is suspected: isolate the host, preserve evidence (snapshot,
memory, logs), do not reboot, and follow the incident response plan. A reboot
destroys volatile evidence and may trigger the attacker's persistence.

## IPv4/IPv6 dual stack

```bash
ip -6 addr
ip -6 route
ping6 -c 3 ::1
dig AAAA app.internal
sysctl net.ipv6.conf.all.disable_ipv6
```

Common issues: an application binds only to IPv4 and is unreachable over IPv6,
or a firewall allows IPv4 but not IPv6. `ss -tulpn` shows `[::]` binds. Keep
both stacks consistent or disable IPv6 deliberately.

## Bonding and bridges

```bash
cat /proc/net/bonding/bond0
ip link show bond0
bridge link
```

Bonding modes: `active-backup` (1) for redundancy without switch support,
`802.3ad` (4, LACP) for throughput with a configured switch. A bond with one
link down is degraded but working; both down is an outage. Bridges connect
interfaces at layer 2 (used by VMs, containers, and virtual routers); a bridge
without a member interface is a loop waiting to happen if STP is misconfigured.

## Mission 22 — what you build

`fixtures/` and `etc/resolv.conf` hold evidence from a host that cannot reach
its application: interface state, routes, dig output, sockets, SELinux AVCs, a
TLS handshake, and firewall rules. `net_triage.py --root .` must print:

- `default_gateway` — address after `default via`, or `""`,
- `duplicate_ips` — `{"<ip>": ["iface", ...]}`,
- `mtu_mismatch` — non-loopback interfaces whose MTU is not 1500,
- `link_down` — non-loopback interfaces in state `DOWN`,
- `dns_status` — `status:` from `dig` (for example `SERVFAIL`),
- `dns_ok` — true only for `NOERROR`,
- `listening_ports` — sorted TCP `LISTEN` ports,
- `insecure_services` — sorted listening ports in `{21, 23, 25, 80}`,
- `selinux_denials` — `[{permission, comm, target_type}, ...]`,
- `selinux_denial_count`,
- `tls_protocol`, `tls_cipher`, `tls_issues` — self-signed, obsolete protocol,
  weak cipher,
- `firewall_open_ports` — sorted dports accepted by nftables,
- `issues` — `[{severity, category, evidence, action}, ...]`,
- `recommendations` — one action per issue.

Then write `triage.md` as a runbook using the real commands: `ip route`,
`ip addr`, `dig`, `ss -tulpn`, `ausearch`, `restorecon`, `openssl s_client`,
and name the exposed 3306 database port. Run `python3 main.py verify 22`.

## Exam traps

- A failed `ping` does not prove a service is down; ICMP may be filtered.
- Small packets working while large ones fail means MTU, not DNS.
- `dig` ignores `/etc/hosts`; `getent` follows `nsswitch`.
- `SERVFAIL` is a resolver/zone problem, not “the name does not exist”.
- A listening port can still be blocked by the host firewall or a network ACL.
- `0.0.0.0` means every interface, not localhost.
- A self-signed certificate works technically but fails trust verification.
- `setenforce 0` hides the denial; fix the label or boolean.
- Rebooting a suspected compromised host destroys evidence.
- Binding a database to `0.0.0.0` is how 3306 ends up on the internet.

## Check yourself

1. Which command tells you the interface and source address a packet will use?
2. How do you detect and fix a duplicate IP address?
3. What does `SERVFAIL` mean, and which resolver would you test?
4. Why can small pings succeed while TLS fails?
5. Which ports are insecure by default, and what replaces them?
6. How do you read an AVC denial into `permission`, `comm`, and `target_type`?
7. Which TLS details prove a handshake is obsolete or untrusted?
8. What is the first step when you suspect a host is compromised?

## Going deeper

- Reproduce each failure in a VM: duplicate IP, MTU mismatch, missing default
  route, SERVFAIL, SELinux denial, expired certificate.
- Capture traffic with `tcpdump` while changing one variable at a time.
- Write an incident timeline from the fixtures and map each finding to an
  action.
- Harden a host by removing FTP/Telnet, restricting 3306, and enforcing
  TLS 1.2+.
