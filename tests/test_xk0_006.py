"""Self-tests for the CompTIA Linux+ XK0-006 curriculum pack.

Run from the Learning Program directory:

    python3 -m unittest discover -s tests -v

These tests cover four things the new pack must get right:

* the syllabus and the mission registry agree (22 modules, 22 missions),
* every module has a substantial written lesson,
* all 29 official objectives (1.1 through 5.5) are represented,
* every reference solution passes its own mission checker.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from study import exams as exam_mod

EXAM_ID = "linux-plus-xk0-006"
EXPECTED_MODULES = 22
EXPECTED_MINUTES = 2350
EXPECTED_OBJECTIVES = {
    f"{domain}.{objective}"
    for domain, count in {1: 7, 2: 6, 3: 6, 4: 5, 5: 5}.items()
    for objective in range(1, count + 1)
}


def load_exam():
    found = exam_mod.load_exams()
    exam = next((item for item in found if item.id == EXAM_ID), None)
    if exam is None:  # pragma: no cover - only when the pack is deleted
        raise AssertionError(f"{EXAM_ID} was not discovered")
    return exam


class TestXk0006Pack(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.exam = load_exam()
        cls.modules = cls.exam.modules()
        cls.missions = list(cls.exam.pack().MISSIONS)

    def test_exam_manifest_is_ready(self) -> None:
        self.assertEqual(self.exam.code, "XK0-006")
        self.assertEqual(self.exam.status, "ready")
        self.assertTrue(self.exam.has_curriculum)
        self.assertEqual(len(self.exam.domains), 5)

    def test_syllabus_and_missions_agree(self) -> None:
        self.assertEqual(len(self.modules), EXPECTED_MODULES)
        self.assertEqual(len(self.missions), EXPECTED_MODULES)
        for module in self.modules:
            mission = self.exam.get_mission(module["id"])
            self.assertIsNotNone(mission, f"missing mission for {module['id']}")
            assert mission is not None
            self.assertEqual(module["num"], mission.num)
            self.assertEqual(module["title"], mission.title)
            self.assertEqual(module["domain"], mission.domain)

    def test_module_numbers_and_ids_are_contiguous_and_unique(self) -> None:
        numbers = [module["num"] for module in self.modules]
        ids = [module["id"] for module in self.modules]
        self.assertEqual(numbers, list(range(1, EXPECTED_MODULES + 1)))
        self.assertEqual(len(set(ids)), EXPECTED_MODULES)
        self.assertEqual(
            [mission.num for mission in self.missions],
            list(range(1, EXPECTED_MODULES + 1)),
        )

    def test_total_study_time(self) -> None:
        self.assertEqual(self.exam.total_minutes(), EXPECTED_MINUTES)

    def test_lesson_files_exist_and_are_substantial(self) -> None:
        for module in self.modules:
            path = self.exam.lesson_path(module)
            self.assertTrue(path.is_file(), f"missing lesson {path}")
            text = path.read_text(encoding="utf-8")
            self.assertGreater(
                len(text.splitlines()),
                100,
                f"{module['lesson']} is too short for an in-depth lesson",
            )
            self.assertIn("Mission", text, f"{module['lesson']} omits its mission")
            self.assertIn("# Module", text, f"{module['lesson']} has no title")

    def test_every_official_objective_is_covered(self) -> None:
        covered = set()
        for module in self.modules:
            covered.update(re.findall(r"\b([1-5]\.[1-7])\b", module["domain"]))
        missing = EXPECTED_OBJECTIVES - covered
        extra = covered - EXPECTED_OBJECTIVES
        self.assertFalse(missing, f"objectives with no module: {sorted(missing)}")
        self.assertFalse(extra, f"unknown objectives referenced: {sorted(extra)}")

    def test_every_mission_has_hints_and_a_solution(self) -> None:
        for mission in self.missions:
            self.assertGreaterEqual(len(mission.hints), 2, mission.id)
            self.assertTrue(mission.solution, mission.id)
            self.assertIsNotNone(mission.check, mission.id)
            self.assertIsNotNone(mission.setup, mission.id)

    def test_objectives_document_is_attached(self) -> None:
        files = self.exam.objective_files()
        self.assertTrue(files, "the official objectives document is missing")
        self.assertTrue(
            any(path.suffix.lower() == ".pdf" for path in files),
            f"expected a PDF objectives document, found {files}",
        )

    def test_every_solution_passes_its_checker(self) -> None:
        failures: list[str] = []
        for mission in self.missions:
            with self.subTest(mission=mission.id):
                workspace = Path(
                    tempfile.mkdtemp(prefix=f"xk0006-{mission.id}-")
                )
                try:
                    mdir = mission.prepare(workspace)
                    self.exam.install_solution(mission, mdir)
                    checks = mission.run_checks(workspace)
                    bad = [check for check in checks if not check.ok]
                    if bad:
                        lines = [
                            f"{mission.id} {mission.title}:",
                            *[
                                f"  FAIL {check.name}\n    {check.detail}"
                                for check in bad
                            ],
                        ]
                        failures.append("\n".join(lines))
                finally:
                    shutil.rmtree(workspace, ignore_errors=True)
        if failures:
            self.fail("\n\n".join(failures))


if __name__ == "__main__":
    unittest.main()
