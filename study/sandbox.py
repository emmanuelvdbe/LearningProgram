"""Sandboxed command execution for the graphical study lab.

Every terminal session in the GUI is wrapped in a bubblewrap_ user namespace.
The host filesystem is not writable from inside the sandbox, the project and
save files are not mounted, and the session only sees:

* read-only ``/usr``, ``/etc``, ``/opt`` and ``/sys``,
* a private, writable home directory,
* a writable bind mount of the selected mission workspace at ``/workspace``,
* private ``/tmp``, ``/run`` and ``/var``.

Network namespaces are isolated by default.  Loopback still works, which is
what the platform's socket missions use; ``allow_network=True`` shares the
host network for lessons that need DNS or a remote host.

bubblewrap is a rootless tool.  If it is not installed (or unprivileged user
namespaces are disabled) the GUI refuses to open a terminal rather than run
commands unsandboxed.

.. _bubblewrap: https://github.com/containers/bubblewrap
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

BWRAP = "bwrap"

# Directories that are useful read-only inside the study sandbox.
READ_ONLY_DIRS = ("/usr", "/etc", "/opt", "/sys")

# Symlinks that normally live at the root of a Linux filesystem.
ROOT_SYMLINKS = (
    ("/bin", "usr/bin"),
    ("/sbin", "usr/sbin"),
    ("/lib", "usr/lib"),
    ("/lib64", "usr/lib64"),
)

# Host paths that must never be visible inside a session.
MASKED_DIRS = ("/home", "/root", "/mnt", "/media", "/srv", "/boot")

DEFAULT_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

DEFAULT_PS1 = (
    r"\[\e[1;36m\]sandbox\[\e[0m\]:"
    r"\[\e[1;33m\]\w\[\e[0m\] "
    r"\[\e[1;32m\]$\[\e[0m\] "
)


class SandboxUnavailable(RuntimeError):
    """Raised when bubblewrap cannot be used on this machine."""


# Host directories that are already replaced by an empty tmpfs in the sandbox.
PRIVATE_ROOTS = ("/tmp", "/run", "/var", "/home", "/root", "/mnt", "/media", "/srv", "/boot")


def _is_hidden_by_default(path: Path) -> bool:
    for base in PRIVATE_ROOTS:
        try:
            if path == Path(base) or path.is_relative_to(base):
                return True
        except ValueError:  # pragma: no cover - different drives on Windows
            continue
    return False


def bwrap_path() -> str | None:
    """Return the bubblewrap executable, or ``None`` when it is missing."""
    return shutil.which(BWRAP)


def sandbox_available() -> bool:
    return bwrap_path() is not None


@dataclass
class SandboxConfig:
    """Everything needed to build one isolated terminal command."""

    workspace: Path
    home: Path
    allow_network: bool = False
    shell: str = "/bin/bash"
    ps1: str = DEFAULT_PS1
    env: dict[str, str] = field(default_factory=dict)
    # ``--new-session`` protects the *outer* terminal from TIOCSTI, but it also
    # detaches the sandbox from the terminal's foreground process group.  An
    # interactive GUI shell then cannot receive Ctrl-C: the signal kills bwrap
    # (and ``--die-with-parent`` kills the shell) instead of interrupting the
    # running command.  The GUI shell talks to a private PTY that no host shell
    # reads, so the default is off there and on for one-shot commands.
    new_session: bool = False
    # Host paths that must stay invisible even when they live under a
    # read-only system directory (for example a project checkout in /opt).
    # Directories are replaced with an empty tmpfs; files are bound to
    # /dev/null.  Paths already covered by PRIVATE_ROOTS, and paths that
    # contain a system directory, are ignored on purpose.
    hidden_paths: tuple[Path, ...] = ()

    def prepare(self) -> None:
        """Create the writable directories before bubblewrap starts."""
        self.workspace = Path(self.workspace).expanduser().resolve()
        self.home = Path(self.home).expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.home.mkdir(parents=True, exist_ok=True)

    def _hide_arguments(self) -> list[str]:
        """Return bwrap arguments that mask this session's hidden paths."""
        protected = [
            Path(path)
            for path in (*READ_ONLY_DIRS, "/proc", "/dev", "/workspace")
        ]
        # The bind sources for /home/student and /workspace must stay
        # reachable, so never mask a directory that contains them.
        protected += [self.home, self.workspace]
        candidates: list[Path] = []
        for raw in self.hidden_paths:
            path = Path(raw).expanduser()
            try:
                path = path.resolve(strict=True)
            except (OSError, RuntimeError):
                # A path that does not exist is already invisible.  A symlink
                # loop is not something we can mask safely either.
                continue
            if _is_hidden_by_default(path):
                continue
            if any(path == base or base.is_relative_to(path) for base in protected):
                # Refuse to hide /, /usr, /etc, /proc, /dev, ... because that
                # would remove the tools and files the session needs.
                continue
            candidates.append(path)

        # Mask ancestors before descendants.  A nested tmpfs target would not
        # exist once its parent has been replaced by an empty directory.
        candidates.sort(key=lambda item: len(item.parts))
        masked: list[Path] = []
        arguments: list[str] = []
        for path in candidates:
            if any(path == parent or path.is_relative_to(parent) for parent in masked):
                continue
            masked.append(path)
            if path.is_dir():
                arguments += ["--tmpfs", str(path)]
            else:
                arguments += ["--ro-bind", "/dev/null", str(path)]
        return arguments

    def command(self, argv: list[str] | None = None) -> list[str]:
        """Build the full ``bwrap`` argv for this session."""
        self.prepare()
        executable = bwrap_path()
        if executable is None:
            raise SandboxUnavailable(
                "bubblewrap (bwrap) is not installed. Install it with your "
                "package manager (for example: sudo apt install bubblewrap) "
                "to use sandboxed terminals."
            )

        command = [
            executable,
            "--unshare-all",
            "--die-with-parent",
        ]
        if self.new_session:
            command.append("--new-session")
        command += [
            "--cap-drop",
            "ALL",
            "--hostname",
            "study-sandbox",
        ]
        if self.allow_network:
            # --unshare-all also unshared the network; put it back when the
            # lesson explicitly needs DNS or a remote host.
            command.append("--share-net")

        for directory in READ_ONLY_DIRS:
            if Path(directory).exists():
                command += ["--ro-bind", directory, directory]

        for link, target in ROOT_SYMLINKS:
            path = Path(link)
            if path.is_symlink():
                command += ["--symlink", target, link]
            elif path.exists():
                command += ["--ro-bind", link, link]

        command += [
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--tmpfs",
            "/run",
            "--tmpfs",
            "/var",
            "--symlink",
            "/run",
            "/var/run",
            "--dir",
            "/var/tmp",
            "--dir",
            "/var/log",
        ]

        for directory in MASKED_DIRS:
            command += ["--tmpfs", directory]

        command += self._hide_arguments()

        command += [
            "--dir",
            "/home/student",
            "--bind",
            str(self.home),
            "/home/student",
            "--bind",
            str(self.workspace),
            "/workspace",
            "--chdir",
            "/workspace",
            "--clearenv",
        ]

        environment = {
            "HOME": "/home/student",
            "USER": "student",
            "LOGNAME": "student",
            "SHELL": self.shell,
            "PATH": DEFAULT_PATH,
            "TERM": "xterm-256color",
            "COLORTERM": "truecolor",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TMPDIR": "/tmp",
            "PS1": self.ps1,
            "SANDBOX": "linuxplus",
            "STUDY_SANDBOX": "1",
        }
        environment.update(self.env)
        for key, value in environment.items():
            command += ["--setenv", key, str(value)]

        command += ["--"]
        command += list(argv) if argv else [self.shell, "--noprofile", "--norc", "-i"]
        return command

    def describe(self) -> str:
        network = "network shared with host" if self.allow_network else "network isolated"
        return (
            f"bubblewrap sandbox · {network} · workspace {self.workspace} "
            "mounted read-write at /workspace · private home"
        )

    def validate(self, timeout: float = 10.0) -> tuple[bool, str]:
        """Run a tiny command inside the sandbox and report the result."""
        try:
            command = self.command(
                [
                    "/bin/sh",
                    "-c",
                    "test -w /workspace && printf 'sandbox-ok' || exit 1",
                ]
            )
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={"PATH": DEFAULT_PATH, "LC_ALL": "C.UTF-8"},
            )
        except SandboxUnavailable as exc:
            return False, str(exc)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"could not start bubblewrap: {exc}"

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "unknown error").strip()
            return False, f"bubblewrap failed: {detail}"
        return True, proc.stdout.strip() or "sandbox ready"


def terminal_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Minimal environment for the outer bwrap process itself."""
    env = {
        "PATH": DEFAULT_PATH,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TERM": "xterm-256color",
    }
    if extra:
        env.update({str(key): str(value) for key, value in extra.items()})
    return env


__all__ = [
    "BWRAP",
    "DEFAULT_PATH",
    "DEFAULT_PS1",
    "SandboxConfig",
    "SandboxUnavailable",
    "bwrap_path",
    "sandbox_available",
    "terminal_environment",
]
