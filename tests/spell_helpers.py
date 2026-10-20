"""Synthetic spells for the cast tests: Fire Arrow with the data.bin numbers of docs/data/spells.md section 9 (no install needed)."""

from allods2.formats.spelldefs import FIELDS, SpellDef, SpellTable

FIRE_ARROW = 1


def fire_arrow():
    """Spell 1: complication 3, mana 3, fire, unit target, missile delivery, range 7, speed 200, single target, damage 5..10."""
    f = dict.fromkeys(FIELDS, -1)
    f.update(complication_level=3, mana_cost=3, sphere=1, item=0, target=1, delivery=2, max_range=7, speed=200,
             distribution=1, radius=0, damage_min=5, damage_max=10, defensive=-1)
    return SpellDef(FIRE_ARROW, "Fire Arrow", "Fire Arrow", f)


def spell_table():
    return SpellTable([fire_arrow()])


# The 29 spells with the data.bin numbers the AI casting tests need (mana, defensive, target, delivery, distribution, damage, range; spells.md 2).
_ROWS = {   # n: (name, mana, defensive, target, delivery, distribution, damage_min, damage_max, range)
    1: ("Fire Arrow", 3, -1, 1, 2, 1, 5, 10, 7), 2: ("Fire Ball", 30, -1, 2, 2, 3, 7, 13, 10), 3: ("Wall of Fire", 30, -1, 2, 1, 4, 1, 3, 6),
    4: ("Protection from Fire", 40, 1, 1, 1, 1, -1, -1, 5), 5: ("Ice Missile", 3, -1, 1, 2, 1, 5, 10, 7),
    6: ("Poison Cloud", 30, -1, 2, 1, 3, -1, -1, 6), 7: ("Blizzard", 100, -1, 2, 1, 5, 10, 30, 10),
    8: ("Protection from Water", 40, 1, 1, 1, 1, -1, -1, 5), 9: ("Acid Stream", 100, -1, 2, 1, 5, 10, 14, 3),
    10: ("Lightning", 10, -1, 1, 2, 1, 5, 10, 7), 11: ("Prismatic Spray", 80, -1, 1, 2, 1, 5, 15, 7),
    12: ("Invisibility", 100, 1, 1, 1, 1, -1, -1, 5), 13: ("Protection from Air", 40, 1, 1, 1, 1, -1, -1, 5),
    14: ("Darkness", 5, -1, 2, 1, 3, -1, -1, 6), 15: ("Light", 5, 1, 2, 1, 3, -1, -1, 6), 16: ("Diamond Dust", 3, -1, 1, 2, 1, 5, 10, 7),
    17: ("Wall of Earth", 15, -1, 2, 1, 4, -1, -1, 6), 18: ("Stone Curse", 40, -1, 1, 1, 1, -1, -1, 5),
    19: ("Protection from Earth", 40, 1, 1, 1, 1, -1, -1, 5), 20: ("Bless", 10, 1, 1, 1, 1, -1, -1, 5), 21: ("Haste", 10, 1, 1, 1, 1, -1, -1, 5),
    22: ("Control Spirit", 30, -1, 2, 1, 1, -1, -1, 5), 23: ("Teleport", 60, 1, 2, 1, 1, -1, -1, 1), 24: ("Heal", 5, 1, 1, 1, 1, 8, 16, 6),
    25: ("Summon", 100, -1, 2, 1, 1, -1, -1, 0), 26: ("Drain Life", 20, -1, 1, 1, 1, 4, 6, 7), 27: ("Shield", 10, 1, 2, 1, 1, -1, -1, 0),
    28: ("Curse", 10, -1, 1, 1, 1, -1, -1, 5), 29: ("Slow", 10, -1, 1, 1, 1, -1, -1, 5)}


def sphere_of(n):
    return 1 if n <= 4 else 2 if n <= 9 else 3 if n <= 15 else 4 if n <= 19 else 5


def spell(n):
    name, mana, defensive, target, delivery, dist, lo, hi, rng = _ROWS[n]
    f = dict.fromkeys(FIELDS, -1)
    f.update(complication_level=3 if n == 1 else 0, mana_cost=mana, sphere=sphere_of(n), item=0, target=target, delivery=delivery,
             max_range=rng, speed=200 if delivery == 2 else 0, distribution=dist, radius=0, damage_min=lo, damage_max=hi, defensive=defensive)
    return SpellDef(n, name, name, f)


def full_table():
    """All 29 spells (synthetic copies of the data.bin numbers)."""
    return SpellTable([spell(n) for n in sorted(_ROWS)])


# The effect numbers of data.bin (docs/engine/effects.md 3; spells.md 2): radius (p9), area_duration (p11), duration (p14), modifier terms
# (kind, value, mode, time) of the spells whose release builds an effect object or an area.
_FX = {2: (1, 0, 0, ()), 3: (2, 10, 0, ()), 4: (0, 0, 15, ((21, 30, 1, 30),)), 6: (2, 5, 0, ((6, -2, 2, 8),)), 7: (4, 8, 0, ()),
       8: (0, 0, 15, ((22, 30, 1, 30),)), 9: (3, 0, 0, ()), 12: (0, 0, 10, ()), 13: (0, 0, 15, ((23, 30, 1, 30),)),
       14: (4, 15, 0, ((19, -2, 1, 1),)), 15: (4, 15, 0, ((19, 2, 1, 1),)), 17: (2, 10, 0, ()),
       18: (0, 0, 10, ((16, 5, 1, 8), (15, -20, 1, 8))), 19: (0, 0, 15, ((24, 30, 1, 30),)), 20: (0, 0, 10, ((12, 1, 1, 30),)),
       21: (0, 0, 10, ((17, 2, 1, 30),)), 27: (0, 0, 20, ((16, 5, 1, 30),)), 28: (0, 0, 10, ((12, -1, 1, 30),)),
       29: (0, 0, 10, ((17, -2, 1, 30),))}


def effect_spell(n):
    """`spell(n)` with the radius, the durations and the modifier terms (the speed 200 of the missiles)."""
    from allods2.databin import Modifier
    s = spell(n)
    if n not in _FX:
        return s
    r, area, dur, mods = _FX[n]
    f = dict(s.fields)
    f.update(radius=r, area_duration=area, duration=dur)
    return SpellDef(n, s.name, s.name, f, modifiers=tuple(Modifier(*m) for m in mods))


def effect_table():
    return SpellTable([effect_spell(n) for n in sorted(_ROWS)])
