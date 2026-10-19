"""The player's party at map start (docs/engine/triggers.md section 9; exe `FUN_004f2c83`).

The campaign maps hold no hero of the human player: the exe keeps the party (main hero first) in the player's unit list, built
from the campaign state, and places the units that are not yet on the map at a "Drop Location" cell when the ready message
(type 4) arrives.  `place_party` builds a fresh campaign start (the hero state of later maps lives in the save: open question)
and places it exactly like the exe: one drop cell drawn at random, the main hero on it (radius 0, else in the radius), the
others in the radius `max(5, trunc(sqrt(n) + 4))` of it, every search by `FUN_00510089` (`engine.sim.triggers.find_place`).
"""

import math
from types import SimpleNamespace

from allods2.formats import entities as E

from .sim.triggers import find_place

# data.bin server ids of the hero templates (docs/data/progression.md section 6); +0x14c = (id / 10) % 1000 = 21, 22, 23
# = scenario hero numbers 10001, 10002, 10003 (FUN_00562518).  The main hero is a `Start_*` (FUN_004f254b picks it from the
# creation screen's class / gender bits: MF = fighter male, FF, MM, FM).
START = {"MF": 10210, "FF": 10211, "MM": 10212, "FM": 10213}
FIGHTER_HERO, MAGE_HERO = 10220, 10230
FALLBACK_BASE, FALLBACK_SPAN = 0x1E, 0x46        # no drop cell: x = rand(0x46) + 0x1e, y likewise (FUN_004f2c83 0x4f2e2e)


def party_ids(count=1, start="MF"):
    """Server ids of the first `count` party members: the main hero, then the two recruitable heroes (a campaign save holds them
    after the story recruited them; a fresh start only has the main hero)."""
    return [START[start], FIGHTER_HERO, MAGE_HERO][:count]


def spread(n):
    """The search radius of the non-main members: `ftol(max(5.0, sqrt(n) + 4.0))`, n = units in the player's list (0x4f2e72-0x4f2ee2)."""
    return int(max(5.0, math.sqrt(n) + 4.0))


def drop_cell(world, drops):
    """The cell the party is placed around: `drops[rand(len - 1)]` (one draw per placement, none for a single cell), or when the
    list is empty or the cell has a zero coordinate two draws `rand(0x46) + 0x1e` (the exe logs a warning)."""
    x = y = 0
    if drops:
        x, y = drops[world.rng.rand(len(drops) - 1)]
    if x * y == 0:
        x = world.rng.rand(FALLBACK_SPAN) + FALLBACK_BASE
        y = world.rng.rand(FALLBACK_SPAN) + FALLBACK_BASE
    return x & 0xFF, y & 0xFF


def place_party(world, assets, drops, count=1, start="MF", owner=None):
    """Create the party of the human player and place it at the drop cells; returns the list of placed units (main hero first).

    Does nothing (returns []) when the player already has a main hero.  Sets `Player.main_hero`.  The exe's unit uid is a free
    network id; here `max(unit / structure uid) + 1 + k` (DECISION), the scenario hero number comes from the template (+0x14c)."""
    if owner is None:
        owner = next((p for _, p in sorted(world.players.items()) if p.human), None)
    if owner is None or owner.main_hero:
        return []
    types = assets.unit_stats()
    ids = party_ids(count, start)
    uid0 = 1 + max([u.uid for u in world.units.values()] + [o.uid for o in world.objects.values()] + [0])
    n = len([u for u in world.units.values() if u.owner == owner.id]) + len(ids)
    x, y = drop_cell(world, drops)
    r = spread(n)
    placed = []
    for k, sid in enumerate(ids):
        tpl = types.lookup(True, sid)
        if tpl is None:
            raise ValueError("hero template %d is not in data.bin" % sid)
        stub = SimpleNamespace(move_type=tpl.movement_type)
        spot = (find_place(world, stub, x, y, 0) if k == 0 else None) or find_place(world, stub, x, y, r)
        if spot is None:
            continue                        # the exe logs "can't place unit" and goes on (FUN_004f2c83 0x4f2fb3)
        rec = E.Unit((spot[0] << 8) + 128, (spot[1] << 8) + 128, tpl.unit_type, 0, E.HUMAN_FLAG, 0, sid, owner.id, 0, 0,
                     E.NO_HP, E.NO_HP, uid0 + k, 0, 0)
        keep = (world.report.units_on_blocked, world.report.units_sharing_cell)
        world._load_units(SimpleNamespace(units=[rec], item_groups=[]), assets, None)
        world.report.units_on_blocked, world.report.units_sharing_cell = keep
        u = world.units[0x6000 + uid0 + k]
        if k == 0:
            owner.main_hero = u.id          # FUN_004f254b: owner+0x38 := the new hero
        placed.append(u)
    return placed
