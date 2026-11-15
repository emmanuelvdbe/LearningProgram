"""PTY-backed terminal sessions used by the GUI.

The GUI needs a persistent shell so ``cd``, environment variables, and
history survive between commands.  :class:`PtySession` starts any argv under a
pseudo-terminal and exposes a thread-safe byte queue that Tkinter can drain
from its event loop.  It is deliberately UI-free so it can be tested without a
display.
"""
from __future__ import annotations

import errno
import fcntl
import os
import pty
import queue
import select
import signal
import struct
import termios
import threading
import time
from typing import Sequence


class PtySession:
    """A child process attached to a pseudo-terminal."""

    def __init__(
        self,
        argv: Sequence[str],
        *,
        env: dict[str, str] | None = None,
        cwd: str | os.PathLike[str] | None = None,
        rows: int = 30,
        cols: int = 100,
        echo: bool = False,
    ) -> None:
        if not argv:
            raise ValueError("argv must not be empty")
        self.argv = [str(item) for item in argv]
        self.env = dict(env) if env is not None else None
        self.cwd = os.fspath(cwd) if cwd is not None else None
        self.rows = max(1, int(rows))
        self.cols = max(1, int(cols))
        self.echo = echo

        self.pid: int = -1
        self.master: int = -1
        self.returncode: int | None = None
        self.eof = False

        self._queue: queue.Queue[bytes | None] = queue.Queue()
        self._lock = threading.Lock()
        self._closed = False
        self._reader: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> "PtySession":
        if self.pid > 0:
            return self
        pid, master = pty.fork()
        if pid == 0:  # child
            try:
                if self.cwd is not None:
                    os.chdir(self.cwd)
                if self.env is not None:
                    os.execvpe(self.argv[0], self.argv, self.env)
                os.execvp(self.argv[0], self.argv)
            except BaseException:
                os._exit(127)

        self.pid = pid
        self.master = master
        self._configure_tty()
        self.resize(self.rows, self.cols)
        self._reader = threading.Thread(
            target=self._read_loop,
            name=f"pty-reader-{pid}",
            daemon=True,
        )
        self._reader.start()
        return self

    def _configure_tty(self) -> None:
        try:
            attrs = termios.tcgetattr(self.master)
        except termios.error:
            return
        if not self.echo:
            attrs[3] &= ~termios.ECHO
        attrs[3] &= ~termios.ECHONL
        try:
            termios.tcsetattr(self.master, termios.TCSANOW, attrs)
        except termios.error:
            pass

    def _read_loop(self) -> None:
        while not self._closed:
            try:
                ready, _, _ = select.select([self.master], [], [], 0.1)
            except (OSError, ValueError):
                break
            if not ready:
                if self.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(self.master, 65536)
            except OSError as exc:
                if exc.errno in (errno.EIO, errno.EBADF):
                    break
                if exc.errno == errno.EINTR:
                    continue
                break
            if not chunk:
                break
            self._queue.put(chunk)
        self.eof = True
        self._queue.put(None)

    def poll(self) -> int | None:
        """Return the exit status when the child has finished."""
        with self._lock:
            if self.returncode is not None:
                return self.returncode
            if self.pid <= 0:
                return None
            try:
                pid, status = os.waitpid(self.pid, os.WNOHANG)
            except ChildProcessError:
                self.returncode = -1
                return self.returncode
            except OSError:
                return None
            if pid == 0:
                return None
            if os.WIFEXITED(status):
                self.returncode = os.WEXITSTATUS(status)
            elif os.WIFSIGNALED(status):
                self.returncode = -os.WTERMSIG(status)
            else:
                self.returncode = -1
            return self.returncode

    def is_alive(self) -> bool:
        return self.poll() is None

    # -- input/output ------------------------------------------------------
    def read(self) -> bytes:
        """Drain queued output without blocking."""
        chunks: list[bytes] = []
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is None:
                self.eof = True
                continue
            chunks.append(item)
        return b"".join(chunks)

    def write(self, data: str | bytes) -> bool:
        if self.master < 0 or self._closed:
            return False
        payload = data.encode("utf-8") if isinstance(data, str) else data
        try:
            os.write(self.master, payload)
            return True
        except OSError:
            return False

    def send_line(self, line: str) -> bool:
        """Send one complete line, as if the user pressed Enter."""
        return self.write(line + "\r")

    def interrupt(self) -> bool:
        return self.write(b"\x03")

    def end_of_file(self) -> bool:
        return self.write(b"\x04")

    def resize(self, rows: int, cols: int) -> None:
        self.rows = max(1, int(rows))
        self.cols = max(1, int(cols))
        if self.master < 0:
            return
        try:
            fcntl.ioctl(
                self.master,
                termios.TIOCSWINSZ,
                struct.pack("HHHH", self.rows, self.cols, 0, 0),
            )
        except OSError:
            pass

    # -- shutdown ----------------------------------------------------------
    def close(self, timeout: float = 0.5) -> None:
        if self._closed:
            return
        self._closed = True
        pid = self.pid
        if pid > 0:
            self._signal_group(signal.SIGHUP)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if self.poll() is not None:
                    break
                time.sleep(0.02)
            if self.poll() is None:
                self._signal_group(signal.SIGTERM)
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if self.poll() is not None:
                        break
                    time.sleep(0.02)
            if self.poll() is None:
                self._signal_group(signal.SIGKILL)
                try:
                    os.waitpid(pid, os.WNOHANG)
                except OSError:
                    pass
        if self.master >= 0:
            try:
                os.close(self.master)
            except OSError:
                pass
            self.master = -1

    def _signal_group(self, sig: int) -> None:
        try:
            os.killpg(self.pid, sig)
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(self.pid, sig)
            except OSError:
                pass
        except OSError:
            pass


__all__ = ["PtySession"]
