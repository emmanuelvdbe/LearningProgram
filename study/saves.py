"""Save slots: isolated progress files with an active exam per save."""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

SAVE_KIND = "comptia-study-lab-save"
SAVE_VERSION = 1
ACTIVE_FILE = "active"
DEFAULT_NAME = "default"
SAVE_GLOB = "*.json"

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_name(name: str) -> str:
    name = name.strip().lower()
    if not name:
        raise ValueError("Save name cannot be empty.")
    if not _NAME_RE.match(name):
        raise ValueError(
            "Save names must start with a letter or number and may contain "
            "letters, numbers, dots, dashes, and underscores."
        )
    return name


def save_path(directory: Path, name: str) -> Path:
    return Path(directory) / f"{normalize_name(name)}.json"


def ensure_directory(directory: Path, fallback: Path) -> Path:
    """Use the preferred folder, falling back if it cannot be written."""
    for candidate in (Path(directory), Path(fallback)):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / f".save-probe-{os.getpid()}"
            probe.write_text("probe", encoding="utf-8")
            probe.unlink()
            return candidate
        except OSError:
            continue
    raise OSError("No writable location for save files.")


def _new_data(name: str, exam_id: str) -> dict:
    stamp = now()
    return {
        "kind": SAVE_KIND,
        "version": SAVE_VERSION,
        "name": name,
        "created": stamp,
        "updated": stamp,
        "active_exam": exam_id,
        "progress": {},
        "migrations": [],
    }


def _normalize(data: dict, name: str) -> dict:
    if not isinstance(data, dict):
        data = {}
    data.setdefault("kind", SAVE_KIND)
    data.setdefault("version", SAVE_VERSION)
    data.setdefault("name", name)
    data.setdefault("created", now())
    data.setdefault("updated", now())
    data.setdefault("active_exam", "")
    data.setdefault("progress", {})
    data.setdefault("migrations", [])
    if not isinstance(data["progress"], dict):
        data["progress"] = {}
    return data


def load_save(directory: Path, name: str) -> dict:
    directory = Path(directory)
    name = normalize_name(name)
    path = save_path(directory, name)
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        return _normalize(raw, name)
    data = _new_data(name, "")
    write_save(directory, name, data)
    return data


def write_save(directory: Path, name: str, data: dict) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    name = normalize_name(name)
    data["name"] = name
    data["updated"] = now()
    path = save_path(directory, name)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def list_save_names(directory: Path) -> list[str]:
    directory = Path(directory)
    if not directory.is_dir():
        return []
    names = []
    for path in sorted(directory.glob(SAVE_GLOB)):
        if path.name.startswith("."):
            continue
        try:
            names.append(normalize_name(path.stem))
        except ValueError:
            continue
    return names


def active_name(directory: Path) -> str:
    directory = Path(directory)
    path = directory / ACTIVE_FILE
    try:
        name = normalize_name(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        names = list_save_names(directory)
        name = names[0] if names else DEFAULT_NAME
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path.write_text(name + "\n", encoding="utf-8")
        except OSError:
            pass
    return name


def set_active_name(directory: Path, name: str) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    name = normalize_name(name)
    (directory / ACTIVE_FILE).write_text(name + "\n", encoding="utf-8")


def create_save(directory: Path, name: str, exam_id: str) -> dict:
    directory = Path(directory)
    name = normalize_name(name)
    path = save_path(directory, name)
    if path.exists():
        raise FileExistsError(f"Save {name!r} already exists.")
    data = _new_data(name, exam_id)
    write_save(directory, name, data)
    return data


def delete_save(directory: Path, name: str) -> None:
    directory = Path(directory)
    name = normalize_name(name)
    path = save_path(directory, name)
    if not path.is_file():
        raise FileNotFoundError(f"Save {name!r} does not exist.")
    path.unlink()
    if active_name(directory) == name:
        remaining = list_save_names(directory)
        if remaining:
            set_active_name(directory, remaining[0])
        else:
            set_active_name(directory, DEFAULT_NAME)


def exam_progress(data: dict, exam_id: str) -> dict:
    progress = data.setdefault("progress", {})
    if not isinstance(progress, dict):
        progress = {}
        data["progress"] = progress
    entry = progress.setdefault(exam_id, {})
    if not isinstance(entry, dict):
        entry = {}
        progress[exam_id] = entry
    entry.setdefault("completed", {})
    entry.setdefault("attempts", {})
    if not isinstance(entry["completed"], dict):
        entry["completed"] = {}
    if not isinstance(entry["attempts"], dict):
        entry["attempts"] = {}
    return entry


def completed_count(data: dict, exam_id: str) -> int:
    return len(exam_progress(data, exam_id)["completed"])


def total_completed(data: dict) -> int:
    return sum(
        len(entry.get("completed", {}))
        for entry in data.get("progress", {}).values()
        if isinstance(entry, dict)
    )


def copy_save(directory: Path, source: str, destination: str) -> dict:
    source = normalize_name(source)
    destination = normalize_name(destination)
    src = save_path(directory, source)
    dst = save_path(directory, destination)
    if not src.is_file():
        raise FileNotFoundError(f"Save {source!r} does not exist.")
    if dst.exists():
        raise FileExistsError(f"Save {destination!r} already exists.")
    shutil.copy2(src, dst)
    data = load_save(directory, destination)
    data["name"] = destination
    data["created"] = now()
    write_save(directory, destination, data)
    return data
