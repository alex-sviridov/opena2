"""Combat stats of a unit: the attack record and the armour block the hit routine reads.

Spec: docs/engine/combat.md section 6 (`FUN_005114f3`, `FUN_00511959`, `FUN_0051366b`, `FUN_005113e7`, `FUN_005290cc`, `FUN_00527a13`,
`FUN_0051d436`).  Pure functions of a data.bin template (`allods2.formats.unitstats.UnitType`), the item table and, for humans, the
skills: no world state.  The exe keeps these as bytes and words of the creature (+0xa6 and +0xbe); here they are plain ints that wrap
the way the exe's fields do (`lo`, `sp` are u8, `skill`, `defence`, `absorb`, `prot` are s16).
"""

from dataclasses import dataclass, field

from allods2.formats import progression as prog
from allods2.formats.itemdefs import ARMOUR, ELEMENT_DAMAGE, SHIELD, STAT_DAMAGE, STAT_DAMAGE_BONUS, WEAPON

HUMAN_WINDUP, HUMAN_RECOVERY = 8, 4         # constructor defaults of a human (`FUN_0050ec60`), kept for a -1 param
SURE_HIT_KIND = 3                           # monster damage kind 3: creature flag +0x4c |= 0x10
STAT_DEFENCE, STAT_ABSORPTION, STAT_TOHIT, STAT_DAMAGE_MAX = 15, 16, 12, 14
STAT_ATTR = {2: "body", 3: "mind", 4: "reaction", 5: "spirit"}      # effect kinds 2-5 (docs/engine/unit-struct.md)
STAT_PROT0 = 20                             # kinds 20..25: protection[phys, fire, water, air, earth, astral]
STAT_ELEM0 = 44                             # kinds 44..48: elemental damage fire..astral


def u8(v):
    return v & 0xFF


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


@dataclass
class AttackRecord:
    """Creature `+0xa6` (the part `FUN_00516f6f` reads): see combat.md 5.2 for the byte offsets."""
    skill: int = 0          # +0xa6 s16, "to-hit"
    lo: int = 0             # +0xb4 u8 physical minimum (bit 7: stored /15)
    sp: int = 0             # +0xb5 u8 physical spread
    kind: int = 0           # +0xb6 attack type 0..5 (the weapon's school)
    lo2: int = 0            # +0xb7 second part minimum (monster damage kind 1)
    sp2: int = 0            # +0xb8
    elo: int = 0            # +0xb9 elemental minimum
    esp: int = 0            # +0xba elemental spread
    elem: int = 0           # +0xbb element 1..5 fire, water, air, earth, astral

    def copy(self):
        return AttackRecord(**self.__dict__)


@dataclass
class ArmourBlock:
    """Creature `+0xbe` (0x16 bytes)."""
    defence: int = 0        # +0xbe s16
    absorb: int = 0         # +0xc0 s16
    prot: list = field(default_factory=lambda: [0] * 6)     # +0xc2.. s16: phys (never read), fire, water, air, earth, astral
    res: list = field(default_factory=lambda: [0] * 6)      # +0xce.. u8: 0, blade, axe, bludgeon, pike, shooting (percent)

    def copy(self):
        return ArmourBlock(self.defence, self.absorb, list(self.prot), list(self.res))

    def add(self, other):
        """`FUN_00515617`: element-wise sum (defence, absorption, 6 protections, 6 resistances)."""
        self.defence = s16(self.defence + other.defence)
        self.absorb = s16(self.absorb + other.absorb)
        self.prot = [s16(a + b) for a, b in zip(self.prot, other.prot)]
        self.res = [u8(a + b) for a, b in zip(self.res, other.res)]


@dataclass
class CombatStats:
    """Everything the fight needs from a unit: the two blocks, flags and the weapon-driven numbers."""
    record: AttackRecord = field(default_factory=AttackRecord)
    block: ArmourBlock = field(default_factory=ArmourBlock)
    sure_hit: bool = False      # +0x4c & 0x10
    human: bool = False         # vtable +0x30
    mage: bool = False          # +0x4c & 4
    range: int = 1              # +0x12c
    windup: int = HUMAN_WINDUP  # +0x134
    recovery: int = HUMAN_RECOVERY      # +0x135
    has_weapon: bool = False    # +0x74 != 0
    weapon_weight: int = 0      # weapon +0x4a, for the hero delay
    reaction: int = 0           # +0x86, humans only (hero delay)


class _Bonus:
    """The equipment / effect accumulators (`+0xd4`..`+0x113`) the combat numbers read."""

    def __init__(self):
        self.tohit = 0          # +0xe6 s16
        self.dmin = 0           # +0xf4 u8
        self.dmax = 0           # +0xf5 u8
        self.elo = self.esp = self.elem = 0         # +0xf9, +0xfa, +0xfb
        self.attr = {"body": 0, "mind": 0, "reaction": 0, "spirit": 0}
        self.block = ArmourBlock()                  # +0xfe
        self.kind = 0           # +0xb6, set by the weapon
        self.range = 0          # added to +0x12c
        self.windup = self.recovery = None
        self.weight = 0
        self.weapon = False


def _apply_effects(bonus, effects):
    """`FUN_0051d436` for the permanent modifiers of an item, kinds that touch the combat numbers only."""
    for e in effects:
        k, v = e.kind, e.value
        if e.mode != 0:                             # duration / charges / single use: not an equipment bonus
            continue
        if k in STAT_ATTR:
            bonus.attr[STAT_ATTR[k]] += v
        elif k == STAT_TOHIT:
            bonus.tohit = s16(bonus.tohit + v)
        elif k in (13, STAT_DAMAGE, STAT_DAMAGE_BONUS):
            bonus.dmin = u8(bonus.dmin + v)
        elif k == STAT_DAMAGE_MAX:
            bonus.dmax = u8(bonus.dmax + v)
        elif k == STAT_DEFENCE:
            bonus.block.defence = s16(bonus.block.defence + v)
        elif k == STAT_ABSORPTION:
            bonus.block.absorb = s16(bonus.block.absorb + v)
        elif STAT_PROT0 <= k < STAT_PROT0 + 6:
            i = k - STAT_PROT0
            bonus.block.prot[i] = max(0, s16(bonus.block.prot[i] + v))
        elif k in ELEMENT_DAMAGE:
            bonus.elem = k - STAT_ELEM0 + 1
            bonus.elo, bonus.esp = u8(v), u8(e.spread)


def _element_of(effects):
    """Weapon bytes +0x69..+0x6b: the elemental damage modifier of the weapon (kinds 44-48), or zeros."""
    for e in effects:
        if e.kind in ELEMENT_DAMAGE:
            return u8(e.value), u8(e.spread), e.kind - STAT_ELEM0 + 1
    return 0, 0, 0


def _equip_weapon(bonus, item, general_skill, human):
    """`FUN_005290cc`: the carrier-side effects of a weapon."""
    d, s = item.defn, item.stats
    t = d.fields.get("attack_type", 0)
    if t >= 10:                                     # flame thrower / elemental beam: elemental damage, own to-hit
        if t in (11, 12):
            bonus.elo = u8(bonus.elo + s.damage_min)
            bonus.esp = u8(bonus.esp + s.damage_spread)
            bonus.elem = 1 if t == 11 else 2
        bonus.tohit = s16(general_skill)
        bonus.kind = 0
    else:
        bonus.dmin = u8(bonus.dmin + s.damage_min)
        bonus.dmax = u8(bonus.dmax + s.damage_spread)
        bonus.block.defence = s16(bonus.block.defence + s.defence)
        bonus.elo, bonus.esp, bonus.elem = _element_of(item.effects)
        bonus.tohit = s16(bonus.tohit + s.to_hit)
        bonus.kind = t
    bonus.range += s.range - 1
    bonus.weight = s.weight
    bonus.weapon = True
    if human:
        w, r = d.fields.get("windup", -1), d.fields.get("recovery", -1)
        if w != -1:
            bonus.windup = w
        if r != -1:
            bonus.recovery = r
    _apply_effects(bonus, item.effects)


def _equip_armour(bonus, item):
    """`FUN_00527a13` / the shield twin: the item's defence and absorption join the carrier's block B."""
    bonus.block.defence = s16(bonus.block.defence + item.stats.defence)
    bonus.block.absorb = s16(bonus.block.absorb + item.stats.absorption)
    _apply_effects(bonus, item.effects)


def _merge(rec, block, bonus):
    """`FUN_005113e7`: `FUN_00515a6c` (attack bonus block into the record) and `FUN_00515617` (armour bonus block)."""
    rec.skill = s16(rec.skill + bonus.tohit)
    rec.lo = u8(rec.lo + bonus.dmin)
    rec.sp = u8(rec.sp + bonus.dmax)
    rec.elo = u8(rec.elo + bonus.elo)
    rec.esp = u8(rec.esp + bonus.esp)
    rec.elem = bonus.elem                           # copied, even when 0
    block.add(bonus.block)


def _param(t, name, default=0):
    v = t.get(name, -1)
    return default if v is None or v < 0 else v


def monster_stats(t, items=None):
    """Monster template -> `CombatStats` (`FUN_005114f3` loader, equipment, merge).  `items`: the item table; without it the weapon
    strings are ignored (template numbers only)."""
    rec = AttackRecord(skill=s16(_param(t, "to_hit")))
    block = ArmourBlock(defence=s16(_param(t, "defence")), absorb=s16(_param(t, "absorption")))
    for i, name in enumerate(("prot_fire", "prot_water", "prot_air", "prot_earth", "prot_astral"), 1):
        block.prot[i] = s16(_param(t, name))
    for i, name in enumerate(("res_blade", "res_axe", "res_bludgeon", "res_pike", "res_shooting"), 1):
        block.res[i] = u8(_param(t, name))
    kind = t.get("damage_kind", -1)
    lo_t = _param(t, "damage_min")
    sp_t = _param(t, "damage_max") - lo_t
    sure = False
    if kind < 1:
        if lo_t < 0x80 and sp_t <= lo_t + 0xFF:
            rec.lo, rec.sp = u8(lo_t), u8(sp_t)
        else:                                       # large natural damage is stored divided by 15, bit 7 = scaled
            rec.lo = min(lo_t // 15, 0x7F) | 0x80
            rec.sp = min(sp_t // 15, 0xFF)
    elif kind == 1:
        rec.lo2, rec.sp2 = u8(lo_t), u8(sp_t)
    elif kind == 2:
        rec.elo, rec.esp = u8(-lo_t), u8(-sp_t)
    elif kind == SURE_HIT_KIND:
        sure = True
        rec.lo, rec.sp = u8(lo_t), u8(sp_t)
    st = CombatStats(rec, block, sure_hit=sure, human=False, windup=_param(t, "windup", HUMAN_WINDUP),
                     recovery=_param(t, "recovery", HUMAN_RECOVERY))
    bonus = _Bonus()
    if items is not None:
        for text in t.equipment:
            if not text.strip():
                continue
            r = items.parse_equipment(text, None)
            item = items.resolve(*r) if r else None
            if item is not None and item.defn.kind == WEAPON:
                _equip_weapon(bonus, item, rec.skill, human=False)      # `+0xe6 := +0xa8` = the template's to-hit
            elif item is not None and item.defn.kind == SHIELD:
                _equip_armour(bonus, item)                              # `FUN_0052846b` has no human gate (no monster has a shield)
            # armour: `FUN_00527a13` returns at once for a non-human carrier
    _merge(rec, block, bonus)
    rec.kind = bonus.kind
    st.range = 1 + bonus.range
    st.weapon_weight, st.has_weapon = bonus.weight, bonus.weapon
    return st


def human_stats(t, items=None, skills=None):
    """Human template -> `CombatStats` (the recompute `FUN_0051366b` after the equipment strings)."""
    mage = t.get("mana_max", -1) > 0
    female = t.get("gender", 0) == 1
    caps = prog.ATTR_CAPS[(mage, female)]
    raw = {n: (prog.ATTR_DEFAULT if t.get(n, -1) < 0 else t.get(n)) for n in ("body", "reaction", "mind", "spirit")}
    sk = list(prog.skills_of(t) if skills is None else skills)
    bonus = _Bonus()
    equipped = {}
    if items is not None:
        for slot, text in enumerate(t.equipment):
            if not text.strip():
                continue
            r = items.parse_equipment(text, slot)
            item = items.resolve(*r) if r else None
            if item is None or not item.defn.can_use(mage):
                continue
            equipped[slot] = item
        w, sh = equipped.get(0), equipped.get(1)
        if w is not None and sh is not None and w.defn.fields.get("two_handed") == 2:
            del equipped[0]                         # equipping the shield moved the two-handed weapon to the pack
        for slot in sorted(equipped):
            item = equipped[slot]
            if item.defn.kind == WEAPON:
                _equip_weapon(bonus, item, sk[0], human=True)
            elif item.defn.kind in (SHIELD, ARMOUR):
                _equip_armour(bonus, item)
    body = min(min(raw["body"], caps[0]) + bonus.attr["body"], 100)
    reaction = min(min(raw["reaction"], caps[1]) + bonus.attr["reaction"], 100)
    spirit = min(min(raw["spirit"], caps[3]) + bonus.attr["spirit"], 100)
    base = int(1.1 ** body / 20.0)
    rec = AttackRecord(skill=s16(int((1.1 ** body + 1.1 ** reaction) / 5.0)), lo=u8(base), sp=u8(base), kind=bonus.kind)
    school = [min(max(s, 0), 100) for s in sk]
    if bonus.kind:
        k = school[bonus.kind]
        rec.skill = s16(rec.skill + 3 * k)
        rec.lo = u8(rec.lo + k // 5)
    block = ArmourBlock(defence=reaction // 3)
    for i in range(1, 6):
        block.prot[i] = spirit // 2
    _merge(rec, block, bonus)
    block.defence = max(block.defence, 0)
    block.absorb = max(block.absorb, 0)
    for i in range(1, 6):
        block.prot[i] = max(0, min(100, min(block.prot[i], spirit // 2 + 70)))
    st = CombatStats(rec, block, human=True, mage=mage, range=1 + bonus.range, reaction=reaction,
                     windup=bonus.windup if bonus.windup is not None else _param(t, "windup", HUMAN_WINDUP),
                     recovery=bonus.recovery if bonus.recovery is not None else _param(t, "recovery", HUMAN_RECOVERY),
                     weapon_weight=bonus.weight, has_weapon=bonus.weapon)
    return st


def unit_combat_stats(t, items=None, skills=None):
    """Dispatch on the template kind (`unitstats.MONSTER` / `HUMAN`); None for an unknown template."""
    if t is None:
        return None
    return human_stats(t, items, skills) if t.kind == prog.unitstats.HUMAN else monster_stats(t, items)


def item_code(item):
    """The 16-bit item code of a resolved item (`material << 12 | class << 8 | quality << 5 | index`, the same as `GenItem.code`)."""
    d = item.defn
    return item.material << 12 | d.cls << 8 | item.quality << 5 | d.index


def equipment_codes(t, items):
    """The item codes the template's equipment strings leave in a unit's loot bag at death (`FUN_00510a70` steps 1-3, C§12.4), in the
    exe's bag order: the second item (`+0x78`, a shield), the weapon (`+0x74`; **only when the weapon class's parameter 15 `suitable_for`
    is non-zero**, natural weapons have 0), then for humans the armour slots 1..12 ascending (`FUN_00512697`).
    Monsters (`FUN_00511959`): 2 strings, a string containing `Shield` is a shield, else a weapon.  Humans (`FUN_005145d1`): 10 strings, 0
    weapon, 1 shield, 2..9 armour (the slot is the class record's `Slot`; a later string for the same slot replaces the earlier one, which
    is lost); items the unit cannot use are not equipped (as in `human_stats`); a two-handed weapon next to a shield is not kept as the weapon."""
    if t is None or items is None:
        return []
    human = t.kind == prog.unitstats.HUMAN
    mage = t.get("mana_max", -1) > 0
    weapon = shield = None
    armour = {}
    for i, text in enumerate(t.equipment):
        if not text.strip():
            continue
        if human:
            r = items.parse_equipment(text, i)
        else:
            r = items.parse_equipment(text, 1 if "Shield" in text else 0)
        item = items.resolve(*r) if r else None
        if item is None or (human and not item.defn.can_use(mage)):
            continue
        if item.defn.kind == WEAPON:
            weapon = item
        elif item.defn.kind == SHIELD:
            shield = item
        else:
            armour[item.defn.cls] = item           # armour class = the record's Slot
    if weapon is not None and shield is not None and weapon.defn.fields.get("two_handed") == 2:
        weapon = None           # equipping the shield moved the weapon to the pack (the pack is dropped too)
    out = []
    if shield is not None:
        out.append(item_code(shield))
    if weapon is not None and weapon.defn.fields.get("suitable_for", 0) != 0:
        out.append(item_code(weapon))
    if human:
        out += [item_code(armour[s]) for s in sorted(armour)]
    return out
