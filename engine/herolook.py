"""Which sprite folder a hero is drawn from (`FUN_0046a215`, docs/formats/animation.md 1.3).

The server builds the party's heroes by name (`FUN_005145d1` with the hero flag, `+0x0e` = `0x21`, or `0x23` for a template with mana, plus the
gender); the client view of such a unit (`obj+0x1b8 & 1`) re-picks its sprite folder from the equipment every tick:

* folder `heroes` for a mage (`& 2`); a fighter's `heroes_l` when the armour slot 8 (`obj+0x1a4`: cuirass, cloak, cape) is empty, else the `Path` of
  `material.reg` `Material<code >> 12>` of that item (`heroes` or `heroes_l`);
* name: `unarmed` while dying (a mage: `mage_st`), else the line `(weapon item index) - 1` of `main/text/heropicture.txt` (0 without a weapon),
  `_` appended with a shield, and a mage's plain `unarmed` becomes `mage`.

The sprite set is then `graphics/units/<folder>/<name>/sprites.256` (`allods2.anim.units.load_unit_set("heroes_l/swordsman")`).  Units that are not heroes
(map humans: the units.reg type of their template) keep their own set.  This module sits next to the view because it reads the simulation's gear."""

from .sim import combatstats as cs
from .sim import gear
from .sim import xp

WEAPON, SHIELD, ARMOUR = 1, 2, 8            # creature slots read by the view (`obj+0x188`, `+0x18c`, `+0x1a4`)
_template_codes = {}


def _codes(world, u, hidden=0):
    """`{slot: item code}` of slots 1, 2, 8: the explicit loadout, else the template's equipment strings as the constructor equips them."""
    if u.equipment:
        return {s: it.code for s, it in gear.slots_of(u).items() if s in (WEAPON, SHIELD, ARMOUR) and s != hidden}
    table = world.item_table
    if table is None or u.stats is None:
        return {}
    key = (u.stats.name, id(table))
    if key not in _template_codes:
        equipped, _ = cs.template_gear(u.stats, table)
        _template_codes[key] = {s: cs.item_code(r) for s, r in equipped.items() if s in (WEAPON, SHIELD, ARMOUR)}
    return {s: c for s, c in _template_codes[key].items() if s != hidden}


def look_key(world, assets, u, hidden=0):
    """The hero sprite set key (`"heroes_l/swordsman"`) of unit `u`, or None for a unit that is not a hero or whose folder does not exist.  `hidden`: the
    creature slot whose item is on the cursor (taken out of the client unit at once, `FUN_004b012f`; `FUN_0046a215` then re-picks the set)."""
    if not xp.is_hero(u):
        return None
    names, materials = assets.hero_look()
    mage = gear.is_mage(u)
    codes = _codes(world, u, hidden)
    if u.hp <= 0:
        name = "mage_st" if mage else "unarmed"
    else:
        w = codes.get(WEAPON)
        i = (w & 0x1F) - 1 if w else 0
        name = names[i] if 0 <= i < len(names) and names[i] else "unarmed"
        if codes.get(SHIELD):
            name += "_"
        if mage and name == "unarmed":
            name = "mage"
    armour = codes.get(ARMOUR)
    folder = "heroes" if mage else ("heroes_l" if not armour else materials.get(armour >> 12, "heroes_l"))
    key = "%s/%s" % (folder, name)
    return key if assets.unit_set(key) is not None else None
