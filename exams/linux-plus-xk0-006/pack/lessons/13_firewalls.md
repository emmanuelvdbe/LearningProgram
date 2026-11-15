# Module 13 — Firewalls, NAT, and forwarding

> **Exam objective:** Linux+ 3.2 — Given a scenario, configure and implement
> firewalls on a Linux system.
> **Study time:** about 100 minutes, including the mission.
> **Mission:** `fw_audit.py` — audit an nftables ruleset, a firewalld zone, and
> a ufw status, then write a hardened nftables ruleset with NAT.

## What the exam expects

- **frontends:** `firewalld` (`firewall-cmd`) and `ufw`,
- **backends:** `nftables` (`nft`) and legacy `iptables`, plus `ipset`,
- **concepts:** zones, rich rules, runtime versus permanent, stateful versus
  stateless filtering,
- **NAT:** source NAT (`SNAT`, masquerade), destination NAT (`DNAT`, port
  forwarding), `PAT`,
- **the netfilter module** and `net.ipv4.ip_forward`.

The exam phrase “runtime vs. permanent” is a firewalld idea: `firewall-cmd`
changes are runtime-only until you pass `--permanent` and reload. nftables has
no such split because the ruleset is just a file you load.

## How netfilter fits together

The kernel packet-filtering framework is called **netfilter**. It exposes hooks
in the packet path:

```
ingress → prerouting → routing decision → forward → postrouting → egress
                                 ↘ input → local process
local process → output → postrouting
```

- **prerouting** — before the routing decision (DNAT happens here).
- **input** — packets destined for this host.
- **forward** — packets routed through this host.
- **output** — packets from local processes.
- **postrouting** — after the routing decision (SNAT/masquerade here).

`nftables` and `iptables` are two syntaxes over the same hooks. New systems
should use nftables; `iptables-nft` translates legacy commands.

## nftables

### Tables, chains, and rules

An nftables ruleset is nested: **table** → **chain** → **rules**.

```nft
#!/usr/sbin/nft -f
flush ruleset

table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        ct state established,related accept
        iif lo accept
        ip protocol icmp accept
        tcp dport 22 accept
        tcp dport { 80, 443 } accept
    }
    chain forward {
        type filter hook forward priority 0; policy drop;
    }
    chain output {
        type filter hook output priority 0; policy accept;
    }
}
```

- `inet` is a family that covers both IPv4 and IPv6; `ip`, `ip6`, `arp`,
  `bridge`, and `netdev` are the others.
- `hook input` binds the chain to a netfilter hook; `priority` sets its order.
- `policy drop` is the default verdict for packets that reach the end.
- `ct state established,related accept` makes the firewall **stateful**:
  replies to outbound connections are allowed without an explicit rule.
- `iif lo accept` allows loopback.
- `tcp dport { 80, 443 }` is a set; nftables supports anonymous sets natively.

### Managing the ruleset

```bash
sudo nft list ruleset
sudo nft -c -f /etc/nftables.conf      # syntax check only
sudo nft -f /etc/nftables.conf        # apply
sudo nft list tables
sudo nft list table inet filter
sudo nft add rule inet filter input tcp dport 8443 accept
sudo nft delete rule inet filter input handle 12
sudo nft flush ruleset
```

`-c` (check) is the safe way to validate a file before applying it; a typo in
a live ruleset can cut your SSH session. Persist the file by enabling
`nftables.service` and keeping the ruleset in `/etc/nftables.conf`.

### Stateful versus stateless

- **Stateful** — uses connection tracking (`ct state`) so only new connections
  are filtered. Efficient and simple; required for NAT and for sane rules.
- **Stateless** — filters every packet independently. Rare, used for very high
  throughput or simple routers.

Without `ct state established,related accept`, return traffic for outbound
connections is dropped and “the internet is broken”.

## NAT and forwarding

NAT rewrites addresses. It requires IP forwarding for traffic that passes
*through* the host:

```bash
sysctl net.ipv4.ip_forward
sudo sysctl -w net.ipv4.ip_forward=1
echo 'net.ipv4.ip_forward = 1' | sudo tee /etc/sysctl.d/99-forward.conf
sudo sysctl --system
```

With forwarding off, DNAT rules match but the packet is never routed onward —
the classic “port forward does nothing” incident.

### SNAT and masquerade

Source NAT changes the source address of outbound packets so replies come back
to the router:

```nft
table ip nat {
    chain postrouting {
        type nat hook postrouting priority 100; policy accept;
        ip saddr 10.0.0.0/24 oifname "eth0" masquerade
    }
}
```

`masquerade` uses the outgoing interface's address automatically — right for a
dynamic WAN address. `snat to 203.0.113.10` is explicit and slightly cheaper;
right for a static address.

### DNAT and port forwarding

Destination NAT rewrites the destination so an external port reaches an
internal service:

```nft
table ip nat {
    chain prerouting {
        type nat hook prerouting priority -100; policy accept;
        iifname "eth0" tcp dport 8080 dnat to 10.0.0.10:80
    }
}
```

This maps public `eth0:8080` to `10.0.0.10:80`. DNAT happens in prerouting,
before the routing decision, which is why it can change where a packet goes.
You still need a forward-chain rule that accepts the translated traffic.

`PAT` (port address translation) is NAT that also rewrites ports, which is what
masquerade does when many clients share one address.

## iptables (legacy syntax)

You will still meet it on older systems and in documentation. Read the chains
as the same hooks:

```bash
sudo iptables -L -n -v --line-numbers
sudo iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
sudo iptables -A INPUT -i lo -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT
sudo iptables -P INPUT DROP
sudo iptables -t nat -A POSTROUTING -s 10.0.0.0/24 -o eth0 -j MASQUERADE
sudo iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 8080 -j DNAT --to-destination 10.0.0.10:80
sudo iptables-save > /etc/iptables/rules.v4
sudo iptables-restore < /etc/iptables/rules.v4
```

`iptables -L` does not show rule numbers or NAT; use `iptables -t nat -L -n -v`
and `iptables-save`. `ipset` stores large address/port sets for efficient
matching (`ipset create blocklist hash:ip`).

## firewalld

firewalld is a higher-level manager over nftables (or iptables). Its central
idea is the **zone**: a set of rules applied to interfaces and sources.

```bash
sudo firewall-cmd --get-default-zone
sudo firewall-cmd --get-active-zones
sudo firewall-cmd --zone=public --list-all
sudo firewall-cmd --zone=public --add-service=https
sudo firewall-cmd --zone=public --add-port=8080/tcp
sudo firewall-cmd --zone=public --add-service=https --permanent
sudo firewall-cmd --reload
```

- **runtime** changes apply immediately and vanish on reload/reboot.
- **permanent** changes are written to `/etc/firewalld/zones/*.xml` and only
  apply after `--reload` or reboot.
- Do both, or do `--permanent` then `--reload`.

Common zones: `public` (untrusted, default), `internal`, `dmz`, `trusted`,
`drop`, `block`. A zone can be assigned to an interface or a source subnet.

### Rich rules

Rich rules express what services/ports cannot:

```bash
sudo firewall-cmd --permanent --zone=public --add-rich-rule='
  rule family="ipv4" source address="203.0.113.0/24" port port="22" protocol="tcp" accept'
sudo firewall-cmd --permanent --zone=public --add-rich-rule='
  rule family="ipv4" source address="198.51.100.7" drop'
sudo firewall-cmd --permanent --zone=public --add-masquerade
sudo firewall-cmd --permanent --zone=public --add-forward-port=port=8080:proto=tcp:toport=80:toaddr=10.0.0.10
sudo firewall-cmd --reload
```

`--add-masquerade` is SNAT. `--add-forward-port` is DNAT.

## ufw

ufw is Ubuntu's simple frontend. It is friendly but less expressive than
firewalld or nftables.

```bash
sudo ufw status verbose
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow from 10.0.0.0/24 to any port 5432 proto tcp
sudo ufw enable
sudo ufw delete allow 80/tcp
sudo ufw reload
```

`ufw status` prints lines like:

```
22/tcp                     ALLOW IN    Anywhere
5432/tcp                   ALLOW IN    10.0.0.0/24
```

The first is open to everyone; the second is restricted to a subnet. Prefer
restricted rules for databases and admin services.

## Choosing an approach

| Tool | Best for | Notes |
|---|---|---|
| nftables | modern servers, full control, routers | one syntax for IPv4/IPv6/NAT |
| firewalld | RHEL-family servers, dynamic zones | runtime/permanent split, D-Bus API |
| ufw | Ubuntu desktops and simple servers | opinionated, easy to read |
| iptables | legacy systems, existing automation | being replaced by nft |

Never run two frontends over the same backend without knowing which owns the
ruleset. firewalld and raw `nft` rules can conflict, and a `--reload` can wipe
manual rules.

## Reading a firewall like an auditor

For each listening service ask:

1. Is the port reachable from outside? `ss -tulpn` + firewall rules.
2. Is it restricted to the right source? A database open to `Anywhere` is a
   finding.
3. Is the default policy `drop`/`deny` on input and forward?
4. Is forwarding enabled only if this host is a router?
5. Is there a stateful `established,related` rule?
6. Are NAT rules explicit and minimal?

That is exactly what the mission asks `fw_audit.py` to report.

## Mission 13 — what you build

`etc/nftables.conf`, `etc/firewalld/zones/public.xml`, and
`fixtures/ufw_status.txt` describe three firewalls on one host.
`fw_audit.py --root .` must print:

- `nft_input_policy`, `nft_forward_policy`,
- `nft_open_ports` — sorted dports allowed,
- `dnat_targets` — `["8080->10.0.0.10:80", ...]`,
- `snat` — true when masquerade is present,
- `ip_forward` — `net.ipv4.ip_forward` as an integer,
- `firewalld_services`, `firewalld_ports`, `firewalld_masquerade`,
- `ufw_default_incoming`, `ufw_anywhere_ports`, `ufw_restricted_ports`,
- `issues` — concrete security problems.

Then write `nftables.hardened.conf` that:

- drops by default on both input and forward,
- accepts established traffic and loopback,
- allows only TCP 22 and 443 from new sources,
- keeps an explicit SNAT (masquerade) and the DNAT rule,
- never allows 3306.

The sandbox has no netfilter privileges, so the checker reads the file. Use
`nft -c -f` in the lesson if you have a host that allows it. Run
`python3 main.py verify 13`.

## Exam traps

- DNAT does nothing when `net.ipv4.ip_forward` is 0.
- `firewall-cmd` without `--permanent` is lost on reload.
- `--permanent` without `--reload` does not take effect now.
- A `drop` policy without `ct state established,related` breaks return traffic.
- `iptables -L` omits NAT rules and masks ports as names (`ssh` not `22`) unless
  you pass `-n`.
- Opening 3306 to the world is a classic breach.
- A host firewall does not replace network segmentation, but it is the last
  line of defence.
- Running ufw and firewalld simultaneously usually produces a ruleset nobody
  understands.

## Check yourself

1. Which netfilter hook does DNAT use, and which does SNAT use?
2. Why does a stateful firewall need `established,related`?
3. What is the difference between masquerade and explicit SNAT?
4. How do you make a firewalld change survive a reboot?
5. Which file does nftables read at boot, and how do you validate it first?
6. What is the difference between `@` and `@@` in rsyslog? (module 12) —
   answer it to link logging and firewall thinking about transports.
7. Why is a database port open to `Anywhere` a finding even behind NAT?

## Going deeper

- Build a router VM with two interfaces, enable forwarding, and masquerade a
  private subnet.
- Publish an internal web server with DNAT and confirm the forward chain
  accepts the translated traffic.
- Write the same policy in nftables, firewalld rich rules, and ufw, then
  compare readability.
- Use `nft monitor trace` (or `conntrack -L`) to watch a connection being
  accepted.
