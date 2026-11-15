# Module 11 — Containers: images, volumes, and networks

> **Exam objective:** Linux+ 2.6 — Given a scenario, configure and manage
> containers.
> **Study time:** about 110 minutes, including the mission.
> **Mission:** write a hardened `Dockerfile`, a `compose.yaml`, and a
> `container_audit.py` linter that flags the deliberately bad fixtures.

## What the exam expects

- **Runtime stack:** Docker, Podman, containerd, runC, and the OCI image and
  runtime specifications.
- **Lifecycle:** build, run, stop, remove, logs, exec, inspect.
- **Images:** Dockerfile instructions, layers, caching, tags, registries,
  digests, multi-stage builds.
- **Storage:** named volumes, bind mounts, tmpfs, image layers.
- **Networking:** bridge, host, none, overlay; port publishing; DNS between
  containers.
- **Hardening:** non-root users, read-only root filesystem, dropped
  capabilities, no secrets in images, resource limits, healthchecks.

This objective overlaps 3.3 (hardening) and 4.1 (orchestration). The mission
is deliberately a security review, because that is how the exam frames it.

## The runtime stack

```
docker CLI / podman CLI / kubectl
        │  (API)
containerd  or  CRI-O            ← image pull, container lifecycle
        │  (OCI runtime spec)
runC (or crun)                   ← creates namespaces + cgroups, execs process
        │
Linux kernel                     ← namespaces (isolation), cgroups (limits),
                                   capabilities, seccomp, SELinux/AppArmor
```

- **Namespaces** isolate what a process can *see*: PID, mount, network, IPC,
  UTS (hostname), user, cgroup, time.
- **cgroups** limit what a process can *use*: CPU, memory, block I/O, PIDs.
- **Capabilities** split root's power into small pieces (`CAP_NET_BIND_SERVICE`,
  `CAP_SYS_ADMIN`, …).
- **seccomp** filters syscalls; **SELinux/AppArmor** add mandatory access
  control.

A container is not a virtual machine. It is a normal process with a restricted
view of the system and shared kernel. That is why containers start in
milliseconds and why a kernel exploit escapes all of them.

### Docker versus Podman

| | Docker | Podman |
|---|---|---|
| Daemon | `dockerd` (root) | daemonless, fork/exec |
| Rootless | optional | first-class |
| Compose | `docker compose` | `podman compose` / `podman-compose` |
| Kubernetes YAML | no | `podman generate kube` |
| CLI | `docker` | drop-in `podman` alias |

On the exam, know that Podman is daemonless and rootless-friendly, and that
both build OCI images that run under either runtime.

## Container lifecycle

```bash
docker pull nginx:1.27.3
docker images
docker run -d --name web -p 8080:80 nginx:1.27.3
docker ps
docker ps -a
docker logs -f web
docker exec -it web /bin/sh
docker inspect web
docker stats
docker stop web
docker rm web
docker rmi nginx:1.27.3
docker system df
docker system prune -a
```

`docker run` flags worth memorising:

| Flag | Effect |
|---|---|
| `-d` | detached |
| `-it` | interactive TTY |
| `--name` | container name |
| `-p host:container` | publish a port |
| `-v name:/path` | named volume |
| `-v /host:/path` | bind mount |
| `--rm` | delete on exit |
| `-e KEY=value` | environment variable |
| `--network` | attach to a network |
| `--restart` | restart policy |
| `--read-only` | read-only root filesystem |
| `--cap-drop ALL` | drop capabilities |
| `--user 1000:1000` | run as a non-root user |
| `--memory`, `--cpus` | resource limits |
| `--health-cmd` | healthcheck |

## Dockerfile instructions

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --no-create-home app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

USER app
EXPOSE 8080
CMD ["python", "app.py"]
```

Instruction reference:

| Instruction | Purpose |
|---|---|
| `FROM` | base image; pin a version or digest, never `latest` |
| `WORKDIR` | set the working directory for later instructions |
| `COPY` / `ADD` | copy files (`ADD` also unpacks archives and fetches URLs) |
| `RUN` | execute a build step; each `RUN` is a layer |
| `ENV` / `ARG` | environment at runtime / build time |
| `USER` | drop to a non-root user |
| `EXPOSE` | document the port (does not publish it) |
| `VOLUME` | declare a data directory |
| `ENTRYPOINT` / `CMD` | fixed executable / default arguments |
| `HEALTHCHECK` | command the runtime uses to test liveness |
| `LABEL` | metadata (source, version, maintainer) |

### Layers and caching

Each instruction creates a layer. Layers are cached: if the inputs to an
instruction do not change, the cached layer is reused. Put the slow, rarely
changing steps first:

```dockerfile
COPY requirements.txt .          # changes rarely
RUN pip install -r requirements.txt
COPY . .                         # changes often
```

A `.dockerignore` keeps `.git`, `node_modules`, `.venv`, and secrets out of the
build context — both for speed and to avoid leaking them into layers.

### Tags, digests, and registries

```bash
docker build -t registry.example/app:1.4.2 .
docker tag registry.example/app:1.4.2 registry.example/app:latest
docker push registry.example/app:1.4.2
docker pull registry.example/app@sha256:...
docker image inspect --format '{{.RepoDigests}}' registry.example/app:1.4.2
```

`latest` is a moving tag, not a version. Production deployments should use an
immutable tag or, better, a digest. A registry is any OCI-compatible store:
Docker Hub, GHCR, Quay, Harbor, or an internal registry.

### Multi-stage builds

```dockerfile
FROM golang:1.23 AS build
WORKDIR /src
COPY . .
RUN CGO_ENABLED=0 go build -o /out/app ./cmd/app

FROM gcr.io/distroless/static
COPY --from=build /out/app /app
USER 65532:65532
ENTRYPOINT ["/app"]
```

The final image contains only the binary and its runtime, not the compiler or
source. Smaller image means smaller attack surface and faster pulls.

## Volumes and mounts

| Type | Example | Lifetime |
|---|---|---|
| named volume | `-v appdata:/data` | managed by the runtime, survives container deletion |
| bind mount | `-v /srv/app:/app` | host path, full host permissions |
| tmpfs | `--tmpfs /tmp` | RAM, gone on stop |
| image layer | files baked into the image | read-only at runtime |

```bash
docker volume create appdata
docker volume ls
docker volume inspect appdata
docker volume rm appdata
```

Use volumes for persistent data (databases), bind mounts for development and
configuration, tmpfs for scratch. Never store data only in the container's
writable layer — it disappears with the container and is invisible to backups.

## Networking

```bash
docker network ls
docker network create frontend
docker network inspect frontend
docker run -d --network frontend --name api app:1.0
docker run -d --network frontend --name web -p 8080:80 nginx:1.27.3
```

| Driver | Behaviour |
|---|---|
| `bridge` | private network, NAT to the host, port publishing required |
| `host` | shares the host network namespace; no isolation |
| `none` | no networking |
| `overlay` | multi-host (Swarm) |
| `macvlan` | container gets a MAC on the physical LAN |

On a user-defined bridge (not the default `bridge`), containers resolve each
other by name — `web` can reach `api:8000`. Publishing a port (`-p`) is
required only for access from outside the container network.

Port mapping `-p 8080:80` binds the host's 8080 to container 80. `-p
127.0.0.1:8080:80` restricts it to localhost, which is the correct choice for
an admin interface that should not be public.

## Compose

`compose.yaml` describes a multi-container application:

```yaml
services:
  web:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - appdata:/data
    environment:
      APP_MODE: production
    read_only: true
    cap_drop: [ALL]
    security_opt:
      - no-new-privileges:true
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')"]
      interval: 30s
      timeout: 3s
      retries: 3
    networks:
      - frontend

volumes:
  appdata:

networks:
  frontend:
    driver: bridge
```

```bash
docker compose up -d
docker compose ps
docker compose logs -f web
docker compose exec web /bin/sh
docker compose down
docker compose down -v          # also delete volumes (destructive)
```

Compose is the standard for local development and small deployments; Kubernetes
(module 16) is the standard for orchestration at scale.

## Hardening a container

1. **Pin the base image** — `python:3.12-slim`, not `python:latest`, ideally by
   digest.
2. **Run as non-root** — `USER app` and no `sudo` in the image.
3. **Read-only root filesystem** — `read_only: true` / `--read-only`; mount
   writable volumes where needed.
4. **Drop capabilities** — `cap_drop: [ALL]`, add back only what is required.
5. **No new privileges** — `no-new-privileges:true` blocks setuid escalation.
6. **No secrets in the image** — not in `ENV`, not in `RUN`, not in a copied
   file. Use a secret manager or mounted secret, and remember that layers are
   readable history.
7. **Resource limits** — `--memory`, `--cpus`, `pids_limit` in Compose.
8. **Healthcheck** — so the orchestrator can restart an unhealthy container.
9. **Minimal base** — distroless or slim images have fewer packages to patch.
10. **Scan the image** — `docker scout cves`, `trivy image`, `grype`.

`--privileged` disables almost every isolation mechanism. Treat it as a red
flag in a review: it grants all capabilities, all devices, and usually access
to the host. The same applies to mounting `/var/run/docker.sock` — a container
with the socket effectively has root on the host.

## Logging and inspection

```bash
docker logs --tail 100 web
docker inspect --format '{{.State.Health.Status}}' web
docker top web
docker stats --no-stream
docker diff web
docker cp web:/app/config.yaml ./config.yaml
```

`docker diff` shows files changed in the container's writable layer compared to
the image — useful for debugging, and a reminder that state in that layer is
not managed.

## Mission 11 — what you build

The folder contains `Dockerfile.bad`, `compose.bad.yaml`, and `app.py`.

1. **`Dockerfile`** for a Python 3.12 web app:
   - pinned `python:3.12-slim` base (never `latest`),
   - `WORKDIR /app`, copy `app.py`,
   - create and switch to a non-root `app` user,
   - `EXPOSE 8080` and a `CMD`,
   - no API keys, passwords, or tokens in `ENV`.
2. **`compose.yaml`** with a `web` service that:
   - builds the image and publishes 8080,
   - mounts the named volume `appdata` at `/data`,
   - uses `read_only: true`, `cap_drop: [ALL]`, and a healthcheck,
   - joins the `frontend` network.
3. **`container_audit.py --dockerfile FILE --compose FILE`** printing JSON
   with `base_image`, `pinned`, `non_root`, `has_cmd`, `secrets`, `services`,
   `volumes`, and `networks`. It must flag the bad fixtures correctly.

Run `python3 main.py verify 11`.

## Exam traps

- `EXPOSE` documents a port; it does not publish it. `-p` does.
- `latest` is not “the newest known good”; it is whatever was pushed last.
- A container with `--privileged` is effectively root on the host.
- Secrets in `ENV` or `RUN` are visible in `docker history` and the image.
- Data in a container's writable layer is lost when the container is removed.
- `docker compose down -v` deletes named volumes.
- The default bridge network has no DNS between containers; a user-defined
  network does.
- Containers share the host kernel; they are not a security boundary against a
  kernel exploit.

## Check yourself

1. Which kernel features provide isolation and which provide limits?
2. What is the difference between Docker and Podman?
3. Why does `COPY requirements.txt` come before `COPY . .`?
4. What does `-p 127.0.0.1:8080:80` do differently from `-p 8080:80`?
5. Which flags would you add to a Compose service to drop privileges and make
   the root filesystem read-only?
6. How do you find the digest of an image you are deploying?
7. Why is `--privileged` dangerous?

## Going deeper

- Build the same app with a single-stage and a multi-stage Dockerfile and
  compare `docker images` sizes.
- Run a container with `--read-only` and observe which paths need volumes.
- Scan an image with `trivy image` (if available) and read the CVE report.
- Create two containers on a user-defined bridge and prove name resolution
  works, then repeat on the default bridge.
