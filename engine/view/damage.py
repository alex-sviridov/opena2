"""Floating damage numbers: the original's "Flying damage" option (docs/engine/combat.md section 8).

Client message `0x73` (`FUN_0040d9b2`) creates a number `old HP - new HP` (`FUN_0045c4ea`) when the option (`view+0xabc`, default on,
registry `GameOptions\\FlyingHP`, Ctrl+L) is on: start offset `x = +/-16 * size` (a unit of the local player to the right, others to the left),
`y = -48 * size`; every view tick (+1 per sim tick, `FUN_0045c67b`) `y -= 2` and `x += 1` (local player's unit) or `x -= 1`; it lives
1000 ms of wall time (`FUN_0045c6cd`); two numbers of one unit created in the same tick are summed (`FUN_0045c801`).  Drawn in the
owner's colour ramp (`0x61fac8 + 32 * colour`) with the small font at the unit's screen position plus the offset.
Pure: no pygame.
"""

from dataclasses import dataclass

from allods2.formats import objects as fobj

from .drawlist import CELL, FLYER_ALTITUDE, unit_position

LIFE_MS = 1000
START_X = 16            # `size << 4`
START_Y = 48            # `size * -0x30`
STEP_X, STEP_Y = 1, 2   # pixels per sim tick


@dataclass
class Floating:
    unit: int           # world id of the victim
    value: int
    colour: int         # human.pal row of the victim's owner (ramp 0x61fac8 + 32 * colour)
    foreign: bool       # not a unit of the viewing player: drifts left
    size: int
    x: int              # offset from the unit's anchor, pixels
    y: int
    born_ms: int
    stamp: int          # sim tick of creation: numbers of one unit and one stamp merge


class FloatingDamage:
    """The list of live numbers (`view+0x3f54`)."""

    def __init__(self):
        self.numbers = []

    def add(self, unit, value, colour, foreign, size, now_ms, stamp):
        """`FUN_0045c801`: merge into a number of the same unit and stamp, else create one."""
        for n in self.numbers:
            if n.unit == unit and n.stamp == stamp:
                n.value += value
                return n
        size = max(size, 1)
        n = Floating(unit, value, colour, foreign, size, -START_X * size if foreign else START_X * size,
                     -START_Y * size, now_ms, stamp)
        self.numbers.append(n)
        return n

    def advance(self, ticks=1):
        """`FUN_0045c67b` once per sim tick: up two pixels, sideways one."""
        for n in self.numbers:
            n.x += -STEP_X * ticks if n.foreign else STEP_X * ticks
            n.y -= STEP_Y * ticks

    def prune(self, now_ms):
        self.numbers = [n for n in self.numbers if now_ms - n.born_ms <= LIFE_MS]

    def visible(self, now_ms):
        return [n for n in self.numbers if now_ms - n.born_ms <= LIFE_MS]


def unit_anchor(world, camera, assets, u):
    """(x, y, size) of unit `u`'s screen position (the foot of its sprite, relief and flyer altitude applied) relative to the view's
    top-left, as the draw list places it (`_unit`); None when its sprite set is unknown."""
    aset = assets.unit_set(u.type_id)
    if aset is None:
        return None
    size = aset.t.TileSize
    X, Y, _, _ = unit_position(u, size)
    z = fobj.ground_height(world.heights, (u.x << 8) | u.sub_x, (u.y << 8) | u.sub_y, size, size)
    alt = FLYER_ALTITUDE if aset.t.Z else 0
    return ((X * CELL) >> 8) - camera.ix, ((Y * CELL) >> 8) - z - alt - camera.iy, size
