"""Units created at run time: the Summon and Control Spirit spells (docs/data/spells.md 9b).

The exe builds the creature object (`FUN_0050dc2b`, or recycles a freed one), initialises it from a template name (`FUN_0050e173`), places it
with `FUN_00510089`, links it into the manager (`FUN_0052b246`), the owner's unit list (`FUN_0052b22a`) and a new group of its own
(`FUN_0052ae43`, `FUN_0052af8c`), cancels it into a stand (`FUN_0056dba1`) and gives the group its order.  Layer 4: reads and writes
`engine.world`.
"""

from dataclasses import replace
from types import SimpleNamespace

from allods2.formats import entities as E

from . import movement as mv
from .triggers import find_place


def template_by_name(world, name):
    """The monster template called `name` (`Squirrel.2`), None when the world has no asset tables or the name is unknown."""
    if world.assets is None:
        return None
    for t in world.assets.unit_stats():
        if t.kind == "monster" and t.name == name:
            return t
    return None


def next_uid(world):
    """A fresh scenario uid (DECISION: the exe's id is a free network id, `FUN_004f8d90`): above every unit, corpse and structure."""
    ids = [u.uid for u in world.units.values()] + [u.uid for u in world.corpses.values()] + [o.uid for o in world.objects.values()]
    return 1 + max(ids + [0])


def spawn_unit(world, tpl, owner, cell, behaviour=8, master=0, fields=None):
    """Create a unit of template `tpl` (a `UnitType`) at the centre of `cell` for player `owner`, with the map-unit behaviour `behaviour` (bit 8 =
    `+0x1a0`, summoned: no loot, no XP).  `fields` replaces template columns of this unit (the raised dead copy their corpse).  The unit is added to
    `world.units` (the update order) and gets a command group of its own, joined but with no order yet; returns the unit."""
    from . import orders
    rec = E.Unit((cell[0] << 8) + 128, (cell[1] << 8) + 128, tpl.unit_type, 0, 0, behaviour, tpl.server_id, owner, 0, 0,
                 E.NO_HP, E.NO_HP, next_uid(world), 0, 0)
    keep = (world.report.units_on_blocked, world.report.units_sharing_cell, list(world.report.unknown_units))
    stats_tpl = tpl
    if fields:
        stats_tpl = replace(tpl, fields={**tpl.fields, **fields})
    # _load_units looks the template up by server id: put the (possibly edited) template in front for this one call
    real = world.assets
    shim = SimpleNamespace(unit_stats=lambda: _Table(stats_tpl), unit_set=real.unit_set)
    world._load_units(SimpleNamespace(units=[rec], item_groups=[]), shim, None, 2)      # difficulty 2: no map-load tweak
    world.report.units_on_blocked, world.report.units_sharing_cell, world.report.unknown_units[:] = keep
    u = world.units[0x6000 + rec.uid]
    u.master = master
    u.squad = -rec.uid              # a group of its own: never a map squad (the `ai_groups` key of a computer owner would join it to squad 0)
    g = orders._new_group(world, owner)
    orders._join(world, g, u)
    return u, g


class _Table:
    """One-template stand-in for the unit table `World._load_units` reads."""

    def __init__(self, tpl):
        self.tpl = tpl

    def lookup(self, human, server_id):
        return self.tpl


def place(world, tpl, owner, x, y, radius, **kw):
    """`FUN_00510089(x, y, radius)` for a unit of `tpl`, then `spawn_unit` on the cell it found; (None, None) when no cell is free."""
    stub = SimpleNamespace(move_type=tpl.movement_type)
    spot = find_place(world, stub, x, y, radius)
    if spot is None:
        return None, None
    return spawn_unit(world, tpl, owner, spot, **kw)


def settle(world, u, g, stand_ground):
    """The tail of both spells: `FUN_0056dba1` (cancel + stand order 0xc), then the group order: `FUN_005709d9(group, 0)` (guard, Summon) or
    `FUN_00570f2b` (cancel + stand ground `FUN_00570b8b`, Control Spirit); the awake map is recomputed (`FUN_0055b5f1`)."""
    from . import ai, orders
    mv.set_stand(world, u)
    if stand_ground:
        orders.stop_group(world, g)
    else:
        orders.guard_group(world, g, 0)
    if world.ai_on:
        ai.wake(world)
