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


@dataclass(frozen=True)
class MoveUnits(Command):
    """Exe command 0x16: the player's units walk to `cell` = (x, y) in map cells (border included).
    Intake: docs/engine/simulation.md "Orders (H3)"."""
    player_id: int
    unit_ids: tuple
    cell: tuple
    ai: bool = False                # issued by the AI (docs/engine/ai.md 10): the brain-level `FUN_0056c8af`, no new command group

    def __post_init__(self):
        object.__setattr__(self, "unit_ids", tuple(self.unit_ids))
        object.__setattr__(self, "cell", (int(self.cell[0]), int(self.cell[1])))


@dataclass(frozen=True)
class AttackUnit(Command):
    """Exe command 0x19 (object target, `msg+0xe`): the player's units attack unit `target_id`.  Intake and effect: docs/engine/combat.md
    section 2."""
    player_id: int
    unit_ids: tuple
    target_id: int
    ai: bool = False                # AI: the brain-level mode 5 of `FUN_0056acc8` (order, anchor and group untouched)

    def __post_init__(self):
        object.__setattr__(self, "unit_ids", tuple(self.unit_ids))


@dataclass(frozen=True)
class Stop(Command):
    """Exe command 0x18 (key T, stand ground): cancel the walk, order 0xc."""
    player_id: int
    unit_ids: tuple
    ai: bool = False                # AI: brain mode 0 (`FUN_0056b025`), the unit keeps its order and group

    def __post_init__(self):
        object.__setattr__(self, "unit_ids", tuple(self.unit_ids))


@dataclass(frozen=True)
class SetFormation(Command):
    """Exe command 0x46 sub-code 2: the player's formation option, client mode 0 off, 1 auto, 2 on."""
    player_id: int
    mode: int


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
