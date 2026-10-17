"""Tests for docs/data/items.md section 11 (allods2.formats.itemgen): one synthetic test per rule."""

import math

import pytest

from allods2.formats import itemdefs as I
from allods2.formats import itemgen as G

from helpers import GFS, needs

needs_databin = needs("world", "data", "data.bin")

# --- scripted random source ---------------------------------------------------------------------


class Script:
    """Returns the given raw rand() values in order."""

    def __init__(self, *values):
        self.values = list(values)

    def rand15(self):
        return self.values.pop(0)


def raw(n, k):
    """A raw rand() value for which rnd(n) == k."""
    r = -(-k * 32768 // (n + 1))
    assert (r * (n + 1)) >> 15 == k and r <= 32767
    return r


def draws(*pairs):
    """Script of rnd(n) == k for each (n, k)."""
    return Script(*[raw(n, k) for n, k in pairs])


# --- synthetic table ------------------------------------------------------------------------------

#         price weight dmg toHit def abs level
COMMON = ("Common", (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0))
RARE = ("Rare", (4.0, 1.0, 1.0, 1.0, 1.0, 1.0, 3.0))
IRON = ("Iron", (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0))
BRONZE = ("Bronze", (0.5, 1.0, 1.0, 1.0, 1.0, 1.0, 40.0))
FILLER = ("None", (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 150.0))


def cls_fields(**kw):
    p = dict(shape=0, material=0, price=0, weight=1, slot=1, attack_type=1, damage_min=1, damage_max=2, to_hit=1,
             defence=0, absorption=0, range=-1, windup=-1, recovery=-1, two_handed=-1, suitable_for=1, other=-1)
    p.update(kw)
    return p


def class_def(kind, cls, index, name, price, masks, **kw):
    f = cls_fields(price=price, **kw)
    return I.ItemDef(kind, cls, index, name, price, 1, f, tuple(masks), 0, "", ())


def special_def(index, name, price, text=""):
    return I.ItemDef(I.SPECIAL, 14, index, name, price, 1, {"price": price, "weight": 1}, (), 1, text, ())


def stat_def(i, name="", cost=10, lo=1, hi=5, usable=3, weights=None):
    return I.StatDef(i, name, cost, lo, hi, usable, tuple(weights or [0] * 24))


def make_stats():
    """Fighter weapon column (class 1): body 10, health 20, castSpell 5 (cumulative 10, 30, 35); shield
    column (class 2): only body 4; mage weapon column: castSpell."""
    stats = [stat_def(0)]
    for i in range(1, 50):
        w = [0] * 24
        w[0] = 0 if i < 2 else 10 if i < 3 else 30 if i < 41 else 35          # fighter weapon (class 1)
        w[1] = 0 if i < 2 else 4                                                # fighter shield (class 2)
        w[12] = 0 if i < 41 else 7                                              # mage weapon: 7 for castSpell
        w[5] = 0 if i < 3 else 6                                                # fighter helm: health only
        name = {2: "body", 3: "health", 41: "castSpell", 42: "teachSpell", 44: "damageFire"}.get(i, "")
        cost = {2: 10, 3: 10, 41: 1, 44: 15}.get(i, 10)
        lo, hi = {2: (1, 5), 3: (3, 50), 41: (-1, 0), 44: (5, 50)}.get(i, (1, 5))
        usable = {3: 1, 44: 1, 41: 3, 2: 3}.get(i, 3)
        stats.append(stat_def(i, name, cost, lo, hi, usable, w))
    return stats


def make_table():
    masks_all = (0xFFFF,) * 7
    defs = [
        class_def(I.WEAPON, 1, 1, "Sword", 1000, masks_all),
        class_def(I.WEAPON, 1, 2, "Staff", 800, masks_all, suitable_for=2),
        class_def(I.SHIELD, 2, 1, "Shield", 500, masks_all, slot=2),
        class_def(I.ARMOUR, 4, 1, "Ring", 100, masks_all, slot=4, suitable_for=3),
        class_def(I.ARMOUR, 5, 2, "Amulet", 100, masks_all, slot=5, suitable_for=3),
        class_def(I.ARMOUR, 6, 3, "Helm", 300, masks_all, slot=6),
    ]
    schools = ["Book Air", "Book Water", "Book Fire", "Book Earth", "Book Astral"]
    for i, n in enumerate(schools, 1):
        defs.append(special_def(i, n, 1))
    for sid in range(1, 30):
        defs.append(special_def(5 + sid, "Scroll S%d" % sid, 100 * sid, "castSpell=S%d:50" % sid))
    for sid in range(1, 30):
        defs.append(special_def(34 + sid, "SuperScroll S%d" % sid, 1000 * sid, "castSpell=S%d:100" % sid))
    for k, (n, price, text) in enumerate((("Potion Antipoison", 7, ""), ("Potion Health Regeneration", 100, "healthRegeneration=100"),
                           ("Potion Medium Healing", 1000, "health=+30"), ("Potion Big Healing", 10000, "health=+100"),
                           ("Potion Mana Regeneration", 100, ""), ("Potion Medium Mana", 1000, ""),
                           ("Potion Big Mana", 10000, ""))):
        defs.append(special_def(64 + k, n, price, text))
    spells = [("S%d" % i, 50, 1000 * i) for i in range(1, 30)]
    names = {}
    return I.ItemTable(defs, [COMMON, RARE], [IRON, BRONZE] + [FILLER] * 14, make_stats(), spells, names)


@pytest.fixture(scope="module")
def table():
    return make_table()


# --- rules ----------------------------------------------------------------------------------------


def test_msvc_rng_is_the_crt_rand():
    r = G.MsvcRng(1)
    assert [r.rand15() for _ in range(3)] == [41, 18467, 6334]


def test_rnd_and_rnd1():
    assert G.rnd(Script(32767), 0) == 0                      # n == 0 makes no draw
    s = Script(32767)
    assert G.rnd(s, 9) == 9 and not s.values                 # (32767 * 10) >> 15
    assert G.rnd(Script(0), 9) == 0
    assert G.rnd1(Script(32767), 10) == 10 and G.rnd1(Script(0), 10) == 1
    s = Script(5)
    assert G.rnd(s, -1) == 0 and not s.values                # n == -1 draws and gives 0


def test_flag_lists():
    assert G.quality_list(0x3F8000) == list(range(7))
    assert G.quality_list(0x8000 | 0x40000) == [0, 3]
    assert G.material_list(0x7FFF) == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15]    # 13 is never rolled
    assert G.material_list(1 << 13 | 1 << 14 | 1) == [0, 14, 15]
    assert G.material_list(0) == []


def test_pool_window_masks_and_category_order(table):
    flags = G.GEN_WEAPONS | G.GEN_SHIELDS | 0x8000 | 1 | 2        # quality 0, materials 0 and 1
    pool = G.build_pool(table, 0, 100000, flags, None)
    # weapons (fighter record only), then shields; per (quality, material)
    assert [(i.defn.name, i.material) for i in pool] == [("Sword", 0), ("Sword", 1), ("Shield", 0), ("Shield", 1)]
    # price window uses ftol(price * material * quality) without +0.5: Sword 1000 * 0.5 = 500 for bronze
    pool = G.build_pool(table, 600, 100000, flags, None)
    assert [(i.defn.name, i.material) for i in pool] == [("Sword", 0)]
    # a mask bit selects the material
    t2 = make_table()
    d = t2.get(I.WEAPON, 1)
    object.__setattr__(d, "masks", (0b01,) * 7)
    assert [i.material for i in G.build_pool(t2, 0, 10 ** 6, G.GEN_WEAPONS | 0x8000 | 3, None)] == [0]


def test_pool_armour_skips_and_staff_rules(table):
    flags = G.GEN_ARMOUR | 0x8000 | 1 | 2
    pool = G.build_pool(table, 0, 10 ** 6, flags, None)
    # armour record 2 (Amulet) is skipped for quality 0 with materials 0 and 1
    assert [(i.defn.name, i.material) for i in pool] == [("Ring", 0), ("Helm", 0), ("Ring", 1), ("Helm", 1)]
    # staves (mage weapons) enter the pool only together with GEN_ENCHANT
    assert G.build_pool(table, 0, 10 ** 6, G.GEN_STAFFS | 0x8000 | 1, None) == []
    pool = G.build_pool(table, 0, 10 ** 6, G.GEN_STAFFS | G.GEN_ENCHANT | 0x8000 | 1, None)
    assert [i.defn.name for i in pool] == ["Staff"]
    # the skipped armour combination (quality 6, bronze-like material 4) is checked on the record index
    assert (6, 4, 6) in G.SKIPPED_ARMOUR


def test_enchant_pool_ignores_window_but_checks_magic_cap(table):
    flags = G.GEN_ARMOUR | G.GEN_ENCHANT | 0x8000 | 1 | 2
    # window [0, 10]: nothing is cheap enough, yet armour enters (restricted pool); magic_cap >= min ** 0.4
    pool = G.build_pool(table, 0, 10, flags, None)
    assert {(i.defn.name, i.material) for i in pool} == {("Ring", 0), ("Ring", 1), ("Helm", 0), ("Helm", 1)}
    # bronze has capacity 40 * 1, iron 0: with min 4 ** (1/0.4) = 32 only bronze keeps its items
    lo = int(32.0)
    pool = G.build_pool(table, lo, 10 ** 6, flags, None)
    assert math.pow(lo, 0.4) > 3 and {i.material for i in pool} == {1}
    assert {i.magic_cap for i in pool} == {40}


def test_magnitude_generic_and_cast(table):
    # body: cost 10, range 1..5.  budget 2000, capacity 10: s = ftol(ln(3) / ln(1.5) * 70 / 10) = 18, cap/cost = 1
    assert G.magnitude(table, 2, 0, 2000, 10) == 1
    assert G.magnitude(table, 2, 0, 20000, 100) == 5                 # t = 3 again: min(18, 10) = 10, clamped to affectMax 5
    assert G.magnitude(table, 2, 0, 1000, 10) == -1                  # ln(1) = 0 -> 0 < affectMin
    assert G.magnitude(table, 2, 0, 100, 10) == -1                   # log of a negative number: indefinite
    # castSpell: scrollCost 50, budget 5000 -> (1.2 ** log2(10) - 1) * 30 = 24.97 -> 24, limited by capacity / cost(1)
    assert G.magnitude(table, 41, 1, 5000, 100) == 24
    assert G.magnitude(table, 41, 1, 5000, 10) == 10
    assert G.magnitude(table, 41, 1, 500, 100) == -1                 # budget <= scrollCost * 10
    assert G.magnitude(table, 41, 1, 10 ** 9, 500) == 100            # at most 100 charges


def test_set_magnitude_draws(table):
    # castSpell: charges = rnd1(m), at most 100
    e = G.set_magnitude(table, draws((9, 3)), 41, 7, 10)
    assert e == I.Effect(41, 7, 0, 4)
    # stat: value rnd1(m), at least affectMin (health 3..50)
    assert G.set_magnitude(table, draws((9, 0)), 3, 0, 10) == I.Effect(3, 3)
    assert G.set_magnitude(table, draws((9, 6)), 3, 0, 10) == I.Effect(3, 7)
    # damageFire: a wasted first draw, then min in 1..min(m, 255) and spread in 1..m/2
    s = draws((9, 9), (9, 2), (4, 3))
    assert G.set_magnitude(table, s, 44, 0, 10) == I.Effect(44, 3, 4) and not s.values
    s = draws((299, 0), (254, 253), (254, 0))
    assert G.set_magnitude(table, s, 44, 0, 300) == I.Effect(44, 254, 1)       # m capped at 255 first


def test_roll_modifier_stat_choice_and_failures(table):
    # fighter weapon column: cumulative body 10, health 30, castSpell 35; r in 1..35 is rnd1(35)
    def roll(k, cap=100, budget=100000, price=100):
        # rnd1(35) == k  <=>  rnd(34) == k - 1; then the magnitude draw rnd1(m) == 1 (rnd(m - 1) == 0)
        return G.roll_modifier(table, Script(raw(34, k - 1), 0, 0, 0), True, G.T_WEAPON, 1, cap, budget, price)
    assert roll(10).kind == 2 and roll(11).kind == 3 and roll(30).kind == 3
    cast = roll(31)
    assert cast.kind == 41 and cast.value in G.FIGHTER_SPELLS
    # no room: capacity or budget below 1
    assert G.roll_modifier(table, Script(), True, G.T_WEAPON, 1, 0, 100, 1) is None
    assert G.roll_modifier(table, Script(), True, G.T_WEAPON, 1, 10, 0, 1) is None
    # magnitude -1 (budget too small for the stat) gives None
    assert G.roll_modifier(table, Script(raw(34, 0), 0), True, G.T_WEAPON, 1, 10, 1, 1) is None
    # shield column (class 2): only body weighs (cumulative 4 from row 2)
    e = G.roll_modifier(table, Script(raw(3, 3), 0), True, G.T_ARMOUR, 2, 100, 100000, 100)
    assert e.kind == 2


def test_roll_modifier_castspell_spell_and_budget(table):
    # fighter: spell from (18, 26) by rnd(1); budget = price * 10 = 5000 -> 24 charges max, then rnd1(24)
    s = draws((34, 30), (1, 1), (23, 5))
    e = G.roll_modifier(table, s, True, G.T_WEAPON, 1, 100, 10, 500)
    assert e == I.Effect(41, 26, 0, 6) and not s.values
    # mage item (fighter False): column 12 + 0, always castSpell for a weapon; spell by rnd(6) from MAGE_SPELLS,
    # budget price * 100
    s = Script(raw(6, 6), raw(6, 3), raw(99, 0))                     # stat draw rnd1(7), spell index 3, magnitude
    e = G.roll_modifier(table, s, False, G.T_WEAPON, 1, 1000, 10 ** 6, 100)
    assert e.kind == 41 and e.value == G.MAGE_SPELLS[3]


def test_roll_modifier_last_attempt_hit_is_dropped(table):
    # a stat with no name never matches; with tries=1 a hit on the only (= last) attempt returns None
    assert G.roll_modifier(table, Script(raw(34, 0)), True, G.T_WEAPON, 1, 100, 100000, 100, tries=1) is None
    assert G.roll_modifier(table, Script(raw(34, 0), 0, 0), True, G.T_WEAPON, 1, 100, 100000, 100, tries=2)


def test_add_modifier_usable_by_and_replace(table):
    fx = [I.Effect(3, 5)]                                    # health: UsableBy 1 (fighters)
    G.add_modifier(table, fx, I.Effect(2, 4))                # body: UsableBy 3 -> always added
    assert [e.kind for e in fx] == [3, 2]
    fx = [I.Effect(3, 5)]
    mage_only = I.StatDef(5, "x", 10, 1, 5, 2, tuple([0] * 24))
    t = I.ItemTable([], [], [], list(table.stats[:5]) + [mage_only] + list(table.stats[6:]), [], {})
    G.add_modifier(t, fx, I.Effect(5, 1))                    # UsableBy 2 does not overlap health's 1: dropped
    assert fx == [I.Effect(3, 5)]
    G.add_modifier(t, fx, I.Effect(3, 9))                    # same kind: value overwritten, no second entry
    assert fx == [I.Effect(3, 9)]
    G.add_modifier(t, fx, I.Effect(44, 5, 2, 0))             # fighter-only damageFire overlaps health
    assert [e.kind for e in fx] == [3, 44]


def test_enchant_fighter_item_up_to_three_modifiers(table):
    def item():
        return G.make_class_item(table, table.get(I.WEAPON, 1), 1, 1)     # Rare Bronze Sword: cap 120, price 2000
    it = item()
    assert (it.price, it.magic_cap) == (2000, 120)
    # budget 2 * 10000 - 2000 = 18000: health (r = 11 of 35) -> ftol(ln(2) / ln(1.5) * 7) = 11 points at most,
    # the magnitude draw 1 is raised to affectMin 3.  No second (rnd(100) = 50 is not < 50), no third (25 is not < 25)
    s = Script(raw(34, 10), 0, raw(100, 50), raw(100, 25))
    assert G.enchant(table, it, 10000, s) and not s.values
    assert it.effects == [I.Effect(3, 3)] and it.magic_cap == 120 - 3 * 10
    assert it.price == table.price_with_effects(2000, it.effects) > 2000
    # second (rnd(100) = 49 < 50) and third (24 < 25) modifier: body, then health again (overwrites the value)
    it = item()
    s = Script(raw(34, 10), 0, raw(100, 49), raw(34, 0), 0, raw(100, 24), raw(34, 10), 0)
    assert G.enchant(table, it, 10000, s)
    assert [e.kind for e in it.effects] == [3, 2]
    # a castSpell first roll keeps the item and ends the procedure without touching magic_cap
    it = item()
    assert G.enchant(table, it, 10000, Script(raw(34, 31), raw(1, 0), 0))
    assert it.effects[0].kind == 41 and it.magic_cap == 120
    # a failed first roll rejects the item
    assert not G.enchant(table, item(), 500, Script())                 # budget 2 * 500 - 2000 < 1: first roll fails
    it = item()
    it.magic_cap = 0
    assert not G.enchant(table, it, 10000, Script())                    # no capacity: no draw at all


def test_enchant_failed_later_roll_keeps_the_item(table):
    it = G.make_class_item(table, table.get(I.WEAPON, 1), 1, 1)
    it.magic_cap = 30                       # health takes all of it: 3 points * cost 10
    s = Script(raw(34, 10), 0, raw(100, 0), raw(100, 0))
    assert G.enchant(table, it, 10000, s)
    # the second roll has capacity 0 and returns None: the item stays with one modifier, magic_cap is not reduced
    assert it.effects == [I.Effect(3, 3)] and it.magic_cap == 30 and s.values == [raw(100, 0)]


def test_enchant_staff_and_specials(table):
    staff = G.make_class_item(table, table.get(I.WEAPON, 2), 1, 1)           # Rare Bronze Staff: price 1600, cap 120
    assert staff.price == 1600
    # one staff spell: budget = min(2 * 5000 - 1600, 1600 * 100) = 8400; spell rnd(6) = 0 -> MAGE_SPELLS[0]; the
    # budget buys ftol((1.2 ** log2(8400 / 500) - 1) * 30) = 33 charges at most, drawn as rnd1(33)
    assert G.magnitude(table, 41, 1, 8400, 120) == 33
    s = Script(raw(6, 0), raw(32, 0))
    assert G.enchant(table, staff, 5000, s) and not s.values
    assert staff.effects == [I.Effect(41, G.MAGE_SPELLS[0], 0, 1)]
    assert staff.price > 1600
    # potions, scrolls and books are always rejected (their magic capacity is 0)
    scroll = G.make_special(table, table.get(I.SPECIAL, 6))
    assert not G.enchant(table, scroll, 10 ** 6, Script())


def test_roll_staff_spell_last_attempt_rule(table):
    # a magnitude below zero on every attempt fails; a success on the last of `tries` attempts fails too
    assert G.roll_staff_spell(table, Script(*[raw(6, 0)] * 5), 100, 1, tries=5) is None
    s = Script(raw(6, 0), raw(6, 0), raw(23, 0))
    assert G.roll_staff_spell(table, s, 100, 1, tries=2) is None


def test_generate_plain_pool_and_stacks(table):
    flags = G.GEN_WEAPONS | 0x8000 | 1                       # quality 0, iron only: one sword
    pool = G.build_pool(table, 0, 10 ** 6, flags, None)
    assert len(pool) == 1
    # rnd(0) draws nothing; each item takes rnd(max_stack) -> 1..max_stack pieces, equal stackable codes merge
    s = Script(raw(1, 1), raw(1, 0), raw(1, 1))
    out = G.generate(table, 0, 10 ** 6, flags, 3, 1, s)
    assert [(i.defn.name, i.count) for i in out] == [("Sword", 2 + 1 + 2)]


def test_generate_enchant_window_bypass_and_rejects(table):
    flags = G.GEN_WEAPONS | G.GEN_ENCHANT | G.GEN_BYPASS | 0x8000 | 1 | 2        # iron and bronze swords
    pool = G.build_pool(table, 400, 3000, flags, None)
    assert len(pool) == 2                                                          # window [400, 3000] holds both
    # pool draw 0, bypass draw 50 (< 51): accepted unchanged and (no effects) stackable: rnd(1) = 0 -> count 1
    s = Script(raw(1, 0), raw(100, 50), raw(1, 0))
    out = G.generate(table, 400, 3000, flags, 1, 1, s)
    assert len(out) == 1 and out[0].effects == [] and out[0].count == 1
    # bypass draw 51 (not < 51): enchant.  Bronze sword (price 500, magic_cap 40): body (r = 1), room for 4 points,
    # draw 1; no second / third modifier (99 is not < 50 / 25); a modified item is not stackable: no count draw
    s = Script(raw(1, 1), raw(100, 51), raw(34, 0), 0, raw(100, 99), raw(100, 99))
    out = G.generate(table, 400, 3000, flags, 1, 1, s)
    assert len(out) == 1 and not s.values and out[0].material == 1 and out[0].count == 1
    assert out[0].effects == [I.Effect(2, 1)] and out[0].magic_cap == 40 - 10
    assert out[0].price == table.price_with_effects(500, out[0].effects) == 1529
    # the same item is rejected when the final price 1529 leaves the window [400, 1000]; the retry takes iron (no
    # capacity, enchant fails without a draw) until count * 10 + 1 rejections have ended the run
    s = Script(raw(1, 1), raw(34, 0), 0, raw(100, 99), raw(100, 99))
    s.values += [0] * 500
    assert G.generate(table, 400, 1000, flags & ~G.GEN_BYPASS, 1, 1, s) == []
    # an item whose final price leaves the window is rejected too: iron sword 1000 > max 900 (endless retries,
    # at most count * 10 + 1 rejections, then the run ends empty)
    class Fixed:
        def rand15(self):
            return 0
    assert G.generate(table, 0, 900, G.GEN_WEAPONS | G.GEN_ENCHANT | G.GEN_BYPASS | 0x8000 | 1, 1, 1, Fixed()) == []


def test_generate_stops_after_count_times_ten_rejections(table):
    flags = G.GEN_WEAPONS | G.GEN_ENCHANT | 0x8000 | 1
    # one pool entry (rnd(0) draws nothing); every enchant fails on its first roll (stat 0 never matches) -> after
    # count * 10 + 1 rejections the loop ends with no item
    class Forever:
        n = 0

        def rand15(self):
            Forever.n += 1
            return 0
    assert G.generate(table, 0, 10 ** 6, flags, 2, 1, Forever()) == []
    assert Forever.n == 0              # an iron sword has no magic capacity: enchant fails before any draw


def test_stock_pool_books_scrolls_and_potions(table):
    lo, hi = 0, 10 ** 7
    rng = Script(*[raw(1, 0)] * 29)                            # rnd1(2) == 1 every time: scrolls, not super scrolls
    pool = G.build_stock_pool(table, lo, hi, rng)
    books = [i for i in pool if i.type == G.T_BOOK]
    scrolls = [i for i in pool if i.type == G.T_SCROLL]
    assert len(books) == 23 and len(scrolls) == 29            # 29 spells minus 6 without a book
    assert [b.effects[0].value for b in books][:5] == [1, 2, 3, 4, 5]
    assert books[0].defn.name == "Book Fire" and books[4].defn.name == "Book Water" and books[-1].defn.name == "Book Astral"
    assert [b.price for b in books][:2] == [1000, 2000]       # the spell's bookCost
    assert all(s.defn.name.startswith("Scroll") for s in scrolls)
    # the window applies to books and scrolls
    pool = G.build_stock_pool(table, 0, 1500, Script(*[raw(1, 1)] * 29))
    assert [i.price for i in pool if i.type == G.T_BOOK] == [1000]
    assert all(i.price <= 1500 for i in pool)


def test_generate_stock_list(table):
    flags = G.GEN_STOCK | 0x8000 | 1
    s = Script(*[raw(1, 1)] * 29, raw(49, 4), *([raw(49, 0)] * 12))
    out = G.generate(table, 0, 10 ** 7, flags, 0, 1, s)
    # books count 2 each, the six potions 50 + 1..50 pieces (first potion: rnd(49) = 4 -> 55)
    assert sum(1 for i in out if i.type == G.T_BOOK) == 23 and all(i.count == 2 for i in out if i.type == G.T_BOOK)
    pots = [i for i in out if i.type == G.T_POTION]
    assert len(pots) == 6 and sorted(p.count for p in pots)[-1] == 55
    assert {p.defn.name for p in pots} == set(G.STOCK_POTIONS)


def test_merge_into_stackable_codes():
    d = special_def(70, "Potion", 1)
    a = G.GenItem(d, G.T_POTION, code=0xE46, count=3)
    b = G.GenItem(d, G.T_POTION, code=0xE46, count=4)
    out = []
    G.merge_into(out, a)
    G.merge_into(out, b)
    assert len(out) == 1 and out[0].count == 7
    c = G.GenItem(d, G.T_ARMOUR, code=0x501, effects=[I.Effect(3, 1)])      # carries a modifier: never stackable
    assert not c.stackable
    G.merge_into(out, c)
    G.merge_into(out, c.clone())
    assert len(out) == 3


def test_loot_item_picks_one_with_count_one(table):
    flags = G.GEN_WEAPONS | 0x8000 | 1
    it = G.loot_item(table, 0, 10 ** 6, flags, G.MsvcRng(3))
    assert it.defn.name == "Sword" and it.count == 1
    assert G.loot_item(table, 5000, 6000, flags, G.MsvcRng(3)) is None


def test_display_name(table):
    names = {0xE06: "Scroll", 0xE01: "Book", 0x0101: "Bronze Dagger"}
    t = I.ItemTable([], [], [], [], [("Fire Arrow", 50, 1000), ("Fireball", 70, 5)], names)
    spells = ["Fire Arrow", "Fire Ball Renamed"]
    assert t.display_name(0xE06, [I.Effect(I.STAT_CAST, 1, 0, 50)], spells) == "Scroll of Fire Arrow"
    assert t.display_name(0xE01, [I.Effect(I.STAT_TEACH, 2)], spells) == "Book of Fire Ball Renamed"
    assert t.display_name(0xE01, [I.Effect(I.STAT_TEACH, 2)]) == "Book of Fireball"       # data.bin names by default
    assert t.display_name(0xE06, [], spells) == "Scroll"
    # castSpell on a class item is a tooltip line ("casts X"), not part of the name
    assert t.display_name(0x0101, [I.Effect(I.STAT_CAST, 1, 0, 5)], spells) == "Bronze Dagger"
    assert t.display_name(0xE06, [I.Effect(I.STAT_CAST, 1)], spells, of="de", tail="!") == "Scroll de Fire Arrow!"
    assert t.display_name(0xFFFF, []) is None


# --- the install ----------------------------------------------------------------------------------


@needs_databin
def test_install_generator_runs_on_loot_flags():
    table = I.load(GFS)
    names = table.names
    for flags, lo, hi in ((0x1147FFFF, 100, 5000), (0x2E7FFFFF, 1000, 50000), (0x31FFFFFF, 1000, 100000),
                          (0x2C0FFFFF, 100, 500000)):
        out = G.generate(table, lo, hi, flags, 100, 1, G.MsvcRng(7))
        assert out
        for it in out:
            assert lo <= it.price <= hi or it.type in (G.T_POTION, G.T_BOOK)
            if it.type != 3:                                     # stock potions bypass the window
                assert it.code in names or it.effects            # modifiers do not change the item code
            assert it.code in names
    # shop-stock flags always add the six potions and every in-window book
    out = G.generate(table, 100, 500000, 0x2C0FFFFF, 10, 1, G.MsvcRng(7))
    assert {i.defn.name for i in out if i.type == G.T_POTION} >= set(G.STOCK_POTIONS)
    assert G.loot_item(table, 100, 5000, 0x1147FFFF, G.MsvcRng(11)) is not None
    # the weapon spell lists name real spells
    for sid in G.FIGHTER_SPELLS + G.MAGE_SPELLS:
        assert 1 <= sid <= 29 and table.spells[sid - 1][1] > 0
