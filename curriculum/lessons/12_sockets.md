# Module 12 — Sockets: build a TCP port checker

## Why this matters for Linux+

“Is the service listening?” is one of the most common Linux+ troubleshooting
questions. `ss -tuln` shows local sockets; `nc -zv host port` tests reachability;
monitoring systems do the same thing from Python.

This module builds a TCP port checker. Along the way you learn how clients and
servers connect, why timeouts are mandatory, and why context managers matter
for file descriptors.

## TCP in one paragraph

TCP is a connection-oriented protocol. A server:

1. creates a socket,
2. binds it to an address and port,
3. calls `listen()` to accept connections.

A client calls `connect()` with the server’s address and port. The kernel
performs a three-way handshake. If the port is closed, the connection is
refused immediately (or times out if a firewall drops packets). Once connected,
both sides can send and receive bytes until one closes.

For a port check, you only need the handshake. You do not need to send data.

## The client API

```python
import socket

try:
    with socket.create_connection(("127.0.0.1", 22), timeout=1.0):
        print("open")
except OSError as exc:
    print("closed or unreachable:", exc)
```

Why `create_connection` instead of raw `socket()`?

- it resolves hostnames,
- it tries IPv4 and IPv6 addresses,
- it applies the timeout to the connect,
- it raises `OSError` on failure.

The `with` block closes the socket immediately. Leaving sockets open leaks file
descriptors; a long-running monitor can exhaust them.

## Timeouts are not optional

Without a timeout, a connect to a filtered port can hang for minutes. Use a
small default (0.5–2 seconds) and make it configurable:

```python
parser.add_argument("--timeout", type=float, default=1.0)
```

`timeout` applies to the connect and to subsequent blocking operations on that
socket. If the peer accepts but never responds, later reads can still block;
set timeouts on those operations too.

## Errors you will see

| Exception | Meaning |
|---|---|
| `ConnectionRefusedError` | nothing listening on that port |
| `TimeoutError` / `socket.timeout` | no response within the timeout |
| `socket.gaierror` | hostname resolution failed |
| `OSError` | generic network failure |

All of these are subclasses of `OSError` (in modern Python), so a single
`except OSError` is enough for a checker. If you need to distinguish, catch the
specific ones first.

```python
try:
    with socket.create_connection((host, port), timeout=timeout):
        return True
except ConnectionRefusedError:
    return False
except TimeoutError:
    return False
except OSError:
    return False
```

## Checking several ports

Keep the output machine-friendly and stable:

```text
OPEN 22
CLOSED 8080
```

Exit 0 only if every port is open; otherwise exit 1. Why? Because a monitoring
script can do:

```bash
if python3 portcheck.py db 5432; then
    echo "database reachable"
fi
```

Print one line per port in argument order. Do not stop at the first closed
port unless the interface says `--first-failure`.

## Writing a test server

For local experiments, bind to port 0. The kernel chooses a free port:

```python
import socket

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("127.0.0.1", 0))
server.listen(5)
port = server.getsockname()[1]
print("listening on", port)
```

The verifier does exactly this, then runs your script against the open port and
a closed one.

## Listening sockets in `ss`

```bash
ss -tuln
```

- `-t` TCP, `-u` UDP, `-l` listening, `-n` numeric.
- LISTEN means a TCP server is waiting.
- UNCONN means a UDP socket is bound but has no connection (normal for UDP).

A port check with TCP cannot verify a UDP service. UDP has no handshake.
For UDP monitoring you must send a protocol-specific request and wait for a
reply. Say what you measured; “port open” is meaningless for UDP without a
payload.

## Firewalls and false negatives

A closed port often sends TCP RST → `ConnectionRefusedError` quickly.
A firewall may **drop** packets → timeout. Both mean “not reachable from here”,
but the causes differ. Your report should not claim the service is down; it
should say the port is not reachable from this host.

## Guided walkthrough

```bash
cd "$(python3 main.py doctor | sed -n 's/^  \[ok\] Lab: //p' | head -1)" 2>/dev/null || true
mkdir -p 12_portcheck
cd 12_portcheck
```

Start a temporary listener in one terminal:

```bash
python3 -m http.server 8000 --bind 127.0.0.1
```

In another terminal:

```bash
ss -tuln | grep 8000
nc -zv 127.0.0.1 8000   # if netcat is installed
python3 - <<'PY'
import socket
for port in (8000, 8001):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            print(port, "OPEN")
    except OSError as exc:
        print(port, "CLOSED", type(exc).__name__)
PY
```

Then implement `portcheck.py`:

```bash
python3 portcheck.py 127.0.0.1 8000 8001; echo "status=$?"
python3 portcheck.py 127.0.0.1 8000; echo "status=$?"
```

Verify:

```bash
python3 main.py verify 12
```

The verifier opens a local port and closes another, so you do not need an
external network connection.

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| No timeout | hangs on filtered ports | set `--timeout` |
| Forgetting `with` | leaked sockets | context manager |
| Catching only `ConnectionRefusedError` | timeout crashes | catch `OSError` |
| Reporting “service down” from a port check | wrong diagnosis | say “not reachable” |
| Checking UDP with a TCP connect | always fails | protocol-specific probe |
| Stopping at the first failure | incomplete report | check every port |
| Exiting 0 with a closed port | monitoring misses outages | non-zero if any closed |
| `socket.create_connection` with a string port | `TypeError` | convert with `int` |

## Mission checklist

- [ ] `12_portcheck/portcheck.py` exists.
- [ ] Accepts host, one or more ports, `--timeout`.
- [ ] Prints `OPEN <port>` / `CLOSED <port>` per port.
- [ ] Exit 0 if all open, 1 otherwise.
- [ ] Invalid port exits 2 via argparse.
- [ ] Unreachable address becomes CLOSED without hanging.

Then run:

```bash
python3 main.py verify 12
```

## Extra practice

1. Add `--first-failure` to stop early.
2. Add concurrency with `ThreadPoolExecutor` for many ports.
3. Measure connect latency per port and report milliseconds.
4. Resolve the host once and show both IPv4 and IPv6 results.
5. Write a UDP probe for DNS (port 53) or NTP (port 123).
6. Compare your results with `ss -tln` on the same host.
