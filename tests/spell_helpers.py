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
