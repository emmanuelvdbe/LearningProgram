"""Multi-exam platform support: exam packs, save slots, and objectives.

The original Linux+ curriculum is a built-in *pack*.  Other exams can live in
``exams/<exam-id>/`` with an ``exam.json`` manifest and a folder of CompTIA
objectives.  Save slots keep each learner's progress separate and remember
which exam that save is currently studying.
"""
from __future__ import annotations

from .exams import (
    EXAMS_DIR,
    INBOX_DIR,
    Exam,
    attach_objective,
    create_exam,
    get_exam,
    load_exams,
    resolve_exam,
    slugify,
)
from .objectives import (
    clean_text,
    extract_text,
    read_objective_text,
    scan_objectives,
)
from . import saves

__all__ = [
    "EXAMS_DIR",
    "INBOX_DIR",
    "Exam",
    "attach_objective",
    "clean_text",
    "create_exam",
    "extract_text",
    "get_exam",
    "load_exams",
    "read_objective_text",
    "resolve_exam",
    "scan_objectives",
    "saves",
    "slugify",
]
