"""Burning cells: fire and steam on map cells (list view+0xa94).

Spec: docs/formats/animation.md §4.6, docs/mechanics/lighting.md §3 (all
CONFIRMED).  An entry {cell, counter} lives until the counter reaches 22.
A cell with an object shows projectile 0x0f's sprite (firewall, .16a) after
the object, a water cell projectile 8's (steam) while the counter is below
18; frame = counter >> 1, anchored at the cell centre with the projectile
record's Width/Height halves.  The light it stamps is
graphics.lighting.BURNING_LIGHT_PHASES[counter >> 1].
"""

from ..common import as_fs
from ..graphics.lighting import BURN_TICKS, BURNING_LIGHT_PHASES
from .base import Action, AnimationSet, FrameRef
from .projectiles import load_projectile_records, projectile_paths

FIRE_ID, STEAM_ID = 0x0F, 8
STEAM_TICKS = 18


class BurningSet(AnimationSet):
    """Actions "fire" (22 counts) and "steam" (18 counts); the anchor is the
    cell centre (32 X + 16, 32 Y + 16 - relief).  ref.events carries the
    light value as ("light=<v>",)."""
    kind = "effects"
    blit_mode = "alpha"

    def __init__(self, fire, steam, sprites=None, paths=None, fs=None):
        super().__init__("burning_cells", sprites, paths, fs)
        self.recs = {"fire": fire, "steam": steam}
        self.actions = {name: Action(name, [k >> 1 for k in range(n)], end="once", source=name)
                        for name, n in (("fire", BURN_TICKS), ("steam", STEAM_TICKS))}

    def frame_at(self, action, facing, tick, **kw):
        a = self.actions[action]
        r = self.recs[action]
        if tick >= a.ticks:
            return FrameRef(a.source, -1, False, (0, 0), action, -1)
        ph = a.phases[tick]
        light = BURNING_LIGHT_PHASES[ph] if ph < len(BURNING_LIGHT_PHASES) else None
        return FrameRef(a.source, ph, False, (r["Width"] // 2, r["Height"] // 2), action, ph,
                        events=("light=%d" % light,) if light is not None else ())


def load_burning_set(key, fs=None):
    fs = as_fs(fs)
    recs = load_projectile_records(fs)
    fire, steam = recs[FIRE_ID], recs[STEAM_ID]
    paths = {"fire": projectile_paths(fire, fs)["main"],
             "steam": projectile_paths(steam, fs)["main"]}
    return BurningSet(fire, steam, paths=paths, fs=fs)
