"""Registry of the XK0-006 hands-on missions."""
from pathlib import Path
from typing import Callable

from .base import Check, Mission, install_solution
from .domain1 import MISSIONS as DOMAIN1
from .domain2 import MISSIONS as DOMAIN2
from .domain3 import MISSIONS as DOMAIN3
from .domain4 import MISSIONS as DOMAIN4
from .domain5 import MISSIONS as DOMAIN5

MISSIONS: list[Mission] = [*DOMAIN1, *DOMAIN2, *DOMAIN3, *DOMAIN4, *DOMAIN5]
BY_ID = {mission.id: mission for mission in MISSIONS}
BY_NUM = {mission.num: mission for mission in MISSIONS}


def prepare_once(
    setup: Callable[[Path], None] | None,
) -> Callable[[Path], None] | None:
    """Wrap a setup so the fixtures are created exactly once per workspace.

    ``Mission.run_checks`` calls ``prepare`` again before every verification.
    Re-running the fixtures would undo the learner's work (restore a rewritten
    sudoers file, resurrect a shredded secret, dirty a clean Git tree, or
    remove the sticky bit).  The marker keeps the first-run fixtures in place
    and still recreates them if the directory is deleted.
    """

    if setup is None:
        return None

    def guarded(mdir: Path) -> None:
        # Keep the marker outside the mission directory: some missions turn
        # their directory into a Git work tree, where an extra untracked file
        # would make the "working tree is clean" check fail.
        mdir = Path(mdir)
        marker = mdir.parent / f".{mdir.name}.fixtures-ready"
        if marker.exists():
            return
        setup(mdir)
        marker.write_text("fixtures created\n", encoding="utf-8")

    return guarded


for _mission in MISSIONS:
    _mission.setup = prepare_once(_mission.setup)


def get_mission(key: str | int) -> Mission | None:
    """Look a mission up by number (``3`` / ``"3"``) or id (``"xk103"``)."""
    if isinstance(key, int):
        return BY_NUM.get(key)
    key = str(key).strip().lower()
    if key.isdigit():
        return BY_NUM.get(int(key))
    return BY_ID.get(key)


__all__ = [
    "Check",
    "Mission",
    "MISSIONS",
    "BY_ID",
    "BY_NUM",
    "get_mission",
    "install_solution",
]
