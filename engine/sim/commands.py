"""Commands: the only way input reaches the simulation."""

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    """Base class; concrete commands come with the systems that run them."""


@dataclass(frozen=True)
class SelectUnits(Command):
    """Set (or, with `toggle`, toggle) a player's selection; empty `unit_ids` clears it."""
    player_id: int
    unit_ids: tuple
    toggle: bool = False

    def __post_init__(self):
        object.__setattr__(self, "unit_ids", tuple(self.unit_ids))


class CommandQueue:
    def __init__(self):
        self._q = deque()

    def put(self, cmd):
        self._q.append(cmd)

    def drain(self):
        out = list(self._q)
        self._q.clear()
        return out

    def __len__(self):
        return len(self._q)
