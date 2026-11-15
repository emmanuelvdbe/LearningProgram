# Module 16 — Automation, IaC, CI/CD, and orchestration

> **Exam objective:** Linux+ 4.1 — Summarize automation and orchestration
> concepts.
> **Study time:** about 110 minutes, including the mission.
> **Mission:** `iac_audit.py` — audit an Ansible playbook, an inventory, and a
> Kubernetes Deployment, then write production-shaped replacements.

## What the exam expects

- **Configuration management / IaC:** Ansible, Puppet, Chef, Salt; declarative
  versus imperative; idempotence.
- **Provisioning:** Kickstart, cloud-init, preseed, Terraform/OpenTofu.
- **CI/CD:** pipelines, build/test/deploy stages, artifacts, GitOps.
- **Orchestration:** Kubernetes objects, Compose, Swarm.
- **Infrastructure patterns:** immutable infrastructure, golden images,
  blue/green, canary, rolling updates.
- **Secrets and state:** vaults, encrypted variables, remote state.

## Declarative, imperative, and idempotent

- **Imperative** — a sequence of commands: `apt install nginx`,
  `systemctl start nginx`.
- **Declarative** — the desired end state: “nginx is installed and running”.
  The tool works out the steps.
- **Idempotent** — running it twice has the same effect as running it once.

IaC tools are declarative and idempotent. That is what makes them safe to run
repeatedly and what a shell script usually is not:

```bash
# not idempotent: fails the second time
useradd alice

# idempotent
id alice >/dev/null 2>&1 || useradd alice
```

## Ansible

Agentless: it connects over SSH and runs modules. The pieces:

- **inventory** — hosts and groups,
- **playbook** — a list of plays,
- **play** — maps hosts to tasks,
- **task** — one module invocation,
- **module** — the unit of work (`apt`, `copy`, `template`, `service`,
  `user`, `file`, `command`),
- **handler** — a task triggered by `notify`, run once at the end,
- **role** — a reusable bundle of tasks, handlers, templates, defaults, and
  vars,
- **variable precedence** — defaults < group_vars < host_vars < play vars <
  task vars < extra vars.

```yaml
# site.yml
- name: Configure web servers
  hosts: web
  become: true
  vars:
    app_image: nginx:1.27.3
  tasks:
    - name: Install nginx
      apt:
        name: nginx
        state: present
        update_cache: true

    - name: Deploy site configuration
      template:
        src: templates/site.conf.j2
        dest: /etc/nginx/conf.d/site.conf
        mode: "0644"
      notify: Reload nginx

    - name: Ensure nginx is running
      service:
        name: nginx
        state: started
        enabled: true

  handlers:
    - name: Reload nginx
      service:
        name: nginx
        state: reloaded
```

```ini
# inventory.ini
[web]
web01 ansible_host=10.0.0.11
web02 ansible_host=10.0.0.12

[db]
db01 ansible_host=10.0.0.21

[all:vars]
ansible_user=deploy
```

```bash
ansible-playbook -i inventory.ini site.yml --check   # dry run
ansible-playbook -i inventory.ini site.yml --diff
ansible all -i inventory.ini -m ping
ansible-inventory -i inventory.ini --list
```

`--check` is the dry run. `--diff` shows file changes. Both are how you review
automation before it touches production.

Audit questions for a playbook:

1. Which hosts does each play target?
2. Which modules are used? (`command`/`shell` are imperative escapes — prefer
   native modules.)
3. Does it use `become: true`? (privilege escalation — intended?)
4. Are there handlers, and are they notified?
5. Are variables defined, and are secrets stored in plain text?

## Puppet, Chef, Salt

| Tool | Model | Notes |
|---|---|---|
| Puppet | agent + master, declarative manifests | strong reporting, mature |
| Chef | agent, Ruby DSL recipes | very flexible, more code |
| Salt | agent or agentless, YAML | fast, event-driven |
| Ansible | agentless over SSH, YAML | lowest barrier to entry |

All four express desired state and converge the host toward it. The exam only
needs the model and the vocabulary, not deep syntax for each.

## Provisioning: Kickstart, cloud-init, preseed

Unattended installation is how fleets are built (module 1 covered PXE):

- **Kickstart** (RPM family) — a file answering the installer's questions:
  partitioning, packages, network, users, post-install scripts.
- **preseed** (Debian family) — the equivalent for the Debian installer.
- **cloud-init** — first-boot configuration for cloud images: hostname, users,
  SSH keys, packages, `runcmd`, `write_files`. It reads user-data and metadata
  from the cloud provider.

```yaml
#cloud-config
hostname: web01
users:
  - name: deploy
    ssh_authorized_keys:
      - ssh-ed25519 AAAA...
package_update: true
packages:
  - nginx
runcmd:
  - systemctl enable --now nginx
```

```bash
cloud-init status --long
cat /var/lib/cloud/instance/user-data.txt
```

## Terraform and OpenTofu

Terraform (and its open-source fork OpenTofu) provision infrastructure:
networks, instances, buckets, DNS. They are declarative and keep **state** so
they know what exists.

```hcl
resource "aws_instance" "web" {
  ami           = data.aws_ami.almalinux.id
  instance_type = "t3.small"
  tags = {
    Name = "web01"
  }
}
```

```bash
terraform init
terraform plan
terraform apply
terraform destroy
```

State contains secrets and must be stored remotely with locking and
encryption. `plan` is the review step; never `apply` an unreviewed plan.

## CI/CD and GitOps

A pipeline turns a commit into a deployed artifact:

```
commit → build → unit tests → scan (SAST/deps/image) → package → deploy to staging
       → integration tests → approval → deploy to production → verify
```

- **CI** — continuous integration: build and test every change.
- **CD** — continuous delivery (always releasable) or deployment (automatic).
- **Artifact** — the built image, package, or binary, stored in a registry.
- **Pipeline as code** — `.gitlab-ci.yml`, GitHub Actions workflows,
  `Jenkinsfile`.
- **GitOps** — Git is the source of truth; an agent (Argo CD, Flux) reconciles
  the cluster to the repository.
- **Secrets in CI** — use masked CI variables or a vault, never commit them.

```yaml
# .github/workflows/ci.yml (shape, not a full example)
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python3 -m unittest discover -s tests
```

## Kubernetes objects

Kubernetes is a declarative orchestrator. You submit objects; controllers
reconcile the actual state toward the desired state.

| Object | Purpose |
|---|---|
| `Pod` | one or more containers scheduled together |
| `Deployment` | manages ReplicaSets and rolling updates for stateless apps |
| `StatefulSet` | stable identity and storage for stateful apps |
| `DaemonSet` | one pod per node (agents, log shippers) |
| `Service` | stable virtual IP / DNS for a set of pods |
| `Ingress` | HTTP routing from outside the cluster |
| `ConfigMap` | non-secret configuration |
| `Secret` | sensitive configuration (base64, not encryption by itself) |
| `PersistentVolumeClaim` | request for storage |
| `Namespace` | logical isolation |
| `Job` / `CronJob` | run-to-completion / scheduled work |

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 2
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: web
          image: nginx:1.27.3
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 256Mi
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
          securityContext:
            privileged: false
            readOnlyRootFilesystem: true
```

Review checklist for a workload:

- image pinned (tag or digest), not `latest`,
- `replicas` set intentionally,
- resource **requests and limits** present,
- readiness and liveness probes present,
- `runAsNonRoot: true`, `privileged: false`, `readOnlyRootFilesystem: true`,
- secrets from a `Secret`, not inline env,
- a `Service` selects the pods,
- `NetworkPolicy` restricts traffic where supported.

```bash
kubectl apply -f deploy/k8s.yaml
kubectl get pods,deploy,svc
kubectl describe deploy web
kubectl rollout status deploy/web
kubectl rollout undo deploy/web
kubectl logs deploy/web
kubectl exec -it pod/web-xxxx -- /bin/sh
```

## Compose as orchestration

For a single host, Compose (module 11) is enough: services, volumes, networks,
healthchecks, restart policies. The mental model is the same as Kubernetes,
one scale smaller.

## Immutable infrastructure and rollout patterns

- **Immutable infrastructure** — never patch a running server; build a new
  image, deploy it, destroy the old one. Reduces drift.
- **Golden image** — a patched, hardened base image used for every clone.
- **Rolling update** — replace instances gradually; requires health checks.
- **Blue/green** — run two identical environments; switch traffic after
  verification; instant rollback.
- **Canary** — send a small percentage of traffic to the new version, watch
  metrics, then expand.

## Secrets and state in automation

- Never store secrets in Git, playbooks, images, or CI logs.
- Use Ansible Vault, SOPS, HashiCorp Vault, Kubernetes Secrets plus encryption
  at rest, or a cloud secret manager.
- Restrict who can read state files; they often contain secrets.
- Rotate credentials on a schedule and after any suspected exposure.

## Mission 16 — what you build

`fixtures/` holds a two-play Ansible playbook, an inventory, and a Kubernetes
Deployment. `iac_audit.py --root .` must print:

- `inventory_groups` — `{"web": ["web01", "web02"], "db": ["db01"]}`,
- `play_hosts` — the `hosts:` value for each play, in order,
- `task_modules` — modules used by tasks (`apt`, `template`, `service`, …),
- `uses_become`, `has_handlers`, `handler_notify`, `uses_vars` — booleans,
- `k8s` — `{kind, name, image, replicas, privileged, has_limits, has_liveness,
  has_readiness, read_only_root, non_root}`,
- `issues` — concrete problems in the Kubernetes manifest.

You do not need PyYAML; a careful line parser is enough for these fixtures.

Then write production-shaped versions:

- `deploy/site.yml` — one `become: true` play for the `web` group, a `vars:`
  block with `app_image: nginx:1.27.3`, a task that notifies a handler, and a
  `handlers:` block that reloads nginx,
- `deploy/k8s.yaml` — a Deployment named `web` using image `nginx:1.27.3`, with
  resource limits and requests, `readinessProbe`, `livenessProbe`,
  `runAsNonRoot: true`, `privileged: false`, and
  `readOnlyRootFilesystem: true`.

Run `python3 main.py verify 16`.

## Exam traps

- Ansible is agentless; Puppet and Chef normally use agents.
- `command`/`shell` tasks are not idempotent by default.
- Handlers run once at the end, only if notified.
- `become: true` is privilege escalation; review it.
- Terraform state is sensitive and must be remote and locked.
- A Kubernetes `Secret` is base64, not encryption.
- `latest` images make rollouts non-reproducible.
- A liveness probe that checks a dependency can restart a healthy app when the
  dependency is down.
- GitOps reconciles; it does not replace code review.

## Check yourself

1. What makes a task idempotent, and why does `shell:` often fail that test?
2. What is the difference between a task and a handler?
3. Which Ansible file defines host groups?
4. What does `terraform plan` do before `apply`?
5. Which Kubernetes object provides rolling updates for a stateless app?
6. Why is a `readinessProbe` different from a `livenessProbe`?
7. What is the difference between blue/green and canary deployment?
8. Where should secrets live in a CI/CD pipeline?

## Going deeper

- Convert a shell provisioning script into an idempotent Ansible playbook and
  run it twice.
- Build a cloud-init image and inspect `/var/log/cloud-init-output.log`.
- Add probes and resource limits to a Deployment and watch a rollout with
  `kubectl rollout status`.
- Set up a minimal GitOps loop with Argo CD in a local cluster if you have one.
