"""The player's party at map start (docs/engine/triggers.md section 9; exe `FUN_004f2c83`).

The campaign maps hold no hero of the human player: the exe keeps the party (main hero first) in the player's unit list, built
from the campaign state, and places the units that are not yet on the map at a "Drop Location" cell when the ready message
(type 4) arrives.  `place_party` builds a fresh campaign start (the hero state of later maps lives in the save: open question)
and places it exactly like the exe: one drop cell drawn at random, the main hero on it (radius 0, else in the radius), the
others in the radius `max(5, trunc(sqrt(n) + 4))` of it, every search by `FUN_00510089` (`engine.sim.place.find_place`).
"""

import math
from dataclasses import replace
from types import SimpleNamespace

from allods2.formats import entities as E
from allods2.formats import progression as prog

from .sim.place import find_place

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


_PROG = prog.Progression()
ATTRS = ("body", "reaction", "mind", "spirit")


def start_key(record):
    """`MF`/`MM`/`FF`/`FM` of a character record: the template `Start_xx` chosen by `identity.flags & 0xc0` (FUN_004ea6ab)."""
    return record.identity.template[-2:]


def apply_record(unit, owner, record):
    """Rebuild a freshly created `Start_*` hero from a decoded character record, in the order of FUN_004ea6ab (docs/formats/saves.md
    section 3): the four base attributes, the five school XP pools (skills 1..5 = `thr` inverse of the pools, skill 0 stays),
    the best school, the spell book mask, then the recompute (HP and mana at their maxima), the player's gold and statistics, and
    the 12 equipped items / the pack.  Equipment effects on the stats are not modelled yet (the engine has no equip system)."""
    st = record.stats
    tpl = unit.stats
    if tpl is not None:
        fields = dict(tpl.fields)
        fields.update(zip(ATTRS, st.attributes))
        tpl = replace(tpl, fields=fields)
        unit.stats = tpl
    unit.xp = tuple(st.school_xp)
    unit.xp_total = sum(unit.xp)
    base = unit.skills or (0,) * 6
    unit.skills = (base[0],) + tuple(_PROG.level_of(x) for x in unit.xp)
    unit.best_school = record.identity.school
    unit.name = record.identity.name.split("|")[0]        # the hero's name (+0x80, FUN_004ea6ab / FUN_004ead6b)
    unit.spellbook = st.spells
    if tpl is not None:
        unit.hp_max, unit.mana_max = prog.derived_vitals(tpl, unit.skills, total=unit.xp_total)
    unit.hp, unit.mana = unit.hp_max, unit.mana_max
    unit.equipment = tuple(record.equipment.items) if record.equipment else ()
    unit.pack = tuple(record.pack.items) if record.pack else ()
    unit.carried = tuple(i.code for i in unit.pack)
    owner.gold = st.gold
    owner.hero_deaths = st.hero_deaths
    owner.kills_monsters, owner.kills_players = st.kills_monsters, st.kills_players
    return unit


def on_map(world, unit):
    """`FUN_0055641c(map, unit+0x10) == unit` (-> `FUN_00551edb`, CONFIRMED): the unit already stands on the map when the ground occupant slot
    (cell record `+4`) of its own cell holds it.  `FUN_004f2c83` skips such units; a unit that lost a first-come race for its cell would be
    placed again (no map has one; the engine places only the units it creates)."""
    from engine.cellslots import pack
    return world.slots.occ[0].get(pack(unit.x, unit.y)) == unit.id


def place_party(world, assets, drops, count=1, start="MF", owner=None, record=None):
    """Create the party of the human player and place it at the drop cells; returns the list of placed units (main hero first).

    `record` (a `saves.Character`): the main hero is built from the character record instead of the fresh start template
    (template from the record's flags, `apply_record`); the other members stay the recruitable heroes.

    Does nothing (returns []) when the player already has a main hero.  Sets `Player.main_hero`.  The exe's unit uid is a free
    network id; here `max(unit / structure uid) + 1 + k` (DECISION), the scenario hero number comes from the template (+0x14c)."""
    if owner is None:
        owner = next((p for _, p in sorted(world.players.items()) if p.human), None)
    if owner is None or owner.main_hero:
        return []
    types = assets.unit_stats()
    if record is not None:
        start = start_key(record)
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
        stub = SimpleNamespace(move_type=tpl.movement_type, stats=tpl)
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
            if record is not None:
                apply_record(u, owner, record)
        placed.append(u)
    return placed
