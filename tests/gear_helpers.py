"""A tiny synthetic item table and hero for the gear tests (engine/sim/gear.py): no game files needed."""

from allods2.formats import itemdefs as I
from allods2.formats import saves as S
from allods2.formats.unitstats import HUMAN, UnitType
from engine.world import Player, Unit, UNIT_ID_BASE, World
from engine.sim.combatstats import AttackRecord, ArmourBlock, CombatStats

import numpy as np

COMMON = [1.0] * 7


def _fields(**kw):
    f = dict(shape=0, material=0, price=100, weight=10, slot=0, attack_type=0, damage_min=0, damage_max=0, to_hit=0, defence=0, absorption=0,
             range=-1, windup=-1, recovery=-1, two_handed=0, suitable_for=3, other=0)
    f.update(kw)
    return f


# (kind, class, index, name, fields)
DEFS = [
    (I.WEAPON, 1, 1, "Sword", _fields(attack_type=1, damage_min=5, damage_max=9, to_hit=3, weight=20, suitable_for=1)),
    (I.WEAPON, 1, 2, "Great Sword", _fields(attack_type=1, damage_min=8, damage_max=14, to_hit=2, weight=40, suitable_for=1, two_handed=2)),
    (I.WEAPON, 1, 3, "Staff", _fields(attack_type=3, damage_min=1, damage_max=2, weight=10, suitable_for=2)),
    (I.SHIELD, 2, 1, "Buckler", _fields(defence=4, absorption=1, weight=10, suitable_for=3)),
    (I.ARMOUR, 4, 1, "Helm", _fields(slot=4, defence=3, absorption=1, weight=8, suitable_for=3)),
    (I.ARMOUR, 4, 2, "Hat", _fields(slot=4, defence=1, weight=2, suitable_for=3)),
    (I.ARMOUR, 9, 3, "Boots", _fields(slot=9, defence=2, weight=6, suitable_for=3)),
]
SPECIALS = [("Potion Healing", 30, 1), ("Potion Body", 5, 1), ("Scroll Fire", 20, 1), ("Quest Key", 1, 1)]


def code_of(name):
    for kind, cls, idx, n, _ in DEFS:
        if n == name:
            return cls << 8 | idx
    for i, (n, _, _) in enumerate(SPECIALS, 1):
        if n == name:
            return 14 << 8 | i
    raise KeyError(name)


def table():
    defs = [I.ItemDef(kind, cls, idx, name, f["price"], f["weight"], f) for kind, cls, idx, name, f in DEFS]
    effects = {"Potion Healing": "health=+30", "Potion Body": "body=+1", "Scroll Fire": "castSpell=Fire_Arrow:50", "Quest Key": ""}
    for i, (n, price, weight) in enumerate(SPECIALS, 1):
        defs.append(I.ItemDef(I.SPECIAL, 14, i, n, price, weight, {"price": price, "weight": weight}, flag=1, effects_text=effects[n]))
    names = [""] + ["price", "body", "mind", "reaction", "spirit", "health", "healthMax", "healthRegeneration", "mana", "manaMax", "manaRegeneration",
                    "toHit", "damageMin", "damageMax", "defence", "absorbtion", "speed", "rotationSpeed", "scanRange", "protection0", "protectionFire",
                    "protectionWater", "protectionAir", "protectionEarth", "protectionAstral", "fighterSkill0", "skillBlade", "skillAxe", "skillBludgeon",
                    "skillPike", "skillShooting", "mageSkill0", "skillFire", "skillWater", "skillAir", "skillEarth", "skillAstral", "itemLore",
                    "magicLore", "creatureLore", "castSpell", "teachSpell", "damage", "damageFire", "damageWater", "damageAir", "damageEarth",
                    "damageAstral", "damageBonus"]
    stats = [I.StatDef(i, n, 1, 0, 0, 3, (0,) * 24) for i, n in enumerate(names)]
    return I.ItemTable(defs, [("Common", COMMON)], [("None", COMMON)] * 16, stats, [("Fire Arrow", 10, 10)])


def item(name, **kw):
    t = table()
    return S.Item(code_of(name), kw.pop("count", 1), 0, kw.pop("mods", ()), **kw)


def human_template(mage=False, **kw):
    f = dict(body=40, reaction=30, mind=20, spirit=20, mana_max=70 if mage else -1, gender=0, windup=-1, recovery=-1,
             skill_general=0, skill_blade=25, skill_axe=0, skill_bludgen=0, skill_pike=0, skill_shooting=0)
    f.update(kw)
    return UnitType(HUMAN, 1, "Hero_T", 1, 3, f, ("",) * 10, ())


def world_with_hero(mage=False, **kw):
    w = World(np.zeros((48, 48), np.uint16), np.zeros((48, 48), np.int8), "syn")
    w._cost = np.full((48, 48), 8, np.uint8)
    w.players[1] = Player(1, 0, human=True, relations=(18,) + (1,) * 15)
    w.item_table = table()
    t = human_template(mage, **kw)
    u = Unit(UNIT_ID_BASE + 1, 1, 1, 20, 20, uid=1, hp=100, hp_max=100, human=True, server_id=1, stats=t)
    u.skills = (0, 25, 0, 0, 0, 0)
    u.xp, u.xp_total = (1, 1, 1, 1, 1), 5
    w.add_unit(u)
    from engine.sim import gear
    u.equipment = tuple(gear.EMPTY for _ in range(gear.SLOT_COUNT))
    gear.recompute(w, u)
    u.hp, u.mana = u.hp_max, u.mana_max
    return w, u
