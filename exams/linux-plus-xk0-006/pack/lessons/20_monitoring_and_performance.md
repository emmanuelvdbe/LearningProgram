# Module 20 — Monitoring, SLOs, and performance analysis

> **Exam objectives:** Linux+ 5.1 (summarize monitoring concepts and
> configurations) and 5.5 (given a scenario, analyze system properties and
> remediate performance issues).
> **Study time:** about 120 minutes, including the mission.
> **Mission:** `slo_report.py` — turn per-minute metrics into availability,
> error-budget, burn-rate, and latency verdicts, plus an alert rules file.

## What the exam expects

### Monitoring (5.1)

- service monitoring, health checks, log aggregation,
- **SLA**, **SLO**, **SLI**,
- data acquisition: SNMP (traps, MIBs), agent vs. agentless,
- webhooks,
- configurations: thresholds, alerts, events, notifications, logging.

### Performance (5.5)

- CPU, memory, swap, disk I/O, network,
- load average and run queue,
- `vmstat`, `iostat`, `sar`, `top`, `free`, `mpstat`, `pidstat`,
- latency, throughput, IOPS, queue depth,
- packet loss and jitter,
- capacity planning.

## SLI, SLO, SLA

| Term | Meaning | Example |
|---|---|---|
| **SLI** — service-level indicator | a measured number | 99.95% of requests succeeded this month |
| **SLO** — service-level objective | the internal target for an SLI | 99.9% availability per 30 days |
| **SLA** — service-level agreement | the contract, usually with penalties | 99.5% or service credits |

An SLO should be stricter than the SLA, so you notice trouble before you owe
credits. An SLI must be measurable from real telemetry, not a feeling.

### Error budget

If the SLO is 99.9%, the **error budget** is 0.1% of requests (or time):

```
allowed_errors   = total_requests * (1 - SLO)
remaining_budget = 100 - (errors / allowed_errors * 100)
burn_rate        = observed_error_rate / allowed_error_rate
```

- **burn rate 1** — you will exactly exhaust the budget over the window.
- **burn rate > 1** — you will exhaust it early; page someone.
- **burn rate 14.4** over one hour is a common fast-burn alert threshold.

The budget is a decision tool: if it is healthy, ship features; if it is
exhausted, freeze changes and fix reliability.

### Latency percentiles

Averages hide pain. Report **p50**, **p95**, **p99**:

- p95 = 95% of requests were faster than this value,
- a p99 far above p95 means a small set of very slow requests,
- a changing p99 often predicts an outage before availability drops.

**Nearest-rank percentile**: sort the values, take the element at index
`ceil(p/100 * N) - 1` (0-based). For 100 samples and p95, that is index 94.

## Data acquisition

### SNMP

- **agent** on the device, **manager** polls it,
- **OID** identifies a metric; **MIB** describes the OIDs,
- **traps** are unsolicited alerts from the agent,
- **polling** is scheduled pulls.

```bash
snmpwalk -v2c -c public 10.0.0.1 1.3.6.1.2.1.1
snmpget -v2c -c public 10.0.0.1 1.3.6.1.2.1.1.3.0
snmptranslate -Td 1.3.6.1.2.1.1.5.0
```

SNMPv1/v2c send the community string in clear text. Use SNMPv3 with
authentication and privacy for anything real.

### Agent versus agentless

- **Agent** — a daemon on the host (node_exporter, Telegraf, Datadog agent)
  exposes rich metrics and local checks. Needs installation and updates.
- **Agentless** — polling over SSH, SNMP, or an API. Simpler to deploy, less
  detail, and often slower.

### Health checks and log aggregation

- **Liveness** — is the process alive? Restart if not.
- **Readiness** — can it serve traffic? Remove from the load balancer if not.
- **Deep health check** — verifies dependencies (database, cache). Useful, but
  can turn a dependency blip into a restart storm.
- **Log aggregation** — ship logs to a central store (Loki, Elasticsearch,
  Splunk, a syslog host) so you can search across hosts and retain evidence.
- **Webhooks** — HTTP callbacks that let one system notify another (alert →
  chat, CI → deploy).

## Configurations: thresholds and alerts

- **Threshold** — a static limit (`disk > 90%`, `p95 > 300ms`).
- **Alert** — a rule that fires when a condition holds for a duration.
- **Event** — a single occurrence (deploy, restart, config change).
- **Notification** — where the alert goes (email, chat, pager).
- **Severity** — page vs. ticket vs. dashboard.

Good alerts are:

- **symptom-based** (users are failing) rather than cause-based (CPU is high),
- **actionable** — there is a runbook,
- **deduplicated** and grouped,
- **tied to an SLO** where possible,
- **reviewed** after every incident to remove noise.

Alert fatigue is a security and reliability problem: if everything pages,
nothing pages.

Example rules file (Prometheus-style shape):

```yaml
groups:
  - name: slo
    rules:
      - alert: AvailabilityBelowSLO
        expr: sli:availability:ratio < 0.999
        for: 10m
      - alert: P95LatencyHigh
        expr: sli:latency_p95_ms > 300
        for: 5m
      - alert: ErrorBudgetBurn
        expr: slo:burn_rate > 14.4
        for: 1h
```

## The performance toolbox

### CPU and load

```bash
uptime
top -b -n1 | head -15
mpstat -P ALL 1 5
pidstat 1 5
vmstat 1 5
```

**Load average** counts runnable plus uninterruptible (`D`) tasks. On a
4-vCPU host, a load of 4 is saturated; a load of 8 with low CPU usage usually
means I/O wait, not CPU. Always read load together with `%wa` and the run
queue.

`vmstat` columns:

```
procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----
 r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st
```

- `r` runnable, `b` blocked,
- `si`/`so` swap in/out — non-zero sustained swapping is a problem,
- `bi`/`bo` blocks in/out,
- `us`/`sy`/`id`/`wa`/`st` CPU breakdown; `st` is steal (noisy neighbour in a
  VM).

### Memory and swap

```bash
free -h
cat /proc/meminfo | head
vmstat 1 5
ps -eo pid,rss,%mem,cmd --sort=-rss | head
smem -tk
```

Linux uses free RAM for cache; “free” being low is normal. Look at
`available`. Thrashing (constant swap in/out) is the real problem, and the OOM
killer (`dmesg | grep -i oom`) is the last resort.

### Disk and filesystems

```bash
df -h
df -i
iostat -xz 1 5
iotop -o
du -xhd1 /var | sort -h
```

`iostat -x` columns worth reading:

- `r/s`, `w/s` — IOPS,
- `rkB/s`, `wkB/s` — throughput,
- `await` — average latency per request (ms),
- `aqu-sz` — queue depth,
- `%util` — device busy percentage.

High `await` with low throughput suggests a failing or overloaded device. High
`%util` with a deep queue means saturation.

### Network

```bash
ip -s link
ss -s
sar -n DEV 1 5
iperf3 -c host
mtr --report host
tcpdump -i any -nn -c 50
```

Latency is round-trip time; jitter is its variation; packet loss is dropped
packets. For real-time traffic, jitter and loss matter more than average
latency. `iperf3` measures throughput; `mtr` shows where loss starts.

### Historical data with `sar`

```bash
sar -u 1 5          # CPU
sar -r 1 5          # memory
sar -b 1 5          # I/O
sar -n DEV 1 5      # network
sar -f /var/log/sa/sa14   # a previous day
```

`sysstat` must be installed and enabled. Historical data is how you answer
“was it slow yesterday at 14:00?” after the fact.

## A performance investigation method

1. **Define the symptom** — what is slow, for whom, since when?
2. **Check the SLO/SLI** — availability, latency, error rate.
3. **Narrow the resource** — CPU (`us`/`sy`), memory/swap, disk (`wa`,
   `await`), network (loss, retransmits).
4. **Find the consumer** — `top`, `pidstat`, `iotop`, `ss`, `lsof`.
5. **Confirm with a second tool** — do not trust a single sample.
6. **Change one thing** and measure again.
7. **Record** the finding and the fix in the runbook.

Bottleneck order of suspicion on a server: disk I/O and memory pressure first,
then CPU, then network, then application-level inefficiency. Most “CPU
problems” are actually waiting on storage or a lock.

## Capacity planning

- Track growth in requests, storage, and connections.
- Know the headroom: at current growth, when do you hit the limit?
- Test the limit with a load test, not a guess.
- Scale vertically (bigger host) or horizontally (more hosts) based on where
  the bottleneck is.
- Keep a safety margin for failover: if one of three nodes dies, the other two
  must absorb the load.

## Mission 20 — what you build

`fixtures/metrics.csv` has one row per minute with `requests`, `errors`, and
`latency_ms`.

Build `slo_report.py`:

```
--metrics fixtures/metrics.csv --target 99.9 --latency-ms 300
```

Print one JSON object with:

- `total_requests`, `total_errors`,
- `availability_percent = (requests - errors) / requests * 100`,
- `error_budget_percent = 100 - target`,
- `budget_remaining_percent = max(0, 100 - errors / allowed_errors * 100)`,
- `burn_rate = observed_error_rate / allowed_error_rate`,
- `p95_latency_ms` — nearest-rank 95th percentile,
- `latency_breaches` — count of values strictly above `--latency-ms`,
- `sli = availability_percent`,
- `slo_met = availability >= target`,
- `alerts` — subset of `AvailabilityBelowSLO`, `P95LatencyHigh`,
  `ErrorBudgetBurn`,
- `recommendations` — concrete next actions.

Then write `monitoring/alerts.yaml` with three rules named
`AvailabilityBelowSLO`, `P95LatencyHigh`, and `ErrorBudgetBurn`, using the 99.9
target, the 300 ms limit, and `burn_rate`. Run `python3 main.py verify 20`.

## Exam traps

- Low `free` memory is normal; look at `available` and swap activity.
- High load is not necessarily high CPU; check `D` state and `%wa`.
- An average latency hides the p99 that users feel.
- A threshold alert without a duration flaps on every spike.
- An SLO equal to the SLA leaves no room to react.
- `%util` near 100% on a modern SSD does not always mean saturation; read
  `await` and queue depth too.
- SNMPv2c community strings are clear text.
- A health check that restarts on dependency failure can cause an outage loop.
- Percentiles cannot be averaged across hosts; aggregate the raw data or use
  histograms.

## Check yourself

1. Define SLI, SLO, and SLA, and explain why the SLO should be stricter.
2. How do you compute an error budget for a 99.9% SLO?
3. What does a burn rate of 2 mean?
4. How is a nearest-rank p95 computed?
5. Which `vmstat` columns indicate swapping, and why is it bad?
6. What does `iostat` `await` measure?
7. Why is symptom-based alerting better than cause-based alerting?
8. Which `sar` flags show CPU, memory, and network history?

## Going deeper

- Generate synthetic metrics, compute SLOs, and plot the error budget over 30
  days.
- Break a test service (CPU, memory, disk I/O) and identify the bottleneck with
  `vmstat`, `iostat`, and `pidstat`.
- Write alert rules with `for:` durations and explain how each avoids flapping.
- Compare agent-based and agentless monitoring on the same host.
