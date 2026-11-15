"""Self-tests for the multi-exam platform: exams, objectives, and save slots."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from study import saves
from study import exams as exam_mod
from study.objectives import read_objective_text, scan_objectives


class TestSaveSlots(unittest.TestCase):
    def test_saves_are_isolated_and_switchable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = saves.ensure_directory(root / "saves", root / "fallback")

            alice = saves.create_save(directory, "alice", "linux-plus-xk0-005")
            alice_progress = saves.exam_progress(alice, "linux-plus-xk0-005")
            alice_progress["completed"]["m01"] = {"at": "now"}
            saves.write_save(directory, "alice", alice)

            bob = saves.create_save(directory, "bob", "linux-plus-xk0-005")
            bob_progress = saves.exam_progress(bob, "linux-plus-xk0-005")
            bob_progress["completed"]["m02"] = {"at": "now"}
            saves.write_save(directory, "bob", bob)

            self.assertEqual(
                saves.completed_count(saves.load_save(directory, "alice"), "linux-plus-xk0-005"),
                1,
            )
            self.assertEqual(
                saves.completed_count(saves.load_save(directory, "bob"), "linux-plus-xk0-005"),
                1,
            )
            self.assertIn("m01", saves.load_save(directory, "alice")["progress"]["linux-plus-xk0-005"]["completed"])
            self.assertNotIn("m01", saves.load_save(directory, "bob")["progress"]["linux-plus-xk0-005"]["completed"])

            saves.set_active_name(directory, "alice")
            self.assertEqual(saves.active_name(directory), "alice")
            self.assertEqual(saves.list_save_names(directory), ["alice", "bob"])

            saves.copy_save(directory, "alice", "carol")
            self.assertEqual(
                saves.completed_count(saves.load_save(directory, "carol"), "linux-plus-xk0-005"),
                1,
            )

            saves.set_active_name(directory, "bob")
            saves.delete_save(directory, "bob")
            self.assertEqual(saves.active_name(directory), "alice")

    def test_save_names_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = saves.ensure_directory(Path(temporary) / "s", Path(temporary) / "f")
            for bad in ("", "  ", "../escape", ".hidden", "a/b"):
                with self.subTest(name=bad):
                    with self.assertRaises(ValueError):
                        saves.normalize_name(bad)
            with self.assertRaises(FileExistsError):
                saves.create_save(directory, "same", "exam")
                saves.create_save(directory, "same", "exam")


class TestObjectives(unittest.TestCase):
    def test_scan_extracts_text_and_skips_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "objectives"
            directory.mkdir()
            (directory / "README.md").write_text(
                "Instructions only; do not treat as objectives.", encoding="utf-8"
            )
            (directory / "sy0-701.md").write_text(
                "# Domain 1\n1.1 Compare security controls.\n", encoding="utf-8"
            )
            (directory / "notes.txt").write_text(
                "2.1 Given a scenario, implement controls.\n", encoding="utf-8"
            )
            (directory / "ignored.bin").write_bytes(b"\x00\x01")

            results = scan_objectives(directory)
            self.assertEqual(len(results), 2)
            self.assertTrue(all(item.status == "extracted" for item in results))
            self.assertTrue((directory / "_index.json").is_file())
            self.assertTrue((directory / "_text" / "sy0-701.md.txt").is_file())

            index = json.loads((directory / "_index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(index["sources"]), 2)

            chunks = read_objective_text(directory)
            self.assertEqual(len(chunks), 2)
            combined = "\n".join(text for _, text in chunks)
            self.assertIn("security controls", combined)
            self.assertNotIn("Instructions only", combined)


class TestExamManifests(unittest.TestCase):
    def test_create_attach_and_resolve_exam(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "exams"
            inbox = root / "_inbox"
            inbox.mkdir(parents=True)
            with mock.patch.object(exam_mod, "EXAMS_DIR", root), mock.patch.object(
                exam_mod, "INBOX_DIR", inbox
            ):
                created = exam_mod.create_exam(
                    "security-plus-sy0-701",
                    "CompTIA Security+ (SY0-701)",
                    code="SY0-701",
                )
                self.assertTrue((root / "security-plus-sy0-701" / "exam.json").is_file())
                self.assertTrue(created.objectives_dir.is_dir())
                self.assertFalse(created.has_curriculum)

                source = inbox / "objectives.md"
                source.write_text("1.1 Test objective.\n", encoding="utf-8")
                attached = exam_mod.attach_objective(created, source)
                self.assertTrue(attached.is_file())
                self.assertEqual(len(created.objective_files()), 1)

                found = exam_mod.load_exams()
                self.assertTrue(any(exam.id == "security-plus-sy0-701" for exam in found))
                resolved = exam_mod.resolve_exam("security", found)
                self.assertEqual(resolved.id, "security-plus-sy0-701")

                with self.assertRaises(FileExistsError):
                    exam_mod.create_exam("security-plus-sy0-701", "Duplicate")

    def test_builtin_linux_plus_pack(self) -> None:
        found = exam_mod.load_exams()
        linux = next(exam for exam in found if exam.id == "linux-plus-xk0-005")
        self.assertTrue(linux.has_curriculum)
        self.assertEqual(len(linux.modules()), 16)
        module = linux.get_module(1)
        self.assertIsNotNone(module)
        self.assertTrue(linux.lesson_path(module).is_file())
        self.assertIsNotNone(linux.get_mission(module["id"]))
        self.assertEqual(linux.total_minutes(), 1565)

    def test_custom_pack_loads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = root / "pack"
            pack.mkdir()
            (pack / "pack.py").write_text(
                "from pathlib import Path\n"
                "LESSON_DIR = Path(__file__).parent / 'lessons'\n"
                "MODULES = [{\n"
                "    'num': 1, 'id': 'tp01', 'part': 'Part I',\n"
                "    'title': 'Test module', 'lesson': '01.md',\n"
                "    'domain': 'Test 1.1', 'summary': 'test', 'minutes': 30,\n"
                "}]\n"
                "MISSIONS = []\n",
                encoding="utf-8",
            )
            exam = exam_mod.Exam(
                id="test-pack",
                name="Test Pack",
                code="TP-001",
                short_name="Test",
                status="ready",
                curriculum="pack",
                path=root,
            )
            self.assertTrue(exam.has_curriculum)
            self.assertEqual(len(exam.modules()), 1)
            self.assertEqual(exam.get_module(1)["title"], "Test module")
            self.assertIsNone(exam.get_mission(1))
            self.assertEqual(exam.total_minutes(), 30)
            self.assertEqual(
                exam.lesson_path(exam.modules()[0]),
                pack / "lessons" / "01.md",
            )


if __name__ == "__main__":
    unittest.main()
