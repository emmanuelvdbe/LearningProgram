"""Self-tests for the graphical lab.

The widget tests need a display.  They construct the real application, read a
lesson, navigate to another module, and close it again; the terminal itself is
covered by ``test_sandbox.py`` so these tests stay fast.
"""
from __future__ import annotations

import os
import unittest

from gui import AnsiStripper
from study.sandbox import sandbox_available


class TestAnsiStripper(unittest.TestCase):
    def test_complete_sequences_are_removed(self) -> None:
        stripper = AnsiStripper()
        text = stripper.feed(b"\x1b[?2004h\x1b[1;32mhello\x1b[0m\r\nworld\r\n")
        self.assertEqual(text, "hello\nworld\n")

    def test_partial_escape_survives_a_chunk_boundary(self) -> None:
        stripper = AnsiStripper()
        self.assertEqual(stripper.feed(b"one\x1b[?20"), "one")
        self.assertEqual(stripper.feed(b"04htwo"), "two")
        self.assertEqual(stripper.feed(b"\x1b[1;31mthree"), "three")

    def test_partial_utf8_survives_a_chunk_boundary(self) -> None:
        stripper = AnsiStripper()
        self.assertEqual(stripper.feed(b"caf\xc3"), "caf")
        self.assertEqual(stripper.feed(b"\xa9\n"), "é\n")


def _display_available() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


@unittest.skipUnless(_display_available(), "GUI tests need an X11 or Wayland display")
class TestGuiSmoke(unittest.TestCase):
    def test_construct_read_and_navigate(self) -> None:
        import main
        import gui

        app = gui.StudyApp()
        try:
            app.root.update()
            modules = main.current_modules()
            if not modules:
                self.skipTest("the active save has no curriculum modules")

            self.assertIsNotNone(app._current_module)
            self.assertTrue(app.lesson_tab.text.get("1.0", "end-1c").strip())
            self.assertIn(str(app._current_module["num"]), app.mission_tab.title.cget("text"))
            self.assertIn("Mission", app.mission_tab.title.cget("text"))
            self.assertEqual(
                app.terminal_tab.available,
                gui.sandbox_available(),
            )

            target = modules[-1]
            app.tree.selection_set(app._module_iids[target["id"]])
            for _ in range(5):
                app.root.update()
            self.assertEqual(app._current_module["id"], target["id"])
            self.assertTrue(app.lesson_tab.text.get("1.0", "end-1c").strip())
            self.assertTrue(app.files_tab.workspace.is_dir())
            self.assertEqual(
                app.files_tab.workspace.parent,
                main.exam_lab(),
            )

            app.refresh_progress()
            self.assertIn("missions", app.progress_label.cget("text"))
        finally:
            app.close()

    @unittest.skipUnless(sandbox_available(), "bubblewrap is not installed")
    def test_gui_check_reports_ready(self) -> None:
        import contextlib
        import io

        import gui

        with contextlib.redirect_stdout(io.StringIO()):
            result = gui.check()
        self.assertEqual(result, 0)

    def test_hint_state_is_reset_between_modules(self) -> None:
        from types import SimpleNamespace

        import gui

        app = gui.StudyApp()
        try:
            app.root.update()
            workspace = app.files_tab.workspace
            self.assertIsNotNone(workspace)
            first = SimpleNamespace(
                num=90,
                id="fake-90",
                title="First",
                brief="First brief.",
                hints=["try the obvious thing"],
            )
            app.mission_tab.set_module(
                {"num": 90, "id": "fake-90", "title": "First", "domain": "test"},
                first,
                workspace,
            )
            app.mission_tab.reveal_hint()
            self.assertIn(
                "obvious", app.mission_tab.hints_text.get("1.0", "end-1c")
            )

            second = SimpleNamespace(
                num=91, id="fake-91", title="Second", brief="Second brief.", hints=[]
            )
            app.mission_tab.set_module(
                {"num": 91, "id": "fake-91", "title": "Second", "domain": "test"},
                second,
                workspace,
            )
            self.assertEqual(
                app.mission_tab.hints_text.get("1.0", "end-1c").strip(), ""
            )
            self.assertEqual(app.mission_tab.hint_button.cget("text"), "No hints")
            self.assertIn("disabled", app.mission_tab.hint_button.state())
        finally:
            app.close()

    def test_editor_rejects_non_utf8_files(self) -> None:
        from unittest import mock

        import gui

        app = gui.StudyApp()
        try:
            app.root.update()
            workspace = app.files_tab.workspace
            self.assertIsNotNone(workspace)
            bad = workspace / "not-utf8.bin"
            bad.write_bytes(b"\xff\xfehello")
            try:
                with mock.patch("tkinter.messagebox.showinfo") as info:
                    app.files_tab.open_path(bad)
                info.assert_called_once()
                self.assertNotEqual(app.files_tab.current_path, bad)
            finally:
                bad.unlink()
        finally:
            app.close()

    def test_sandbox_hidden_paths_include_project_and_lab(self) -> None:
        import main
        import gui

        app = gui.StudyApp()
        try:
            hidden = app.sandbox_hidden_paths()
            self.assertIn(main.PROGRAM_DIR, hidden)
            self.assertIn(main.LAB, hidden)
        finally:
            app.close()


if __name__ == "__main__":
    unittest.main()
