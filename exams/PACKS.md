# Building a curriculum pack

A new exam becomes fully studyable when it has a curriculum pack. Until then
it is **objectives-only**: selectable, readable, and tracked per save slot.

## Pack contract

Two complete packs ship with the platform:

- `curriculum/` — CompTIA Linux+ XK0-005 (16 modules, the built-in original).
- `exams/linux-plus-xk0-006/pack/` — CompTIA Linux+ XK0-006 (22 modules,
  package-style, loaded from the exam folder).

The XK0-006 pack is the best template for a new exam. It keeps the syllabus,
lessons, and missions together next to the manifest:

Create `exams/<exam-id>/pack/` with either `pack.py` or `__init__.py`:

```
exams/security-plus-sy0-701/
    exam.json
    pack/
        __init__.py
        lessons/
            01_....md
        missions/
            __init__.py
            part1.py
    objectives/
```

Set `"curriculum": "pack"` and `"status": "ready"` in `exam.json`.

The pack module must expose:

```python
MODULES: list[dict]        # same shape as curriculum/syllabus.py
MISSIONS: list[Mission]    # same shape as curriculum/missions/
LESSON_DIR: Path           # folder containing the lesson markdown files

def lesson_path(module: dict) -> Path: ...
def get_mission(key): ...  # number or id
```

`Mission`, `Check`, and the shared helpers live in
`curriculum/missions/base.py`; a new pack can reuse them:

```python
from curriculum.missions.base import Check, Mission, fresh_dir, run_script
```

Each module dict follows the existing pattern:

```python
{
    "num": 1,
    "id": "sp01",
    "part": "Part I — ...",
    "title": "Security controls in Python",
    "lesson": "01_controls.md",
    "domain": "Security+ 1.1",
    "summary": "One-line description.",
    "minutes": 60,
}
```

### Missions whose work is a command sequence

Most missions are verified from files a learner writes. Some are better
expressed as commands: `git commit`, `chmod`, `python3 -m venv`,
`openssl req`. Those can set the optional `Mission.post_install` hook, which
runs only when the **reference solution** is installed:

```python
Mission(
    ...,
    solution={"build.sh": BUILD_SCRIPT},
    post_install=lambda mdir: run_command(["/bin/bash", str(mdir / "build.sh")]),
)
```

`run_checks` calls `prepare` before every verification, so fixtures must be
idempotent. The XK0-006 pack wraps each setup in `prepare_once()`, which stores
a marker outside the mission directory and recreates fixtures only when the
directory is deleted. That survives a learner who changes permissions, commits
a Git tree, or shreds a file on purpose.

The GUI terminal mounts the directory returned by `prepare()` at `/workspace`
and runs the same checker on the host afterwards. A mission therefore works in
both the CLI and the GUI as long as the checker reads the workspace path it is
given instead of a hard-coded location.

## Suggested build loop

1. Drop the official objectives in `exams/_inbox/`.
2. `exam add` and `exam attach` the document.
3. `exam scan <id>` and read `objectives/_text/`.
4. Group objectives into 8–20 modules.
5. Write one lesson per module with real examples and Linux/CLI context.
6. Write one mission per module with fixtures, a checker, hints, and a
   reference solution.
7. Set `"curriculum": "pack"` in `exam.json`.
8. Run `python3 -m unittest discover -s tests -v`.
9. Verify every reference solution through the CLI:
   `python3 main.py solution N --write`, copy it into the workspace, then
   `python3 main.py verify N`.

Do not generate multiple-choice question banks. The value of this platform is
that a mission proves a real, inspectable result.
