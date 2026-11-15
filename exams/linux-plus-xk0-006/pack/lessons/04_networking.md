# Module 4 — Network configuration and troubleshooting tools

> **Exam objective:** Linux+ 1.4 — Given a scenario, manage network services
> and configurations on a Linux server.
> **Study time:** about 100 minutes, including the mission.
> **Mission:** `net_audit.py` — audit name resolution, interfaces, routes,
> sockets, MTU, and duplicate addresses.

## What the exam expects

You must be comfortable configuring and inspecting a Linux host's network:

- name resolution files: `/etc/hosts`, `/etc/resolv.conf`, `/etc/nsswitch.conf`,
- NetworkManager (`nmcli`) and Netplan (`netplan apply`, `try`, `status`),
- the `ip` family (`ip address`, `ip link`, `ip route`),
- diagnostic tools: `ping`, `ping6`, `dig`, `nslookup`, `hostname`, `ss`,
  `tcpdump`, `curl`, `nc`, `nmap`, `mtr`, `tracepath`, `traceroute`,
  `ethtool`, `arp`, `iperf3`.

The same tools return in troubleshooting (5.3), so learn the output shapes,
not just the commands.

## Name resolution

Linux asks several sources, in the order set by `nsswitch.conf`:

```
# /etc/nsswitch.conf
hosts: files dns myhostname
```

`files` means `/etc/hosts`; `dns` means the servers in `/etc/resolv.conf`.

```bash
cat /etc/hosts
cat /etc/resolv.conf
getent hosts app.internal       # follows nsswitch, unlike dig
```

A typical `resolv.conf`:

```
search corp.example internal.example
nameserver 10.0.0.53
nameserver 10.0.0.54
options edns0 trust-ad timeout:2 attempts:2
```

`/etc/hosts` is checked first. A stale entry there can override correct DNS and
cause “DNS is broken” tickets that are really local configuration problems.

`systemd-resolved` manages `/etc/resolv.conf` on many systems. Inspect it with:

```bash
resolvectl status
resolvectl query app.internal
```

## NetworkManager

NetworkManager is the default on most desktop and server distributions with a
GUI or cloud image. `nmcli` is the scriptable interface.

```bash
nmcli general status
nmcli device status
nmcli connection show
nmcli connection show "Wired connection 1"
nmcli connection modify "Wired connection 1" \
  ipv4.addresses 10.0.0.15/24 ipv4.gateway 10.0.0.1 \
  ipv4.dns "10.0.0.53" ipv4.method manual
nmcli connection up "Wired connection 1"
```

The exam objective lists `nmconnect`, but the real tool is `nmcli` (and
`nmtui` for a menu). Use `nmcli` in scripts. Connection profiles live in
`/etc/NetworkManager/system-connections/` and can be reloaded with
`nmcli connection reload`.

`nmcli` changes are persistent. `ip` changes are not.

## Netplan (Ubuntu)

Netplan writes YAML that renders to NetworkManager or systemd-networkd. Files
live in `/etc/netplan/*.yaml` with strict indentation.

```yaml
network:
  version: 2
  ethernets:
    eth1:
      addresses: [10.0.0.15/24]
      routes:
        - to: default
          via: 10.0.0.1
      nameservers:
        addresses: [10.0.0.53]
      mtu: 1500
```

```bash
sudo netplan try        # apply with automatic rollback if you lose access
sudo netplan apply
netplan status
```

`netplan try` waits for confirmation and reverts if you do not press Enter —
essential when configuring a remote host. `netplan status` shows the rendered
state.

## The `ip` command

`ip` replaces `ifconfig`, `route`, and `arp` on modern systems.

### Links and addresses

```bash
ip link                       # interfaces, state, MTU, MAC
ip link set eth1 up
ip addr                       # addresses
ip addr add 10.0.0.15/24 dev eth1
ip addr del 10.0.0.15/24 dev eth1
ip -br addr                   # one line per interface
```

`state UP` means the link is administratively up. `LOWER_UP` means the carrier
is detected. `state DOWN` with no carrier is a cable/switch problem; `state UP`
but no traffic is usually routing, firewall, or DNS.

### Routes

```bash
ip route
ip route add default via 10.0.0.1
ip route add 10.0.1.0/24 via 10.0.0.1 dev eth1
ip route del 10.0.1.0/24
ip route get 8.8.8.8
```

`ip route get` tells you which interface and source address the kernel will
use. That single command resolves many “which path does this take?” questions.

### Neighbours (ARP)

```bash
ip neigh
arp -n
```

ARP/neighbour entries map IPv4 addresses to MAC addresses. Duplicate IPs show
up as the same address on two interfaces, and a spoofed MAC can poison the
cache (5.3).

## Diagnostic tools

### Reachability and path

```bash
ping -c 3 10.0.0.1
ping6 -c 3 2001:db8::1
tracepath app.internal
traceroute app.internal
mtr --report app.internal       # continuous traceroute + loss
```

`ping` tests ICMP reachability. Some hosts block ICMP, so a failed ping is not
proof the service is down. `mtr` shows where loss begins, which is far more
useful than a single traceroute snapshot.

### DNS

```bash
dig app.internal
dig +short app.internal
dig @10.0.0.53 app.internal A
dig -x 10.0.0.15               # reverse lookup
nslookup app.internal
```

`dig` bypasses `nsswitch`; `getent hosts` follows it. If `dig` works but the
application fails, check `/etc/nsswitch.conf` and `/etc/hosts`.

### Sockets and services

```bash
ss -tulpn                      # TCP/UDP listening sockets with processes
ss -tan state established
lsof -i :443
nc -vz host 443                # port reachability
nmap -sT -p 22,80,443 host     # authorised scanning only
```

`ss -tulpn` is the fastest way to answer “what is listening and who owns it?”.
`0.0.0.0:22` listens on all IPv4 addresses; `127.0.0.1:5432` is local-only.

### HTTP, packet capture, and throughput

```bash
curl -v https://app.internal/healthz
curl -I http://10.0.0.15/
tcpdump -i eth1 -nn port 53
tcpdump -i any -nn -c 20 host 10.0.0.15
iperf3 -s            # server
iperf3 -c 10.0.0.20  # client
```

`tcpdump` is the ground truth for “is the packet leaving/arriving?”. Capture a
small number of packets with a filter; do not run an unfiltered capture on a
busy server.

### Link details

```bash
ethtool eth1
ethtool -S eth1
hostname
hostnamectl
```

`ethtool` reports speed, duplex, link detected, and driver statistics. A
mismatch or a half-duplex link is a classic cause of poor throughput.

## MTU, jitter, and Packet loss

The MTU is the largest frame payload an interface will send. Ethernet defaults
to 1500. A mismatch (for example 9000 jumbo frames on one host and 1500 on the
path) causes large packets to vanish while small pings still work — a
“black hole”.

```bash
ip link show eth1 | grep mtu
ping -M do -s 1472 10.0.0.1     # 1472 + 28 bytes of headers = 1500
ping -M do -s 8972 10.0.0.1     # jumbo frame test
```

`-M do` sets the Don't Fragment bit. If the large ping fails but the small one
works, the path MTU is smaller than the interface MTU.

Packet loss and jitter are measured with `mtr`, `ping`, and `iperf3`. For real
time traffic (VoIP, video), jitter matters more than average latency.

## Common failure patterns

| Symptom | First checks |
|---|---|
| No address | `ip -br addr`, DHCP logs, `nmcli device status` |
| Link down | cable, switch port, `ip link`, `ethtool` |
| Can ping IP but not name | `resolv.conf`, `nsswitch.conf`, `dig` |
| Can reach local subnet only | default route (`ip route`) |
| Some sites fail, others work | MTU / PMTUD |
| Port closed | `ss -tulpn`, firewall, `nc -vz` |
| Intermittent loss | `mtr`, `ethtool -S`, duplex mismatch |
| Duplicate address | `ip neigh`, `arping`, DHCP reservations |

## Mission 04 — what you build

Your `net_audit.py --root .` reads `etc/hosts`, `etc/resolv.conf`,
`etc/nsswitch.conf`, `fixtures/ip_addr.txt`, `fixtures/ip_route.txt`, and
`fixtures/ss.txt`, then prints:

- `default_gateway` — IPv4 address after `default via`,
- `dns_servers` and `search_domains` — in file order,
- `hosts_resolution` — the `hosts:` value from nsswitch,
- `db_internal` — the address for `db.internal` in `/etc/hosts`,
- `mtu_mismatch` — non-loopback interfaces whose MTU is not 1500,
- `duplicate_ips` — `{ip: [interfaces]}` when one address appears twice,
- `listening_ports` — sorted TCP `LISTEN` ports.

The fixture deliberately includes an MTU mismatch and an IP conflict. Build the
parsers so they would work on real command output. Run
`python3 main.py verify 4`.

## Exam traps

- `ip` changes are temporary; `nmcli` and Netplan changes persist.
- `ping` failure does not prove the service is down (ICMP may be filtered).
- `dig` ignores `/etc/hosts`; `getent` follows nsswitch.
- `ss -tulpn` needs root to show process names for other users' sockets.
- 1500 MTU includes the IP and TCP headers; the payload test size is 1472 for
  IPv4.
- A default route is not the same as a DNS server.

## Check yourself

1. Which file decides whether `/etc/hosts` is consulted before DNS?
2. How do you add an address temporarily, and which tool makes it persistent?
3. What does `ip route get 8.8.8.8` tell you?
4. Why can small pings succeed while large transfers fail?
5. Which command lists listening TCP ports with owning processes?
6. What is the difference between `state UP` and `LOWER_UP`?

## Going deeper

- Run `ss -tulpn` and explain every listening socket on your host.
- Capture a DNS query with `tcpdump -i any -nn port 53` while running `dig`.
- Build a Netplan file and test it with `netplan try` on a VM.
- Reproduce an MTU black hole with a VM network and fix it with `ip link set
  mtu`.
