"""Random item generation: pool builders, modifier roll, loot/shop generator.

Spec: docs/data/items.md section 11.  A pure re-implementation of the exe's item generator
(`FUN_00525f67` and the routines it calls) on top of `itemdefs.ItemTable`; no I/O.  The random
source is an explicit object with one method, `rand15()`, the exe's CRT `rand()` (0..32767);
`MsvcRng` is that generator, a test can pass a scripted one.  Every draw below is made in the
exe's order through `rnd` (`FUN_0051fa25`) and `rnd1` (`FUN_0051fa4e`).

Float math follows the x87 code: `__ftol` truncates and yields 0x80000000 for NaN / out of range.
"""

import math
from dataclasses import dataclass, field, replace
from functools import cmp_to_key

from .itemdefs import (ARMOUR, ELEMENT_DAMAGE, SHIELD, SPECIAL, STAT_CAST, STAT_TEACH, WEAPON, Effect,
                       F_PRICE, ftol)

# --- random source ----------------------------------------------------------------------------


class MsvcRng:
    """The CRT `rand()` the exe uses (`0x583290`): x = x * 214013 + 2531011, result (x >> 16) & 0x7fff."""

    def __init__(self, seed=1):
        self.state = seed & 0xFFFFFFFF

    def rand15(self):
        self.state = (self.state * 214013 + 2531011) & 0xFFFFFFFF
        return (self.state >> 16) & 0x7FFF


def rnd(rng, n):
    """`FUN_0051fa25`: 0..n (inclusive) as `(rand * (n + 1)) >> 15`; 0 without a draw for n == 0."""
    if n == 0:
        return 0
    p = rng.rand15() * (n + 1)
    return (p + (0x7FFF if p < 0 else 0)) >> 15


def rnd1(rng, n):
    """`FUN_0051fa4e`: 1..n, `rnd(n - 1) + 1`."""
    return rnd(rng, n - 1) + 1


def _ftol(x):
    """x87 `fistp` with truncation: NaN, infinity and |x| >= 2^31 give the integer indefinite."""
    if x != x or abs(x) >= 2.0 ** 31:
        return -(2 ** 31)
    return int(x)


def _log(x):
    if x > 0:
        return math.log(x)
    return -math.inf if x == 0 else math.nan


# --- flags (monster `item_flags`, generator +0x54) -------------------------------------------

MATERIAL_BITS = 0x7FFF          # bits 0..14: material list, bit 13 maps to material 14, bit 14 to 15
QUALITY_SHIFT = 15              # bits 15..21: quality 0..6
GEN_WEAPONS = 0x400000          # pool: fighter weapons (suitable_for bit 1)
GEN_SHIELDS = 0x800000          # pool: shields
GEN_ARMOUR = 0x1000000          # pool: armour of every slot
GEN_UNUSED25 = 0x2000000        # kept in the pool mask, never tested
GEN_STOCK = 0x4000000           # books, scrolls, six potions (shop stock)
GEN_STAFFS = 0x8000000          # pool: mage weapons, only together with GEN_ENCHANT
GEN_BYPASS = 0x10000000         # with GEN_ENCHANT: 51 of 101 draws accept the item without modifiers
GEN_ENCHANT = 0x20000000        # the price window applies to the final price, modifiers are rolled

# item type byte (+0x44)
T_QUEST, T_ARMOUR, T_WEAPON, T_POTION, T_SCROLL, T_BOOK = 0, 1, 2, 3, 4, 5
# pool builder kinds (FUN_005247db param 4)
K_ARMOUR, K_WEAPON, K_SHIELD, K_STAFF = 1, 2, 7, 8

FIGHTER_SPELLS = (18, 26)                       # 0x5d07f8, castSpell of a fighter item (Stone Curse, Drain Life)
MAGE_SPELLS = (1, 10, 11, 18, 26, 5, 16)        # 0x5d0800, staves
# armour (kind 1) combinations the pool builder skips: (quality, material, armour record index)
SKIPPED_ARMOUR = ((0, 0, 2), (0, 1, 2), (6, 4, 6))
STOCK_POTIONS = ("Potion Health Regeneration", "Potion Medium Healing", "Potion Big Healing",
                 "Potion Mana Regeneration", "Potion Medium Mana", "Potion Big Mana")
NO_BOOK = (9, 14, 15, 24, 28, 29)               # spell ids without a stock book
CAP_EXPONENT = 0.4                              # restricted pools keep magic_cap >= min ** 0.4


def quality_list(flags):
    return [q for q in range(7) if flags >> (QUALITY_SHIFT + q) & 1]


def material_list(flags):
    """Materials of flag bits 0..14 (FUN_00524bca): bit i is material i, except that 13 is skipped."""
    out, m, f = [], 0, flags & MATERIAL_BITS
    while f:
        if f & 1:
            out.append(m)
        m += 1
        if m == 13:
            m = 14
        f >>= 1
    return out


# --- items ------------------------------------------------------------------------------------


@dataclass
class GenItem:
    """A generated item (the exe's item object): +0x1c price, +0x42 count, +0x44 type, +0x48 magic_cap."""
    defn: object
    type: int
    quality: int = 0
    material: int = 0
    code: int = 0
    base_price: int = 0
    price: int = 0
    magic_cap: int = 0
    effects: list = field(default_factory=list)
    count: int = 1

    @property
    def suitable(self):
        return self.defn.fields.get("suitable_for", 0) if self.type in (T_ARMOUR, T_WEAPON) else 0

    @property
    def stackable(self):
        """vtable +0x50 (0x5234c2): potions and scrolls, or any item without modifiers."""
        return self.type in (T_POTION, T_SCROLL) or not self.effects

    def clone(self, **kw):
        return replace(self, effects=list(self.effects), **kw)


def make_class_item(table, defn, quality, material):
    """The constructors 0x5275d2 (armour), 0x528084 (shield), 0x528a07 (weapon)."""
    st = table.class_stats(defn, quality, material)
    code = material << 12 | defn.cls << 8 | quality << 5 | defn.index
    return GenItem(defn, T_WEAPON if defn.kind == WEAPON else T_ARMOUR, quality, material, code,
                   st.price, st.price, st.magic_cap)


def make_special(table, defn, rng=None):
    """Special item from its record (0x522ee0 / 0x522fab): effects from the record text, price 0x52340f."""
    effects = table.parse_effects(defn.effects_text) if defn.effects_text else []
    sub = defn.subtype
    price = defn.price
    if sub == 5:
        price = 0
    return GenItem(defn, sub, 0, 0, 14 << 8 | defn.index, price, price, 0, effects)


def _special_by_name(table, name):
    for d in table.of_kind(SPECIAL):
        if d.name == name:
            return d
    raise KeyError(name)


# --- pool builders ----------------------------------------------------------------------------


def _pool_class(table, kind, quality, material, lo, hi, restrict, pool):
    """FUN_005247db: append every record of the group allowed for (quality, material)."""
    group = {K_ARMOUR: ARMOUR, K_WEAPON: WEAPON, K_STAFF: WEAPON, K_SHIELD: SHIELD}[kind]
    q, m = table.factors(quality, material)
    for d in table.of_kind(group):
        if not d.allows(quality, material):
            continue
        price = ftol(d.fields["price"] * m[F_PRICE] * q[F_PRICE])      # truncated here, rounded in the item
        if not (lo <= price <= hi) and not restrict:
            continue
        if kind == K_ARMOUR and (quality, material, d.index) in SKIPPED_ARMOUR:
            continue
        item = make_class_item(table, d, quality, material)
        if kind == K_WEAPON and not item.suitable & 1:
            continue
        if kind == K_STAFF and item.suitable & 1:
            continue
        if restrict and kind in (K_ARMOUR, K_STAFF) and item.magic_cap < math.pow(lo, CAP_EXPONENT):
            continue
        pool.append(item)


def build_stock_pool(table, lo, hi, rng):
    """FUN_00524e31: one book per spell (not 9, 14, 15, 24, 28, 29; the school selects the book record),
    then per spell 1..29 a coin flip between its Scroll and SuperScroll record; both need a price in [lo, hi]."""
    pool = []
    schools = ((range(1, 5), "Book Fire"), (range(5, 9), "Book Water"), (range(10, 14), "Book Air"),
               (range(16, 20), "Book Earth"), (range(20, 28), "Book Astral"))
    for sid in range(1, 30):
        if sid in NO_BOOK:
            continue
        name = next(n for r, n in schools if sid in r)
        item = make_special(table, _special_by_name(table, name))
        item.price = table.spells[sid - 1][2]
        item.base_price = item.price
        if lo <= item.price <= hi:
            item.effects = [Effect(STAT_TEACH, sid)]
            pool.append(item)
    for sid in range(1, 30):
        index = sid + 5 if rnd1(rng, 2) == 1 else sid + 0x22
        item = make_special(table, table.get(SPECIAL, index))
        if lo <= item.price <= hi:
            pool.append(item)
    return pool


def build_pool(table, lo, hi, flags, rng):
    """FUN_005254e7: the pool, one pass over (quality, material) per category in the order weapons, staves,
    armour, shields, then the stock."""
    pool = []
    quals, mats = quality_list(flags), material_list(flags)
    restrict = bool(flags & GEN_ENCHANT)
    plan = []
    if flags & GEN_WEAPONS:
        plan.append((K_WEAPON, False))
    if flags & GEN_STAFFS and restrict:
        plan.append((K_STAFF, True))
    if flags & GEN_ARMOUR:
        plan.append((K_ARMOUR, restrict))
    if flags & GEN_SHIELDS:
        plan.append((K_SHIELD, False))
    # 0x8000000 without 0x20000000 builds nothing (FUN_00524bca tests the second flag), 0x2000000 is ignored
    for kind, rest in plan:
        for q in quals:
            for m in mats:
                _pool_class(table, kind, q, m, lo, hi, rest, pool)
    if flags & GEN_STOCK:
        pool += build_stock_pool(table, lo, hi, rng)
    return pool


# --- modifiers --------------------------------------------------------------------------------


def _idiv(a, b):
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def magnitude(table, kind, spell, budget, capacity):
    """FUN_0051f7d3: the largest value a modifier of `kind` may get for a price `budget` and a magic
    capacity, or -1.  castSpell (kind 41) returns the charge count, others the stat points."""
    st = table.stats[kind]
    cap_limit = _idiv(capacity, st.cost)
    if kind == STAT_CAST:
        r = _log(budget / (table.spells[spell - 1][1] * 10.0)) / math.log(2.0)
        n = _ftol((math.pow(1.2, r) - 1.0) * 30.0) if r > 0.0 else -1
        n = min(n, cap_limit)
        n = min(n, 100)
        return -1 if n < 0 else n
    s = _ftol(_log(budget / (capacity * 50.0) - 1.0) / math.log(1.5) * 70.0 / st.cost)
    n = min(s, cap_limit)
    if n < st.affect_min:
        return -1
    return min(n, st.affect_max)


def set_magnitude(table, rng, kind, spell, m):
    """The effect's vtable +0x54 (0x51f6af): draw the real value in 1..m.  castSpell: charges (<= 100);
    damageFire..Astral: min in 1..min(m, 255), spread in 1..m/2; others at least `affectMin`.
    The first draw `rnd1(m)` is made for every kind."""
    r = rnd1(rng, m)
    if kind == STAT_CAST:
        return Effect(kind, spell, 0, min(r, 100))
    if kind in ELEMENT_DAMAGE:
        m = min(m, 255)
        lo = rnd1(rng, m)
        return Effect(kind, lo, rnd1(rng, (m - (m >> 31)) >> 1))
    return Effect(kind, max(r, table.stats[kind].affect_min))


def roll_modifier(table, rng, fighter, item_type, cls, capacity, budget, price, tries=100):
    """FUN_00526ec4: one random modifier or None.  `fighter` is `suitable_for & 1`, `cls` the item code's
    class (weapon 1, shield 2, armour slot), `capacity` the item's magic_cap, `budget` the price room.
    Stat choice: r in 1..total of the `in.<slot>` column, the stat whose cumulative range contains r;
    castSpell always uses `price * 10` (`* 100` for mage items) as budget and a fixed spell list."""
    if budget < 1 or capacity < 1:
        return None
    col = cls - 1 + (0 if fighter else 12)
    stats = table.stats
    last = len(stats) - 1
    total = stats[last].slot_weights[col]
    kind, attempts = -1, 0
    while True:
        if attempts >= tries:
            return None
        kind = -1
        attempts += 1
        r = rnd1(rng, total)
        for i in range(1, last + 1):
            if stats[i].name and stats[i - 1].slot_weights[col] < r <= stats[i].slot_weights[col]:
                kind = i
                break
        if kind != -1:
            break
    if attempts == tries:
        return None                                  # the exe also drops a hit on the last attempt
    if not fighter and item_type == T_WEAPON:
        kind = STAT_CAST
    spell = 0
    if kind == STAT_CAST:
        spell = MAGE_SPELLS[rnd(rng, 6)] if not fighter else FIGHTER_SPELLS[rnd(rng, 1)]
        budget = price * (100 if not fighter else 10)
    m = magnitude(table, kind, spell, budget, capacity)
    if m == -1:
        return None
    return set_magnitude(table, rng, kind, spell, m)


def roll_staff_spell(table, rng, capacity, budget, tries=100):
    """FUN_0052714f: a castSpell modifier of a staff; up to `tries` draws of (spell, magnitude), the first
    non-negative magnitude wins unless it came on the last attempt."""
    n = 0
    while n < tries:
        n += 1
        spell = MAGE_SPELLS[rnd(rng, 6)]
        m = magnitude(table, STAT_CAST, spell, budget, capacity)
        if m >= 0:
            break
    if n >= tries:
        return None
    return set_magnitude(table, rng, STAT_CAST, spell, m)


def add_modifier(table, effects, e):
    """FUN_0052397e: an effect whose `UsableBy` mask (unless 3) misses the mask of any present effect is
    dropped; one of an existing kind overwrites that effect's value; else it is appended."""
    m = table.stats[e.kind].usable_by
    if m != 3:
        for x in effects:
            if m & table.stats[x.kind].usable_by == 0:
                return
    for i, x in enumerate(effects):
        if x.kind == e.kind:
            effects[i] = replace(x, value=e.value, spread=e.spread, count=e.count)
            return
    effects.append(e)


def used_capacity(table, item):
    """FUN_00527273: sum of the effect costs (FUN_0051e318)."""
    return sum(table.effect_cost(e) for e in item.effects)


def _reprice(table, item):
    item.price = table.price_with_effects(item.base_price, item.effects)


def enchant(table, item, max_price, rng):
    """FUN_00526b5d: roll up to three modifiers for a class item so that the price may reach
    `2 * max_price - price`.  Returns False to reject the item.  Specials are always rejected (capacity 0).

    Fighter items and non-weapons: modifier 1 (a failed roll rejects the item; castSpell ends the
    procedure), modifier 2 with `rnd(100) < 50`, modifier 3 with `rnd(100) < 25` (a failed roll or a
    castSpell stops with the item kept), then `magic_cap -= used`.  Staves: one staff spell roll with
    budget `min(2 * max - price, price * 100)`."""
    if item.type not in (T_ARMOUR, T_WEAPON):
        return False
    fighter = bool(item.suitable & 1)
    cls = item.defn.cls
    if not fighter and item.type == T_WEAPON:
        budget = min(2 * max_price - item.price, item.price * 100)
        e = roll_staff_spell(table, rng, item.magic_cap, budget)
        if e is None:
            return False
        add_modifier(table, item.effects, e)
        _reprice(table, item)
        return True
    e = roll_modifier(table, rng, fighter, item.type, cls, item.magic_cap, 2 * max_price - item.price, item.price)
    if e is None:
        return False
    add_modifier(table, item.effects, e)
    _reprice(table, item)
    if e.kind == STAT_CAST:
        return True
    for chance in (0x32, 0x19):
        if rnd(rng, 100) < chance:
            e = roll_modifier(table, rng, fighter, item.type, cls, item.magic_cap - used_capacity(table, item),
                              2 * max_price - item.price, item.price)
            if e is None or e.kind == STAT_CAST:
                return True
            add_modifier(table, item.effects, e)
            _reprice(table, item)
    item.magic_cap -= used_capacity(table, item)
    return True


# --- the generator ----------------------------------------------------------------------------


def _class_key(it):
    return it.suitable & 1 if it.type in (T_ARMOUR, T_WEAPON) else 0


def _compare(a, b):
    """FUN_0052571c.  The exe zeroes the first key when the second item is not armour/weapon/shield and
    leaves the second key uninitialised; here both are 0 then (INFERRED).  Sorting is stable here."""
    ka, kb = _class_key(a), _class_key(b)
    if b.type not in (T_ARMOUR, T_WEAPON):
        ka = 0
    if ka != kb:
        return 1 if ka < kb else -1
    for x, y in ((a.defn.index, b.defn.index), (a.price, b.price)):
        if x != y:
            return 1 if x > y else -1
    return 0


def merge_into(result, item):
    """FUN_005259af: a stackable item of an existing code adds its count to that entry."""
    if item.stackable:
        for e in result:
            if e.code == item.code and e.stackable:
                e.count += item.count
                return
    result.append(item)


def generate(table, lo, hi, flags, count, max_stack, rng, sort=True):
    """FUN_00525f67 on a generator built by FUN_005254e7: up to `count` items with price in [lo, hi].

    1. pool (`build_pool`); empty pool: nothing.
    2. GEN_STOCK: every pool book (count 2), then the six stock potions with a count of 50 + 1..50.
    3. repeat while produced < count and rejected <= count * 10: draw a pool index (`rnd(len - 1)`,
       redrawn while it is a book, at most 1000 draws; the 1000th draw ends the whole run);
       GEN_ENCHANT: GEN_BYPASS accepts without modifiers when `rnd(100) < 51`, else `enchant`; the final
       price must lie in [lo, hi] or the item is rejected; stackable items get `rnd(max_stack) + 1`
       pieces, others 1; equal stackable codes merge.
    4. the list is sorted (`FUN_0052571c`)."""
    pool = build_pool(table, lo, hi, flags, rng)
    if not pool:
        return []
    result = []
    if flags & GEN_STOCK:
        for it in pool:
            if it.type == T_BOOK:
                result.append(it.clone(count=2))
        for name in STOCK_POTIONS:
            it = make_special(table, _special_by_name(table, name))
            it.count = 50 + rnd1(rng, 50)
            result.append(it)
    made = rejected = 0
    while made < count and rejected <= count * 10:
        tries = 0
        while True:
            tries += 1
            pick = rnd(rng, len(pool) - 1)
            if pool[pick].type != T_BOOK or tries >= 1000:
                break
        if tries > 999:
            break
        item = pool[pick].clone()
        if flags & GEN_ENCHANT:
            if flags & GEN_BYPASS and rnd(rng, 100) < 0x33:
                ok = True
            else:
                ok = enchant(table, item, hi, rng)
            if not (ok and lo <= item.price <= hi):
                rejected += 1
                continue
        item.count = rnd(rng, max_stack) + 1 if item.stackable else 1
        merge_into(result, item)
        made += 1
    if sort:
        result.sort(key=cmp_to_key(_compare))
    return result


def loot_item(table, lo, hi, flags, rng):
    """A monster's drop (0x510da2): `generate(100 items, stacks of 1..2)`, one list entry at random
    (`rnd(len - 1)`) with count 1; None when the list is empty."""
    items = generate(table, lo, hi, flags, 100, 1, rng)
    if not items:
        return None
    it = items[rnd(rng, len(items) - 1)]
    it.count = 1
    return it
