"""Registry of all hands-on missions."""
from .base import Check, Mission, install_solution
from .part1 import MISSIONS as PART1
from .part2 import MISSIONS as PART2
from .part3 import MISSIONS as PART3
from .part4 import MISSIONS as PART4

MISSIONS: list[Mission] = [*PART1, *PART2, *PART3, *PART4]
BY_ID = {m.id: m for m in MISSIONS}
BY_NUM = {m.num: m for m in MISSIONS}


def get_mission(key: str | int) -> Mission | None:
    """Look a mission up by number (``3`` / ``"3"``) or id (``"m03"``)."""
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
