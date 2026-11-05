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
class Guard(Command):
    """Exe command 0x17 (key G, guard): new command group, members order 0xb on their anchor, group order 1 (`FUN_005709d9`)."""
    player_id: int
    unit_ids: tuple

    def __post_init__(self):
        object.__setattr__(self, "unit_ids", tuple(self.unit_ids))


@dataclass(frozen=True)
class StandStill(Command):
    """Exe command 0x12 (key L, stand still): members order 0x17, group order 0x13 (`FUN_00570bde`)."""
    player_id: int
    unit_ids: tuple

    def __post_init__(self):
        object.__setattr__(self, "unit_ids", tuple(self.unit_ids))


@dataclass(frozen=True)
class Retreat(Command):
    """Exe command 0x14 (key R / bar button 8, `FUN_00419e72`): members order 0x16, Brain mode 0, group order 0 (`FUN_00570c31`); the order has no
    end of its own (docs/engine/simulation.md 9.3)."""
    player_id: int
    unit_ids: tuple

    def __post_init__(self):
        object.__setattr__(self, "unit_ids", tuple(self.unit_ids))


@dataclass(frozen=True)
class SetRetreatMode(Command):
    """Exe message `0x46` sub-code 1 (`FUN_0041a4ef`, Ctrl+W; server `0x4f67d5`): the player's retreat mode 0 / 1 / 2 = x 0 / 10 / 30 percent; every
    unit the player owns gets wimpy = maxHP * x / 100 and withdraw = 0 (`FUN_00573b38`, `FUN_0057393c`)."""
    player_id: int
    mode: int


@dataclass(frozen=True)
class Swarm(Command):
    """Exe command 0x1a (swarm, key S then a click, or Ctrl+click): the move group code with group order 5 (`FUN_0057063e`)."""
    player_id: int
    unit_ids: tuple
    cell: tuple

    def __post_init__(self):
        object.__setattr__(self, "unit_ids", tuple(self.unit_ids))
        object.__setattr__(self, "cell", (int(self.cell[0]), int(self.cell[1])))


@dataclass(frozen=True)
class SetFormation(Command):
    """Exe command 0x46 sub-code 2: the player's formation option, client mode 0 off, 1 auto, 2 on."""
    player_id: int
    mode: int


@dataclass(frozen=True)
class SetAutoCast(Command):
    """Exe message `0x46` sub-code 3 (`0x4f6945`; the client sends it at the game start and when the Options dialog or the auto-cast key changes it,
    `FUN_0041a5b9`): the party-AI byte of the player, docs/engine/ai.md 12.8.  Bits 8 / 0x10 / 0x20 = heal / buffs / protections, 1 / 2 / 4 = own /
    allied / neutral friends."""
    player_id: int
    flags: int


@dataclass(frozen=True)
class SetAutoSpell(Command):
    """Exe message `0x46` sub-code 4 (Ctrl+A, `FUN_0041a727`; server `0x4f694d`): unit `unit_id` of the player toggles its selected spell
    `brain+0x78`: equal to `spell` -> 0, else `spell`.  docs/engine/ai.md 12.8."""
    player_id: int
    unit_id: int
    spell: int


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


@dataclass(frozen=True)
class CastSpell(Command):
    """Exe command `0x1e` (cast at a unit; docs/data/spells.md 9c.1): the player's units that know spell `spell_id` (a bit of their spellbook) cast it
    at unit `target_id`; the others of the group are only cancelled.  With `cell` = (x, y) (and `target_id` None) it is command `0x1f`, the cast at a
    cell (order 0xe; only spells with `target == 2`).  `ai=True`: the AI's brain-level cast (`FUN_0056c72b` mode 8 at the unit, `FUN_0056969c` mode 9 at
    the cell; docs/engine/ai.md 12): no group, no cancel, order kept, `brain+0x60 := 1`."""
    player_id: int
    unit_ids: tuple
    spell_id: int
    target_id: int = None
    ai: bool = False
    cell: tuple = None

    def __post_init__(self):
        object.__setattr__(self, "unit_ids", tuple(self.unit_ids))
        if self.cell is not None:
            object.__setattr__(self, "cell", (int(self.cell[0]), int(self.cell[1])))


@dataclass(frozen=True)
class CastScroll(Command):
    """Exe commands `0x25` (at a unit, `target_id`) and `0x26` (at a cell, `cell`) (`FUN_004f515d` case `0x4f5825`; client `0x419753`..): the unit casts the
    spell of the backpack item `index` (the item panel's selected entry, `msg+0x10`) of its own pack: one piece is taken out of the pack (a stack
    loses one), the cast level is the item's charges and no mana is paid.  docs/data/spells.md 9c.5."""
    player_id: int
    unit_id: int
    index: int
    target_id: int = None
    cell: tuple = None

    def __post_init__(self):
        if self.cell is not None:
            object.__setattr__(self, "cell", (int(self.cell[0]), int(self.cell[1])))


@dataclass(frozen=True)
class PickUp(Command):
    """Exe command `0x21` (cell target, `msg+0xe` = the pack index where the items go): the last unit of the selection walks to the sack on `cell` and
    files it in its pack; "Sack not found" (nothing happens) when the cell holds none.  Intake and order: sim/gear.py."""
    player_id: int
    unit_ids: tuple
    cell: tuple
    index: int = 0x7FFF

    def __post_init__(self):
        object.__setattr__(self, "unit_ids", tuple(self.unit_ids))
        object.__setattr__(self, "cell", (int(self.cell[0]), int(self.cell[1])))


@dataclass(frozen=True)
class MoveItem(Command):
    """Server message `0x22` (client `FUN_0041a20c`): move an item between the hero's containers.  Kinds: 1 equipment slot (`index + 1`), 2 pack entry,
    3 ground sack; `count` splits a stack.  Shop kinds 4..8 are not modelled.  Semantics: `gear.move_item`."""
    player_id: int
    unit_id: int
    src_kind: int
    dst_kind: int
    src_index: int = 0
    dst_index: int = 0
    count: int = 1


@dataclass(frozen=True)
class DropGold(Command):
    """Server message `0x23`: drop `amount` of the player's gold at `cell` (or at the first unit's cell when the target is further than 2 cells)."""
    player_id: int
    unit_ids: tuple
    amount: int
    cell: tuple

    def __post_init__(self):
        object.__setattr__(self, "unit_ids", tuple(self.unit_ids))
        object.__setattr__(self, "cell", (int(self.cell[0]), int(self.cell[1])))
