"""Curriculum package: modules, lessons, and missions."""
from pathlib import Path

from .syllabus import BY_ID, BY_NUM, MODULES, get_module, total_minutes
from .missions import MISSIONS, get_mission, install_solution

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
