"""Self-tests for the sandboxed terminal layer.

These tests exercise the real bubblewrap binary when it is installed.  They
are skipped on machines without it, but the command-construction tests always
run so a policy regression is visible everywhere.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from study.sandbox import (
    DEFAULT_PATH,
    SandboxConfig,
    bwrap_path,
    sandbox_available,
    terminal_environment,
)
from study.terminal import PtySession


def read_until(
    session: PtySession, needle: str, timeout: float = 10.0
) -> str:
    """Read PTY output until ``needle`` appears, or fail with the buffer."""
    buffer = ""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        chunk = session.read()
        if chunk:
            buffer += chunk.decode("utf-8", "replace")
            if needle in buffer:
                return buffer
        elif session.eof:
            break
        time.sleep(0.03)
    raise AssertionError(
        f"did not see {needle!r} within {timeout}s; output:\n{buffer[-2000:]}"
    )


def wait_for_exit(session: PtySession, timeout: float = 10.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session.read()
        code = session.poll()
        if code is not None:
            return code
        time.sleep(0.03)
    raise AssertionError(f"process did not exit within {timeout}s")


class TestSandboxCommand(unittest.TestCase):
    def test_command_contains_isolation_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = SandboxConfig(root / "workspace", root / "home")
            command = config.command()

            self.assertEqual(command[0], bwrap_path())
            self.assertIn("--unshare-all", command)
            self.assertIn("--die-with-parent", command)
            self.assertIn("--cap-drop", command)
            self.assertIn("ALL", command)
            self.assertNotIn("--share-net", command)
            self.assertNotIn("--new-session", command)

            self.assertIn("--chdir", command)
            self.assertIn("/workspace", command)
            self.assertIn("--clearenv", command)
            self.assertIn("--tmpfs", command)
            for masked in ("/home", "/root", "/mnt", "/media", "/srv", "/boot"):
                self.assertIn(masked, command)
            self.assertIn(str(config.workspace.resolve()), command)
            self.assertTrue(config.workspace.is_dir())
            self.assertTrue(config.home.is_dir())

    def test_network_and_new_session_are_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = SandboxConfig(
                root / "workspace",
                root / "home",
                allow_network=True,
                new_session=True,
            )
            command = config.command()
            self.assertIn("--share-net", command)
            self.assertIn("--new-session", command)
            self.assertIn("network shared with host", config.describe())

    def test_hidden_paths_are_masked_and_deduplicated(self) -> None:
        shared = Path("/dev/shm")
        if not shared.is_dir() or not os.access(shared, os.W_OK):
            self.skipTest("/dev/shm is not writable")
        with tempfile.TemporaryDirectory(dir=shared) as temporary:
            root = Path(temporary)
            project = root / "project"
            nested = project / "saves"
            nested.mkdir(parents=True)
            secret = root / "secret.txt"
            secret.write_text("hidden", encoding="utf-8")

            config = SandboxConfig(
                root / "workspace",
                root / "home",
                hidden_paths=(
                    project,
                    nested,  # already inside project: must be skipped
                    secret,
                    Path("/tmp/already-private"),
                    Path("/usr"),  # never hide the system
                ),
            )
            command = config.command()

            tmpfs = [
                command[index + 1]
                for index, item in enumerate(command)
                if item == "--tmpfs"
            ]
            self.assertIn(str(project.resolve()), tmpfs)
            self.assertNotIn(str(nested.resolve()), tmpfs)
            self.assertNotIn("/tmp/already-private", tmpfs)
            self.assertNotIn("/usr", tmpfs)

            self.assertIn(str(secret.resolve()), command)
            index = command.index(str(secret.resolve()))
            self.assertEqual(command[index - 1], "/dev/null")
            self.assertEqual(command[index - 2], "--ro-bind")

    def test_environment_is_minimal(self) -> None:
        env = terminal_environment()
        self.assertEqual(env["PATH"], DEFAULT_PATH)
        self.assertNotIn("HOME", env)

    @unittest.skipUnless(sandbox_available(), "bubblewrap is not installed")
    def test_validate_starts_a_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = SandboxConfig(root / "workspace", root / "home")
            ok, message = config.validate()
            self.assertTrue(ok, message)
            self.assertIn("sandbox-ok", message)


@unittest.skipUnless(sandbox_available(), "bubblewrap is not installed")
class TestRealSandbox(unittest.TestCase):
    def test_workspace_writable_and_host_masked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            config = SandboxConfig(workspace, root / "home")
            host_secret = root / "host-secret.txt"
            host_secret.write_text("do not leak", encoding="utf-8")
            project_path = Path(__file__).resolve()

            script = "\n".join(
                [
                    "set -eu",
                    "echo proof > /workspace/proof.txt",
                    "test -f /workspace/proof.txt",
                    "if [ -e %s ]; then echo HOST-SECRET-VISIBLE; exit 3; fi" % host_secret,
                    "if [ -e %s ]; then echo PROJECT-VISIBLE; exit 4; fi" % project_path,
                    "if [ -e /mnt/Main ]; then echo MNT-VISIBLE; exit 5; fi",
                    "if touch /etc/linuxplus-should-fail 2>/dev/null; then echo ETC-WRITABLE; exit 6; fi",
                    "echo SANDBOX-OK",
                ]
            )
            process = subprocess.run(
                config.command(["/bin/sh", "-c", script]),
                capture_output=True,
                text=True,
                env=terminal_environment(),
                timeout=30,
            )
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertIn("SANDBOX-OK", process.stdout)
            self.assertEqual((workspace / "proof.txt").read_text().strip(), "proof")

    def test_network_is_isolated_but_loopback_works(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = SandboxConfig(root / "workspace", root / "home")
            script = "\n".join(
                [
                    "python3 - <<'PY'",
                    "import socket",
                    "s = socket.socket()",
                    "s.settimeout(2)",
                    "try:",
                    "    s.connect(('1.1.1.1', 53))",
                    "except OSError:",
                    "    print('NETWORK-ISOLATED')",
                    "else:",
                    "    raise SystemExit('network is reachable')",
                    "finally:",
                    "    s.close()",
                    "t = socket.socket()",
                    "t.bind(('127.0.0.1', 0))",
                    "print('LOOPBACK-OK')",
                    "t.close()",
                    "PY",
                ]
            )
            process = subprocess.run(
                config.command(["/bin/sh", "-c", script]),
                capture_output=True,
                text=True,
                env=terminal_environment(),
                timeout=30,
            )
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertIn("NETWORK-ISOLATED", process.stdout)
            self.assertIn("LOOPBACK-OK", process.stdout)

    def test_ctrl_c_interrupts_the_command_not_the_shell(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = SandboxConfig(root / "workspace", root / "home")
            argv = config.command([config.shell, "--noprofile", "--norc", "-i"])
            session = PtySession(argv, env=terminal_environment(), echo=False).start()
            try:
                read_until(session, "$")
                session.send_line("echo READY")
                read_until(session, "READY")
                session.send_line("sleep 20")
                time.sleep(0.4)
                session.interrupt()
                time.sleep(0.6)
                self.assertTrue(session.is_alive(), "Ctrl-C killed the sandboxed shell")
                session.send_line("echo AFTER-INTERRUPT")
                read_until(session, "AFTER-INTERRUPT")
            finally:
                session.close()


class TestPtySession(unittest.TestCase):
    def test_captures_output_and_exit_status(self) -> None:
        session = PtySession(
            ["/bin/sh", "-c", "printf 'hello\\n'; exit 3"],
            env={"PATH": DEFAULT_PATH},
        ).start()
        try:
            output = read_until(session, "hello")
            self.assertIn("hello", output)
            self.assertEqual(wait_for_exit(session), 3)
        finally:
            session.close()

    def test_cat_output_and_eof(self) -> None:
        session = PtySession(["/bin/cat"], env={"PATH": DEFAULT_PATH}).start()
        try:
            self.assertTrue(session.write("x\n"))
            read_until(session, "x")
            session.end_of_file()
            self.assertEqual(wait_for_exit(session), 0)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
