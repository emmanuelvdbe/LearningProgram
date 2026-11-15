"""Turn CompTIA objective documents into readable text using only stdlib."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".markdown", ".rst", ".docx", ".json"}
TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".rst", ".json"}
INDEX_NAME = "_index.json"
TEXT_DIR = "_text"


@dataclass
class Extraction:
    source: Path
    status: str
    text: str = ""
    output: Path | None = None
    error: str = ""

    @property
    def chars(self) -> int:
        return len(self.text)


def _extract_pdf(path: Path) -> tuple[str, str]:
    tool = shutil.which("pdftotext")
    if tool is None:
        return "", (
            "pdftotext not installed. Install poppler-utils, or save the "
            "objectives as .txt/.md and scan again."
        )
    try:
        result = subprocess.run(
            [tool, "-layout", "-enc", "UTF-8", str(path), "-"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "", f"pdftotext failed: {exc}"
    if result.returncode != 0:
        error = (result.stderr or "pdftotext returned a non-zero status").strip()
        return result.stdout, error
    return result.stdout, ""


def _extract_docx(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            with archive.open("word/document.xml") as handle:
                tree = ElementTree.parse(handle)
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        return "", f"could not read .docx: {exc}"

    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in tree.iter(f"{namespace}p"):
        pieces = [
            node.text or ""
            for node in paragraph.iter(f"{namespace}t")
        ]
        line = "".join(pieces).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs), ""


def extract_text(path: Path) -> tuple[str, str]:
    """Return ``(text, error)`` for one objectives file."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix in TEXT_SUFFIXES:
        try:
            return path.read_text(encoding="utf-8", errors="replace"), ""
        except OSError as exc:
            return "", str(exc)
    return "", f"unsupported file type {suffix or '(none)'}"


def _safe_relative(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return Path(path.name)


def _output_path(root: Path, source: Path) -> Path:
    relative = _safe_relative(source, root)
    return root / TEXT_DIR / relative.with_suffix(relative.suffix + ".txt")


def _write_output(root: Path, source: Path, text: str) -> Path:
    destination = _output_path(root, source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"SOURCE: {source}\n"
        f"EXTRACTED: {datetime.now().isoformat(timespec='seconds')}\n"
        + "-" * 72
        + "\n\n"
    )
    destination.write_text(header + text.rstrip() + "\n", encoding="utf-8")
    return destination


def _is_instructions(path: Path) -> bool:
    return path.stem.lower() == "readme"


def scan_objectives(directory: Path) -> list[Extraction]:
    """Extract every supported document in ``directory`` into ``_text/``.

    The scan is idempotent: generated text always lands under `_text/`, which
    is skipped on the next pass.  An index is written next to the documents.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    results: list[Extraction] = []
    for source in sorted(directory.rglob("*")):
        if not source.is_file():
            continue
        if TEXT_DIR in source.parts or source.name == INDEX_NAME:
            continue
        if source.name.startswith(".") or _is_instructions(source):
            continue
        if source.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue

        text, error = extract_text(source)
        extraction = Extraction(source=source, status="extracted", text=text)
        if error:
            extraction.status = "partial" if text else "failed"
            extraction.error = error
        if text:
            extraction.output = _write_output(directory, source, text)
        results.append(extraction)

    index = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "directory": str(directory),
        "sources": [
            {
                "file": str(item.source.relative_to(directory)),
                "status": item.status,
                "chars": item.chars,
                "output": (
                    str(item.output.relative_to(directory))
                    if item.output is not None
                    else None
                ),
                "error": item.error,
            }
            for item in results
        ],
    }
    (directory / INDEX_NAME).write_text(
        json.dumps(index, indent=2) + "\n", encoding="utf-8"
    )
    return results


def read_objective_text(directory: Path) -> list[tuple[str, str]]:
    """Return readable texts for an exam, preferring extracted `_text/` files."""
    directory = Path(directory)
    text_root = directory / TEXT_DIR
    if text_root.is_dir():
        chunks: list[tuple[str, str]] = []
        for path in sorted(text_root.rglob("*.txt")):
            if path.name.lower().startswith("readme"):
                continue
            try:
                chunks.append((str(path.relative_to(text_root)), path.read_text(
                    encoding="utf-8", errors="replace"
                )))
            except OSError:
                continue
        if chunks:
            return chunks

    chunks = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.name == INDEX_NAME:
            continue
        if TEXT_DIR in path.parts or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if _is_instructions(path):
            continue
        try:
            chunks.append((str(path.relative_to(directory)), path.read_text(
                encoding="utf-8", errors="replace"
            )))
        except OSError:
            continue
    return chunks


def clean_text(text: str) -> str:
    """Collapse common PDF extraction noise for quick terminal reading."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
