"""The player's party at map start (docs/engine/triggers.md section 9; exe `FUN_004f2c83`).

The campaign maps hold no hero of the human player: the exe keeps the party (main hero first) in the player's unit list, built
from the campaign state, and places the units that are not yet on the map at a "Drop Location" cell when the ready message
(type 4) arrives.  `place_party` builds a fresh campaign start (the hero state of later maps lives in the save: open question)
and places it exactly like the exe: one drop cell drawn at random, the main hero on it (radius 0, else in the radius), the
others in the radius `max(5, trunc(sqrt(n) + 4))` of it, every search by `FUN_00510089` (`engine.sim.place.find_place`).
"""

import copy
import math
from dataclasses import dataclass, replace
from types import SimpleNamespace

from allods2.formats import entities as E
from allods2.formats import progression as prog
from allods2.formats import unitstats as U

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


def apply_record(unit, owner, record, world=None):
    """Rebuild a freshly created `Start_*` hero from a decoded character record, in the order of FUN_004ea6ab (docs/formats/saves.md
    section 3): the four base attributes, the five school XP pools (skills 1..5 = `thr` inverse of the pools, skill 0 stays),
    the best school, the spell book mask, then the recompute (HP and mana at their maxima), the player's gold and statistics, and
    the 12 equipped items / the pack (step 6, `engine/sim/gear.py`): without a `world` item table the items are only stored (slot i = record item
    i, nothing resolves); with one each item is put through the equip method (`gear.put`: a hero equips what it may use, a refused or replaced item goes
    to the pack at the end), so the equipment's effects reach the combat numbers, the speed, the maximum HP / mana and the spell level."""
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
    items = list(record.equipment.items) if record.equipment else []
    pack_items = list(record.pack.items) if record.pack else []
    table = world.item_table if world is not None else None
    if table is None:
        unit.equipment = tuple(items)
        unit.pack = tuple(pack_items)
        unit.carried = tuple(i.code for i in unit.pack)
    else:
        from .sim import gear
        unit.equipment = tuple(gear.EMPTY for _ in range(gear.SLOT_COUNT))      # step 6: the template's equipment goes (a new, empty pack)
        unit.pack = ()
        unit.pack_index = gear.APPEND
        for it in items:
            if it.code:
                gear.put_and_file(world, unit, it)              # vtable +0x44
        for it in pack_items:
            gear._file(world, unit, it)                         # FUN_00529ac2 per pack item
        gear.sync_carried(unit)
        gear.recompute(world, unit)
        unit.hp, unit.mana = unit.hp_max, unit.mana_max
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


# --- the carried roster (docs/engine/campaign.md; docs/formats/saves.md section 4) -----------------------------------------------------------

BUDGET = 0x8C                       # FUN_004f254b: the creation point budget; cost(v) = trunc(0.349 * (v - 1) ^ 1.15 + 0.5) (FUN_004f250e)
SCHOOL_WEAPONS = {1: "Iron Long Sword", 2: "Iron Axe", 3: "Iron Mace", 4: "Iron Pike", 5: "Uncommon Wood Long Bow"}
SCHOOL_STAFFS = {1: "Fire Arrow", 2: "Ice Missile", 3: "Lightning", 4: "Diamond Dust", 5: "Drain Life"}
# the unit fields a hero keeps from mission to mission (saves.md section 4: level / XP / skills / pools / items / spells / name / hero number)
CARRY = ("server_id", "type_id", "human", "move_type", "face", "stats", "skills", "xp", "xp_total", "best_school", "mana_max", "hp_max", "spellbook",
         "name", "equipment", "pack", "pack_index", "carried", "carried_mods", "skill_bonus", "attr_bonus", "gear_speed", "kill_list", "speed_mod",
         "auto_spell", "wimpy_hp", "withdraw_hp", "hero_no")


def attribute_cost(v):
    return int(0.349 * (v - 1) ** 1.15 + 0.5)


@dataclass
class HeroSpec:
    """The arguments of `FUN_004f254b` for a hero that does not exist yet: `attributes` (body, reaction, mind, spirit; all 25 when the point budget
    does not hold), `school` 1..5 (None = the template's own), `name`."""
    attributes: tuple = None
    school: int = None
    name: str = ""


@dataclass
class RosterEntry:
    """One unit of the human's list that is not a map unit: `number` = `+0x14c`, `server_id` = the data.bin template, `net_id` = `unit+4`, `state` = the
    carried fields of the unit (`CARRY`, a `SimpleNamespace`) or None while the hero was never in a world (then `spec` builds it)."""
    number: int
    server_id: int
    human: bool = True
    net_id: int = 0
    state: object = None
    spec: HeroSpec = None


@dataclass
class Roster:
    """What a campaign map starts with instead of a fresh party: the entries in list order (main hero first, the carried heroes, then the hired
    mercenaries), the player's gold and statistics."""
    entries: list
    gold: int = 0
    hero_deaths: int = 0
    kills_monsters: int = 0
    kills_players: int = 0


def hero_number(u):
    """`+0x14c`: the number a recruit / hire wrote (`Unit.hero_no`), else a human's server id above 10000 reduced to `(id / 10) % 1000` (units.md)."""
    v = u.server_id
    return u.hero_no or ((v // 10) % 1000 if u.human and v > 10000 else v)


def _dup(v):
    """A copy of a carried value; the template (`stats`, replaced never mutated) is shared."""
    return v if isinstance(v, U.UnitType) else copy.deepcopy(v)


def capture(u):
    """The carried state of a unit: a deep copy of the `CARRY` fields (HP / mana are not part of it: the carry-over sets them to the maxima)."""
    return SimpleNamespace(**{k: _dup(getattr(u, k)) for k in CARRY})


def restore(world, u, state):
    """Put a carried state on a freshly created unit of the same template; HP and mana at the maxima (FUN_004ebd5f step 6), effects, orders and targets
    clear as the new unit has them."""
    for k in CARRY:
        setattr(u, k, _dup(getattr(state, k)))
    u.combat = None
    if world.item_table is not None and u.human and u.stats is not None:
        from .sim import gear
        gear.recompute(world, u)
    u.hp, u.mana = u.hp_max, u.mana_max


def apply_spec(world, u, spec):
    """A fresh hero of the creation call (`FUN_004f254b`, triggers.md 9.3): attributes when the budget holds (else 25 each), the school skill 20 and
    the shooting skill 10 (`FUN_00514f59`; INFERRED: school 5 = the bow keeps 20), the pools, the best school and the school's weapon / staff."""
    if spec.name:
        u.name = spec.name
    if spec.attributes is not None:
        attrs = tuple(spec.attributes)
        if sum(attribute_cost(v) for v in attrs) > BUDGET:
            attrs = (25, 25, 25, 25)
        fields = dict(u.stats.fields)
        fields.update(zip(ATTRS, attrs))
        u.stats = replace(u.stats, fields=fields)
    if spec.school is not None:
        sk = [u.skills[0], 0, 0, 0, 0, 0]
        sk[5] = 10
        sk[spec.school] = 20
        u.skills = tuple(sk)
        u.xp, u.xp_total = prog.start_pools(u.skills)
        u.best_school = spec.school
    if world.item_table is not None:
        from .sim import combatstats as cs, gear
        gear.ensure_loadout(world, u)
        if spec.school is not None:
            mage = gear.is_mage(u)
            text = SCHOOL_WEAPONS[spec.school] if not mage else "Uncommon Wood Staff {castSpell=%s:1}" % SCHOOL_STAFFS[spec.school]
            r = world.item_table.parse_equipment(text, 0)
            item = world.item_table.resolve(*r) if r else None
            if item is not None:
                gear.take_slot(world, u, 1)
                gear.put_and_file(world, u, gear.make_item(world.item_table, cs.item_code(item), item.effects))
                gear.sync_carried(u)
        gear.recompute(world, u)
    if world.item_table is None and u.stats is not None and u.skills:
        u.hp_max, u.mana_max = prog.derived_vitals(u.stats, u.skills, total=u.xp_total)
    u.hp, u.mana = u.hp_max, u.mana_max


def place_party(world, assets, drops, count=1, start="MF", owner=None, record=None, roster=None):
    """Create the party of the human player and place it at the drop cells; returns the list of placed units (main hero first).

    `record` (a `saves.Character`): the main hero is built from the character record instead of the fresh start template
    (template from the record's flags, `apply_record`); the other members stay the recruitable heroes.

    Does nothing (returns []) when the player already has a main hero.  Sets `Player.main_hero`.  The exe's unit uid is a free
    network id; here `max(unit / structure uid) + 1 + k` (DECISION), the scenario hero number comes from the template (+0x14c).

    `roster` (a `Roster`, the campaign): the entries replace the fresh party, in list order, each from its template (`server_id`, human or monster), then
    its carried `state` (`restore`) or its `spec` (`apply_spec`); the first entry is the main hero; the player's gold and statistics come from the
    roster.  Placement, the radius and the draws are those of the fresh party."""
    if owner is None:
        owner = next((p for _, p in sorted(world.players.items()) if p.human), None)
    if owner is None or owner.main_hero:
        return []
    types = assets.unit_stats()
    if record is not None:
        start = start_key(record)
    if roster is not None:
        plan = [(e.server_id, e.human, e) for e in roster.entries]
    else:
        plan = [(sid, True, None) for sid in party_ids(count, start)]
    ids = plan
    uid0 = 1 + max([u.uid for u in world.units.values()] + [o.uid for o in world.objects.values()] + [0])
    n = len([u for u in world.units.values() if u.owner == owner.id]) + len(ids)
    x, y = drop_cell(world, drops)
    r = spread(n)
    placed = []
    for k, (sid, human, entry) in enumerate(plan):
        tpl = types.lookup(human, sid)
        if tpl is None:
            raise ValueError("hero template %d is not in data.bin" % sid)
        stub = SimpleNamespace(move_type=tpl.movement_type, stats=tpl)
        spot = (find_place(world, stub, x, y, 0) if k == 0 else None) or find_place(world, stub, x, y, r)
        if spot is None:
            continue                        # the exe logs "can't place unit" and goes on (FUN_004f2c83 0x4f2fb3)
        rec = E.Unit((spot[0] << 8) + 128, (spot[1] << 8) + 128, tpl.unit_type, 0, E.HUMAN_FLAG if human else 0, 0, sid, owner.id, 0, 0,
                     E.NO_HP, E.NO_HP, uid0 + k, 0, 0)
        keep = (world.report.units_on_blocked, world.report.units_sharing_cell)
        world._load_units(SimpleNamespace(units=[rec], item_groups=[]), assets, None)
        world.report.units_on_blocked, world.report.units_sharing_cell = keep
        u = world.units[0x6000 + uid0 + k]
        u.net_id = (entry.net_id if entry is not None and entry.net_id else 0) or world.net_ids.alloc()    # `FUN_004f254b` / `FUN_004f312a`: `unit+4` = the lowest free id (engine/netids.py)
        if k == 0:
            owner.main_hero = u.id          # FUN_004f254b: owner+0x38 := the new hero
            if record is not None:
                apply_record(u, owner, record, world)
        if entry is not None:
            u.hero_no = entry.number
            if entry.state is not None:
                restore(world, u, entry.state)
            elif entry.spec is not None:
                apply_spec(world, u, entry.spec)
        placed.append(u)
    if roster is not None:
        owner.gold, owner.hero_deaths = roster.gold, roster.hero_deaths
        owner.kills_monsters, owner.kills_players = roster.kills_monsters, roster.kills_players
    return placed
