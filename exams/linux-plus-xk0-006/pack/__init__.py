"""CompTIA Linux+ XK0-006 curriculum pack.

The pack is discovered by :class:`study.exams.Exam` and exposes the same
surface as the built-in curriculum: modules, missions, and lesson paths.
"""
from __future__ import annotations

from pathlib import Path

from .missions import MISSIONS, get_mission, install_solution
from .syllabus import BY_ID, BY_NUM, MODULES, get_module, total_minutes

LESSON_DIR = Path(__file__).resolve().parent / "lessons"


def lesson_path(module: dict) -> Path:
    return LESSON_DIR / module["lesson"]


__all__ = [
    "MODULES",
    "BY_ID",
    "BY_NUM",
    "MISSIONS",
    "LESSON_DIR",
    "get_module",
    "get_mission",
    "lesson_path",
    "install_solution",
    "total_minutes",
]
