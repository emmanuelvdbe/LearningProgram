"""Self-tests: every reference solution must pass its own mission checker.

Run from the Learning Program directory:

    python3 -m unittest discover -s tests -v

These tests intentionally install the reference solution into a throwaway
workspace, then run the same checks a learner would run.  They catch broken
fixtures, brittle checkers, and typos in a solution.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from curriculum import MODULES, get_mission, install_solution, lesson_path
from curriculum.missions import MISSIONS


class TestMissionSolutions(unittest.TestCase):
    def test_every_solution_passes(self) -> None:
        failures: list[str] = []
        for mission in MISSIONS:
            with self.subTest(mission=mission.id):
                workspace = Path(
                    tempfile.mkdtemp(prefix=f"linuxplus-{mission.id}-")
                )
                try:
                    mdir = mission.prepare(workspace)
                    install_solution(mission, mdir)
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


class TestCurriculum(unittest.TestCase):
    def test_syllabus_and_missions_agree(self) -> None:
        self.assertEqual(len(MODULES), 16)
        self.assertEqual(len(MISSIONS), 16)
        for module in MODULES:
            mission = get_mission(module["id"])
            self.assertIsNotNone(mission, f"missing mission for {module['id']}")
            assert mission is not None
            self.assertEqual(module["num"], mission.num)
            self.assertEqual(module["title"], mission.title)

    def test_lesson_files_exist(self) -> None:
        for module in MODULES:
            path = lesson_path(module)
            self.assertTrue(
                path.is_file(),
                f"missing lesson {path.name} for module {module['num']}",
            )

    def test_lesson_files_are_substantial(self) -> None:
        for module in MODULES:
            text = lesson_path(module).read_text(encoding="utf-8")
            self.assertGreater(
                len(text.splitlines()),
                40,
                f"{module['lesson']} looks too short to teach anything",
            )

    def test_every_mission_has_hints_and_solution(self) -> None:
        for mission in MISSIONS:
            self.assertGreaterEqual(len(mission.hints), 2, mission.id)
            self.assertTrue(mission.solution, mission.id)
            self.assertIsNotNone(mission.check, mission.id)


if __name__ == "__main__":
    unittest.main()
