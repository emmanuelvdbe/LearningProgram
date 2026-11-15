"""Exam discovery, metadata, and optional curriculum packs."""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

PROGRAM_DIR = Path(__file__).resolve().parent.parent
EXAMS_DIR = PROGRAM_DIR / "exams"
INBOX_DIR = EXAMS_DIR / "_inbox"

BUILTIN_EXAM_ID = "linux-plus-xk0-005"
MANIFEST = "exam.json"


def slugify(text: str) -> str:
    """Make a stable, filesystem-friendly identifier."""
    text = text.strip().lower()
    text = text.replace("+", "-plus")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _split_short_name(name: str) -> str:
    """Turn 'CompTIA Security+ (SY0-701)' into 'Security+'."""
    short = re.sub(r"^compTIA\s+", "", name, flags=re.IGNORECASE).strip()
    short = re.sub(r"\s*\([^)]*\)\s*$", "", short).strip()
    return short or name


@dataclass
class Exam:
    """One certification exam and, optionally, its curriculum pack."""

    id: str
    name: str
    code: str
    short_name: str
    status: str
    curriculum: str | None
    path: Path
    description: str = ""
    domains: list[str] = field(default_factory=list)
    _pack: object | None = field(default=None, init=False, repr=False)

    @property
    def manifest_path(self) -> Path:
        return self.path / MANIFEST

    @property
    def objectives_dir(self) -> Path:
        return self.path / "objectives"

    @property
    def has_curriculum(self) -> bool:
        return self.pack() is not None

    @property
    def aliases(self) -> set[str]:
        values = {
            self.id,
            self.id.replace("-", ""),
            self.code,
            self.short_name,
            self.name,
            self.name.replace("CompTIA ", ""),
        }
        return {alias.strip().lower() for alias in values if alias}

    def pack(self) -> object | None:
        """Load the curriculum pack, if this exam has one."""
        if self._pack is not None:
            return self._pack
        if not self.curriculum:
            return None
        if self.curriculum == "linux_plus":
            try:
                import curriculum
            except ImportError:
                return None
            self._pack = curriculum
            return self._pack

        # Future packs: exams/<id>/<curriculum>/ containing pack.py or
        # __init__.py.  The module should expose MODULES, get_mission(),
        # and lesson_path(); MISSIONS and LESSON_DIR are also understood.
        base = (self.path / self.curriculum).resolve()
        module_file = base / "pack.py"
        if not module_file.is_file():
            module_file = base / "__init__.py"
        if not module_file.is_file():
            return None
        name = f"exam_pack_{self.id.replace('-', '_')}"
        options: dict[str, object] = {}
        if module_file.name == "__init__.py":
            # Treat the folder as a real package so relative imports such as
            # ``from .syllabus import MODULES`` work inside the pack.
            options["submodule_search_locations"] = [str(base)]
        spec = importlib.util.spec_from_file_location(name, module_file, **options)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(name, None)
            raise
        self._pack = module
        return module

    def modules(self) -> list[dict]:
        pack = self.pack()
        if pack is None:
            return []
        return list(getattr(pack, "MODULES", []))

    def get_module(self, key: str | int) -> dict | None:
        if isinstance(key, int):
            number = key
        else:
            key = str(key).strip().lower()
            if key.isdigit():
                number = int(key)
            else:
                for module in self.modules():
                    if module["id"].lower() == key:
                        return module
                return None
        for module in self.modules():
            if module["num"] == number:
                return module
        return None

    def get_mission(self, key: str | int):
        pack = self.pack()
        if pack is None:
            return None
        if hasattr(pack, "get_mission"):
            return pack.get_mission(key)
        missions = getattr(pack, "MISSIONS", [])
        if isinstance(key, int):
            number = key
        else:
            text = str(key).strip().lower()
            number = int(text) if text.isdigit() else None
        for mission in missions:
            if number is not None and mission.num == number:
                return mission
            if number is None and str(key).strip().lower() == mission.id.lower():
                return mission
        return None

    def lesson_path(self, module: dict) -> Path:
        pack = self.pack()
        if pack is not None:
            if hasattr(pack, "lesson_path"):
                return Path(pack.lesson_path(module))
            lesson_dir = getattr(pack, "LESSON_DIR", None)
            if lesson_dir is not None:
                return Path(lesson_dir) / module["lesson"]
        return self.path / "lessons" / module["lesson"]

    def install_solution(self, mission, destination: Path) -> list[Path]:
        """Write a mission's reference solution into ``destination``."""
        written: list[Path] = []
        for relative, content in mission.solution.items():
            path = destination / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            if content.startswith("#!") or path.suffix == ".sh":
                path.chmod(0o755)
            written.append(path)
        hook = getattr(mission, "post_install", None)
        if hook is not None:
            hook(destination)
        return written

    def total_minutes(self) -> int:
        return sum(module.get("minutes", 0) for module in self.modules())

    def objective_files(self) -> list[Path]:
        if not self.objectives_dir.is_dir():
            return []
        ignored = {"_text", "_index.json"}
        files = []
        for path in sorted(self.objectives_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.name in ignored or "_text" in path.parts:
                continue
            if path.stem.lower() == "readme":
                continue
            files.append(path)
        return files

    def summary(self) -> str:
        if self.has_curriculum:
            modules = len(self.modules())
            return f"{modules} modules ready"
        count = len(self.objective_files())
        return f"objectives only ({count} document{'s' if count != 1 else ''})"


def _exam_from_manifest(path: Path) -> Exam | None:
    try:
        raw = json.loads((path / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or not raw.get("id") or not raw.get("name"):
        return None
    return Exam(
        id=str(raw["id"]).strip(),
        name=str(raw["name"]).strip(),
        code=str(raw.get("code", "")).strip(),
        short_name=str(raw.get("short_name") or _split_short_name(str(raw["name"]))),
        status=str(raw.get("status", "objectives-only")),
        curriculum=raw.get("curriculum"),
        path=path,
        description=str(raw.get("description", "")),
        domains=list(raw.get("domains", [])),
    )


def load_exams() -> list[Exam]:
    """Discover exam manifests, always including the built-in Linux+ pack."""
    exams: list[Exam] = []
    if EXAMS_DIR.is_dir():
        for child in sorted(EXAMS_DIR.iterdir()):
            if not child.is_dir() or child.name.startswith("_"):
                continue
            if not (child / MANIFEST).is_file():
                continue
            exam = _exam_from_manifest(child)
            if exam is not None:
                exams.append(exam)

    if not any(exam.id == BUILTIN_EXAM_ID for exam in exams):
        exams.insert(
            0,
            Exam(
                id=BUILTIN_EXAM_ID,
                name="CompTIA Linux+ (XK0-005)",
                code="XK0-005",
                short_name="Linux+",
                status="ready",
                curriculum="linux_plus",
                path=EXAMS_DIR / BUILTIN_EXAM_ID,
                description=(
                    "Python for Linux administration: scripts, logs, users, "
                    "permissions, networking, services, backups, and testing."
                ),
                domains=[
                    "1.0 System Management",
                    "2.0 Security",
                    "3.0 Scripting, Containers, and Automation",
                    "4.0 Troubleshooting",
                ],
            ),
        )
    return exams


def get_exam(key: str, exams: list[Exam] | None = None) -> Exam | None:
    """Exact lookup by id, code, short name, or full name."""
    if not key:
        return None
    wanted = key.strip().lower()
    for exam in exams if exams is not None else load_exams():
        if wanted in exam.aliases:
            return exam
    return None


def resolve_exam(key: str, exams: list[Exam] | None = None) -> Exam:
    """Resolve an id or a unique prefix, with a helpful error message."""
    exams = exams if exams is not None else load_exams()
    exact = get_exam(key, exams)
    if exact is not None:
        return exact

    wanted = key.strip().lower()
    matches = [
        exam
        for exam in exams
        if any(alias.startswith(wanted) for alias in exam.aliases)
        or wanted in exam.id
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        choices = ", ".join(exam.id for exam in matches)
        raise ValueError(f"{key!r} is ambiguous. Choose one of: {choices}")
    raise ValueError(
        f"Unknown exam {key!r}. Available: "
        + ", ".join(exam.id for exam in exams)
    )


def create_exam(
    exam_id: str,
    name: str,
    code: str = "",
    description: str = "",
    short_name: str = "",
) -> Exam:
    """Scaffold a new objectives-only exam folder."""
    exam_id = slugify(exam_id)
    if not exam_id:
        raise ValueError("Exam id must contain letters or numbers.")
    folder = EXAMS_DIR / exam_id
    if folder.exists():
        raise FileExistsError(f"Exam folder already exists: {folder}")

    code = code.strip() or exam_id.upper()
    short_name = short_name.strip() or _split_short_name(name)
    metadata = {
        "id": exam_id,
        "name": name.strip(),
        "short_name": short_name,
        "vendor": "CompTIA",
        "code": code,
        "status": "objectives-only",
        "curriculum": None,
        "description": description.strip()
        or "Objectives imported; a hands-on curriculum pack has not been built yet.",
        "domains": [],
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    objectives = folder / "objectives"
    objectives.mkdir(parents=True)
    (folder / MANIFEST).write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    (objectives / "README.md").write_text(
        f"# {name} objectives\n\n"
        "Put the official CompTIA objectives PDF or text files in this folder,\n"
        "then run:\n\n"
        f"    python3 main.py exam scan {exam_id}\n\n"
        "The scanner extracts readable text into `_text/` so the curriculum\n"
        "builder can work from it.\n",
        encoding="utf-8",
    )
    exam = _exam_from_manifest(folder)
    assert exam is not None
    return exam


def attach_objective(exam: Exam, source: Path) -> Path:
    """Copy one objectives document into an exam's objectives folder."""
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"No such file: {source}")
    exam.objectives_dir.mkdir(parents=True, exist_ok=True)
    destination = exam.objectives_dir / source.name
    if destination.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = exam.objectives_dir / f"{source.stem}-{stamp}{source.suffix}"
    shutil.copy2(source, destination)
    return destination
