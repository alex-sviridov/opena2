"""Hero gear: item objects, the pack, the equipment slots, the load, and the item messages (docs/data/items.md 6, 12, 15; combat.md 12.11).

An item is a `saves.Item` (code, count, price, modifier records): the exe's item object with its effect list (`FUN_004ed5f5` builds one from the wire
form, `FUN_00528fd8` & co. copy it with its effects).  The pack (`Unit.pack`, the exe's `unit+0x7c`) and a ground pile (`world.Item`: `codes` +
`mods`) hold such objects; nothing is reduced to the 16-bit code.  A human with an explicit loadout has `Unit.equipment`: the 12 slots (index =
creature slot - 1: 1 weapon `+0x74`, 2 second hand `+0x78`, 3..12 the armour table `+0x214..+0x238`, an armour piece goes to the slot of its class
`Slot`).  `combatstats.human_stats(gear=)` turns the loadout into the combat numbers (the recompute `FUN_0051366b`).

Routines (CONFIRMED, docs/data/items.md 15): creature vtable `+0x40` = `FUN_00512573` put (equip a weapon / shield / armour the carrier may use,
use any other item), `+0x44` = `FUN_00512638` put and file the replaced item in the pack, `+0x48` = `FUN_0051266e` take, `+0x4c` = `FUN_00512697`
unequip slots 1..12; item `+0x38` equip (`FUN_005290cc` weapon, `FUN_00527a13` armour, `FUN_0052846b` shield; `FUN_00523613` use), `+0x3c` unequip,
`+0x50` stackable (`FUN_005234c2`); pack insert `FUN_00529ae2`, take `FUN_00529fb6`, load `FUN_0050f065`; messages `0x21` / `0x22` / `0x23` in
`FUN_004f515d`; pickup `FUN_005108fa` / `FUN_00529e5b`.  Layer 4: reads and writes `engine.world` only.
"""

from dataclasses import replace

from allods2.formats import progression as prog
from allods2.formats import saves as S
from allods2.formats.itemdefs import (ARMOUR, SHIELD, SPECIAL, STAT_CAST, STAT_TEACH, WEAPON, effects_from_mods,
                                      mods_from_effects)

from . import combatstats as cs
from . import effects as fx

APPEND = 0x7FFF                 # a fresh pack's insertion index (`FUN_005299b3`: `+0x1c := 0x7fff`)
PACK_LIMIT = 0x400              # `FUN_00529e5b` moves a sack's items only while the pack holds fewer than 0x400 entries
SLOT_WEAPON, SLOT_SHIELD = 1, 2
SLOT_COUNT = 12
EMPTY = S.Item(0, 0)
DROP_REACH = 2                  # a dropped item lands on the target cell when it is within 2 cells of the hero in both axes, else on the hero's cell
POTION, SCROLL, BOOK = 3, 4, 5  # item type bytes `+0x44` of the specials (SUBTYPE of the name prefix)
USE_FLAGS = 8                   # `FUN_00523613`: an effect with flags 0 gets `|= 8` (single use) before it is applied
PICKALL_ORDER = 0x1a          # unit order of the P key (`FUN_0056dafe`), Brain mode 12
PICK_ORDER, PICK_STATE = 2, 2   # unit order `+0x50` and state `+0x54` of the pickup
K_HEAL_HP, K_HEAL_MANA = 6, 9
K_TEACH = STAT_TEACH
CAP_ATTR = 100                  # the stat switch clamps an attribute word to 100


# ---------------------------------------------------------------------------------------------------------------------------------
# item objects
# ---------------------------------------------------------------------------------------------------------------------------------

effects_of = effects_from_mods
mods_of = mods_from_effects


def resolve(table, item):
    """The `itemdefs.Item` (class record, quality / material numbers, effects) of an item object; None for an empty slot or an unknown code."""
    if table is None or item is None or not item.code:
        return None
    effects = effects_of(item.mods)
    r = table.resolve(item.code & 0xFFFF, effects)
    if r is not None and r.defn.kind == SPECIAL and r.defn.effects_text:
        # a special item is built from its data.bin modifier text (`FUN_00522fab`); the wire records come on top
        r = table.resolve(item.code & 0xFFFF, tuple(table.parse_effects(r.defn.effects_text)) + effects)
    return r


def make_item(table, code, effects=(), count=1):
    """An item object from a code and an effect list (the equipment strings, loot, the map's section 9 records)."""
    mods = mods_of(effects)
    r = table.resolve(code & 0xFFFF, effects) if table is not None else None
    return S.Item(code & 0xFFFF, count, r.price if r is not None else 0, mods)


def stackable(table, item):
    """`FUN_005234c2` (item vtable `+0x50`): potions and scrolls (type byte 3 / 4) always, any other item only without modifiers."""
    r = resolve(table, item)
    if r is not None and r.defn.kind == SPECIAL and r.defn.subtype in (POTION, SCROLL):
        return True
    return not item.mods


def weight_of(table, item):
    """`item +0x4a` (short)."""
    r = resolve(table, item)
    return r.stats.weight if r is not None else 0


def pack_weight(table, pack):
    """The pack's total `+0x20`: the sum of `weight * count` (`FUN_00529ae2` adds, `FUN_00529fb6` subtracts)."""
    return sum(weight_of(table, it) * it.count for it in pack)


def pack_insert(table, pack, item, index=APPEND):
    """`FUN_00529ae2(index, item)` on the list `pack`: the item's block tag `+0x4d` is cleared; a stackable item merges into the first pack entry with the
    same code that is stackable too (count added, the new object destroyed); else it is inserted before position `index` (the end when `index` is not
    below the count)."""
    if item is None or not item.code:
        return
    if stackable(table, item):
        for i, e in enumerate(pack):
            if (e.code & 0xFFFF) == (item.code & 0xFFFF) and stackable(table, e):
                pack[i] = replace(e, count=e.count + item.count, new=e.new or item.new)
                return
    if 0 <= index < len(pack):
        pack.insert(index, item)
    else:
        pack.append(item)


def pack_take(pack, index, count):
    """`FUN_00529fb6(index, count)`: the entry at `index` (None past the end); `count` below its stack count splits that many off (the clone gets `count`),
    else the whole entry leaves the pack."""
    if not 0 <= index < len(pack):
        return None
    e = pack[index]
    if count < e.count:
        pack[index] = replace(e, count=e.count - count)
        return replace(e, count=count)
    return pack.pop(index)


# ---------------------------------------------------------------------------------------------------------------------------------
# slots
# ---------------------------------------------------------------------------------------------------------------------------------

def is_mage(u):
    """Creature flag `+0x4c & 4` (`FUN_0053a5a0`): set for a template with mana (a record hero gets it in `FUN_004ea6ab` step 4)."""
    return u.stats is not None and u.stats.get("mana_max", -1) > 0


def slots_of(u):
    """`{creature slot: item}` of the non-empty slots."""
    return {i + 1: it for i, it in enumerate(u.equipment) if it is not None and it.code}


def _store(u, slots):
    u.equipment = tuple(slots.get(i + 1, EMPTY) for i in range(SLOT_COUNT))


def armour_slot(r):
    """The creature slot an armour piece goes to: the class record's `Slot` (`item +0x54`)."""
    return r.defn.cls


def gear_of(world, u):
    """`{slot: resolved item}` of the loadout for `combatstats.human_stats(gear=)`; items with an unknown code are skipped."""
    out = {}
    for slot, it in slots_of(u).items():
        r = resolve(world.item_table, it)
        if r is not None:
            out[slot] = r
    return out


def load_inputs(world, u):
    """(gear, pack half weight) for `human_stats`: `+0x90 = equipped weight + pack total / 2`, the pack total capped at 32000 when 64000 or more."""
    total = pack_weight(world.item_table, u.pack)
    half = 32000 if total >= 64000 else total // 2
    return gear_of(world, u), half


def ensure_loadout(world, u):
    """Give a human that still has the template's equipment strings an explicit loadout (the exe's objects exist from the constructor on): the same
    items `human_stats` equips from the strings, the displaced ones in the pack in front of the carried section 8 items.  False when the unit cannot
    have one (no item table, not a human)."""
    if u.equipment:
        return True
    table = world.item_table
    if not u.human or u.stats is None or table is None:
        return False
    equipped, displaced = cs.template_gear(u.stats, table)
    slots = {slot: make_item(table, cs.item_code(r), r.effects) for slot, r in equipped.items()}
    pack = [make_item(table, cs.item_code(r), r.effects) for r in displaced]
    for k, code in enumerate(u.carried):
        mods = u.carried_mods[k] if k < len(u.carried_mods) else ()
        pack_insert(table, pack, S.Item(code, 1, 0, tuple(mods)))
    _store(u, slots)
    u.pack = tuple(pack)
    sync_carried(u)
    recompute(world, u)
    return True


def sync_carried(u):
    """`Unit.carried` / `carried_mods` mirror the pack (one entry per stack): the triggers' item checks and the pile builder read them."""
    u.carried = tuple(it.code for it in u.pack)
    u.carried_mods = tuple(it.mods for it in u.pack) if any(it.mods for it in u.pack) else ()


# ---------------------------------------------------------------------------------------------------------------------------------
# recompute
# ---------------------------------------------------------------------------------------------------------------------------------

def vitals(world, u, st=None):
    """(max HP, max mana) of a human including the equipment: attribute modifiers feed the formula, `healthMax` / `manaMax` modifiers are added after
    (`FUN_0051366b`, `FUN_005113e7`)."""
    from .combat import combat_stats
    st = st if st is not None else combat_stats(world, u)
    attrs = (st.attrs[0], st.attrs[3]) if st.attrs is not None else None
    return prog.derived_vitals(u.stats, u.skills, bonus_hp=st.hp_bonus, bonus_mana=st.mana_bonus, total=u.xp_total, attrs=attrs)


def recompute(world, u):
    """The recompute (vtable `+0x58`, `FUN_0051366b`) after a change of the loadout, the pack or an attribute: drops the cached combat stats, takes
    the equipment's attribute / skill bonus, the speed stat (load penalty included) and the maximum HP / mana (HP and mana are clamped to them, never
    raised)."""
    from .combat import combat_stats
    if not u.human or u.stats is None:
        return
    u.combat = None
    st = combat_stats(world, u)
    if st.attrs is not None:
        base = prog.attributes(u.stats)
        u.attr_bonus = tuple(a - b for a, b in zip(st.attrs, base))
        if not any(u.attr_bonus):
            u.attr_bonus = ()
    u.skill_bonus = st.skill_bonus if any(st.skill_bonus) else ()
    if u.equipment:
        u.gear_speed = cs.human_speed(st, u.stats, u.type_id)
    if u.skills:
        u.hp_max, u.mana_max = vitals(world, u, st)
    u.hp = min(u.hp, u.hp_max)
    u.mana = max(0, min(u.mana, u.mana_max))
    u.combat = None                                     # rebuilt on next use


# ---------------------------------------------------------------------------------------------------------------------------------
# equip, unequip, use
# ---------------------------------------------------------------------------------------------------------------------------------

def _file(world, u, item, index=None):
    """`FUN_00529ac2` / `FUN_00529ae2`: file an item in the unit's pack at `index` (default `Unit.pack_index`)."""
    pack = list(u.pack)
    pack_insert(world.item_table, pack, item, u.pack_index if index is None else index)
    u.pack = tuple(pack)


def take_slot(world, u, slot):
    """Creature vtable `+0x48` (`FUN_0051266e`): unequip a slot (the item's `+0x3c` removes its effects and weight) and return the object; None when
    the slot is empty."""
    slots = slots_of(u)
    item = slots.pop(slot, None)
    if item is not None:
        _store(u, slots)
    return item


def _two_handed(world, item):
    r = resolve(world.item_table, item)
    return r is not None and r.defn.fields.get("two_handed") == 2


def put(world, u, item):
    """Creature vtable `+0x40` (`FUN_00512573`): a weapon, shield or armour piece is equipped when the carrier may use it (fighters need `suitable_for`
    bit 1, mages bit 2; the equip methods themselves test nothing) and the object it replaced is returned; an item the carrier may not use is returned
    unchanged (the caller files it in the pack); every other item is used (`FUN_00523613`) and consumed (None).  Equipping a weapon moves a second-hand
    shield into the pack when the weapon is two-handed, equipping a shield moves a two-handed weapon (`FUN_005290cc`, `FUN_0052846b`); armour only on
    humans (`FUN_00527a13`)."""
    table = world.item_table
    r = resolve(table, item)
    if r is None:
        return item
    d = r.defn
    if d.kind == SPECIAL:
        use_item(world, u, item, r)
        return None
    if not d.can_use(is_mage(u)):
        return item
    slots = slots_of(u)
    if d.kind == WEAPON:
        old = slots.get(SLOT_WEAPON)
        if _two_handed(world, item) and SLOT_SHIELD in slots:
            shield = slots.pop(SLOT_SHIELD)
            u.equipment = tuple(slots.get(i + 1, EMPTY) for i in range(SLOT_COUNT))
            _file(world, u, shield)
        slots[SLOT_WEAPON] = item
    elif d.kind == SHIELD:
        old = slots.get(SLOT_SHIELD)
        w = slots.get(SLOT_WEAPON)
        if w is not None and _two_handed(world, w):
            slots.pop(SLOT_WEAPON)
            u.equipment = tuple(slots.get(i + 1, EMPTY) for i in range(SLOT_COUNT))
            _file(world, u, w)
        slots[SLOT_SHIELD] = item
    else:
        if not u.human:
            return item
        slot = armour_slot(r)
        if not 3 <= slot <= SLOT_COUNT:
            return item                                 # "Illegal armor" (slot 0); the other classes have no slot in the table
        old = slots.get(slot)
        slots[slot] = item
    _store(u, slots)
    return old


def put_and_file(world, u, item):
    """Creature vtable `+0x44` (`FUN_00512638`): `put`, the returned object goes to the pack."""
    back = put(world, u, item)
    if back is not None:
        _file(world, u, back)


def unequip_all(world, u):
    """Creature vtable `+0x4c` (`FUN_00512697`): slots 1..12 into the pack, in slot order.  (The death drop collects them: `bag`.)"""
    for slot in range(1, SLOT_COUNT + 1):
        it = take_slot(world, u, slot)
        if it is not None:
            _file(world, u, it)


def use_item(world, u, item, r):
    """`FUN_00523613` for the item object `item` (resolved `r`): every effect of a living carrier gets flags `|= 8` when it had none and is applied
    (its `+0x3c`); the object is then destroyed.  Permanent kinds: attributes 2..5 add to the base word (clamped to 100; the cap of the recompute
    still applies), health / mana 6 / 9 heal up to the maximum; timed modes 1 / 2 (potions with `duration N`) become spell-style effects with id 0
    (merged by id like every effect: effects.md 4); the other kinds go through the effect system's stat switch.  A book's `teachSpell` (42) adds the
    spell to the book of a mage (`FUN_0051c391` / `FUN_0051c29e`); `castSpell` (41) does nothing here (the scroll is cast by message 0x25)."""
    if u.hp <= 0:
        return
    from engine.world import Effect as FxEffect
    for e in r.effects:
        flags = e.mode or USE_FLAGS
        k, v = e.kind, e.value
        if k in (2, 3, 4, 5):
            name = cs.STAT_ATTR[k]
            raw = prog.attributes(u.stats)[("body", "reaction", "mind", "spirit").index(name)]
            fields = dict(u.stats.fields)
            fields[name] = min(raw + v, CAP_ATTR)
            u.stats = replace(u.stats, fields=fields)
        elif k == K_HEAL_HP:
            u.hp = min(u.hp + v, u.hp_max)
        elif k == K_HEAL_MANA:
            u.mana = min(u.mana + v, u.mana_max)
        elif k == K_TEACH:
            if u.spellbook is not None or is_mage(u):
                u.spellbook = (u.spellbook or 0) | (1 << v)
        elif k == STAT_CAST:
            pass
        else:
            fx.apply(world, u, FxEffect(0, k, flags, v, e.time))
    recompute(world, u)


# ---------------------------------------------------------------------------------------------------------------------------------
# the item messages
# ---------------------------------------------------------------------------------------------------------------------------------

KIND_SLOT, KIND_PACK, KIND_GROUND = 1, 2, 3


def move_item(world, u, src_kind, dst_kind, src_index, dst_index, count=1):
    """Message `0x22` (`FUN_004f515d` case 0x22) for the hero `u`; kinds 4..8 (the shop) are not modelled.  Returns False when nothing happened.

    Source: kind 1 the equipment slot `src_index + 1` (slots above 2 only on humans) taken with `+0x48`; kind 2 the pack entry `src_index` split by
    `count` (`FUN_00529fb6`); kind 3 a sack on the hero's own cell: the pack index becomes `dst_index` and the hero gets the pickup order.
    Destination: kind 1 sets the pack index to `src_index` and `put`s the item (a replaced or refused item goes back to the pack at that index);
    kind 2 files it at `dst_index`; kind 3 drops it: a pile on the cell `(dst_index & 255, dst_index >> 8)` when it is within 2 cells of the hero in
    both axes, else on the hero's cell (a cell that cannot hold a pile loses the items).  The load is recomputed afterwards (`FUN_0050f065`)."""
    if not u.human or u.hp <= 0 or world.item_table is None:
        return False
    ensure_loadout(world, u)
    if src_kind == KIND_GROUND:
        if not world.items_at(u.x, u.y):
            return False
        u.pack_index = dst_index
        set_pickup(world, u, (u.x, u.y))
        return True
    if src_kind == KIND_PACK:
        pack = list(u.pack)
        item = pack_take(pack, src_index, count)
        u.pack = tuple(pack)
    elif src_kind == KIND_SLOT:
        slot = src_index + 1
        if slot > 2 and not u.human:
            return False
        item = take_slot(world, u, slot) if 1 <= slot <= SLOT_COUNT else None
    else:
        return False
    if item is None:
        return False
    if dst_kind == KIND_SLOT:
        u.pack_index = src_index
        back = put(world, u, item)
        if back is not None:
            _file(world, u, back)
    elif dst_kind == KIND_PACK:
        _file(world, u, item, dst_index)
    elif dst_kind == KIND_GROUND:
        x, y = dst_index & 0xFF, (dst_index >> 8) & 0xFF
        if abs(u.x - x) > DROP_REACH or abs(u.y - y) > DROP_REACH:
            x, y = u.x, u.y
        drop_items(world, x, y, [item])
    else:
        _file(world, u, item, src_index)                # not a destination of the game: keep the item
    sync_carried(u)
    recompute(world, u)
    return True


def drop_items(world, x, y, items, gold=0):
    """`FUN_0052acf6(cell, bag, gold)`: a stack becomes `count` pile entries (the pile holds single objects)."""
    codes, mods = [], []
    for it in items:
        for _ in range(max(1, it.count)):
            codes.append(it.code & 0xFFFF)
            mods.append(tuple(it.mods))
    return world.place_pile(x, y, gold, codes, mods=tuple(mods) if any(mods) else ())


def drop_gold(world, player, u, amount, cell):
    """Message `0x23`: 1 <= amount <= the player's gold (`player +0x3c`, found by id `FUN_005167c6`), subtracted, then a gold-only pile like a dropped
    item (target cell within 2 cells of the first unit, else its cell).  A cell that cannot hold a pile loses the gold."""
    if amount < 1 or amount > player.gold:
        return False
    player.gold -= amount
    x, y = cell
    if abs(u.x - x) > DROP_REACH or abs(u.y - y) > DROP_REACH:
        x, y = u.x, u.y
    world.place_pile(x, y, amount, [])
    return True


def pile_items(world, pile):
    """The pile's objects as items (`codes` / `mods` are parallel)."""
    out = []
    for i, code in enumerate(pile.codes):
        mods = pile.mods[i] if i < len(pile.mods) else ()
        out.append(make_item(world.item_table, code, effects_of(mods)) if mods else S.Item(code & 0xFFFF, 1, 0, ()))
    return out


def pick_up(world, u, pile):
    """`FUN_005108fa`: the pile's gold goes to the player (`FUN_00516238`), its items are filed in the pack one by one at the pack index
    (`FUN_00529e5b`, only while the pack holds fewer than 0x400 entries), the pile is deleted (the items are lost when the pack is full)."""
    pl = world.players.get(u.owner)
    if pile.gold > 0 and pl is not None:
        pl.gold += pile.gold
    if len(u.pack) < PACK_LIMIT:
        for it in pile_items(world, pile):
            _file(world, u, replace(it, new=True))
    world.remove_item(pile.id)
    sync_carried(u)
    recompute(world, u)


# --- script items (instants 11, 12, 13, 20, 28, 38): the same pack as the pickup ---------------------------------------------------

def give_item(world, u, code, mods=()):
    """`FUN_004fbf01` + `FUN_00529ac2` (instant 12, the second half of 11): a new item filed at the end of the unit's pack.  A unit without an explicit
    loadout (monsters) keeps the section 8 list `Unit.carried`, which the death drop reads."""
    code &= 0xFFFF
    if not u.equipment:
        u.carried = tuple(u.carried) + (code,)
        if u.carried_mods or mods:
            u.carried_mods = tuple(u.carried_mods) + ((),) * (len(u.carried) - 1 - len(u.carried_mods)) + (tuple(mods),)
        return
    _file(world, u, S.Item(code, 1, 0, tuple(mods)), APPEND)
    sync_carried(u)
    recompute(world, u)


def remove_item(world, u, code):
    """`FUN_00529f3f` (instants 11, 13, 38): the first pack entry whose code word matches gives one piece (a stack is split, a single entry leaves the
    list).  Returns the item taken, or None."""
    code &= 0xFFFF
    if not u.equipment:
        for i, c in enumerate(u.carried):
            if (c & 0xFFFF) == code:
                mods = u.carried_mods[i] if i < len(u.carried_mods) else ()
                u.carried = tuple(u.carried[:i]) + tuple(u.carried[i + 1:])
                if u.carried_mods:
                    u.carried_mods = tuple(u.carried_mods[:i]) + tuple(u.carried_mods[i + 1:])
                return S.Item(code, 1, 0, tuple(mods))
        return None
    pack = list(u.pack)
    for i, it in enumerate(pack):
        if (it.code & 0xFFFF) == code:
            taken = pack_take(pack, i, 1)
            u.pack = tuple(pack)
            sync_carried(u)
            recompute(world, u)
            return taken
    return None


def take_all(world, u):
    """The whole pack leaves the unit (instants 20 and 28: `FUN_005109f5` / `FUN_00529e5b` swap in an empty one); returns the items."""
    if not u.equipment:
        items = [S.Item(c, 1, 0, tuple(u.carried_mods[i]) if i < len(u.carried_mods) else ()) for i, c in enumerate(u.carried)]
        u.carried, u.carried_mods = (), ()
        return items
    items = list(u.pack)
    u.pack = ()
    sync_carried(u)
    recompute(world, u)
    return items


# --- the pickup order (message 0x21; order 2, Brain mode 7, state 2) ----------------------------------------------------------

def set_pickup(world, u, cell):
    """`FUN_0056da98`: cancel, order 2, destination `cell`, Brain mode 0 (the group pass starts it)."""
    from . import movement as mv
    mv.cancel(u, world)
    u.order = PICK_ORDER
    u.pick_cell = tuple(cell)
    u.mode_go = u.mode_attack = u.mode_cast = u.mode_cell = u.mode_follow = u.mode_look = u.mode_pick = False
    u.anchor = None
    u.mover.waiting = u.mover.parked = False
    u.mover.arrived = False


def refresh_pickup(world, u):
    """`FUN_0056c8da` (order 2 in the group-pass executor): on the sack's cell Brain mode 7, else Brain mode 1 towards it."""
    if u.pick_cell is None:
        return
    m = u.mover
    if (u.x, u.y) == u.pick_cell:
        u.mode_pick = True
        u.mode_go = False
    else:
        u.mode_pick = False
        u.mode_go = True
        m.goal = u.pick_cell
        m.arrived = m.failed = False
        m.waiting = m.parked = False


def pick_mode(world, u):
    """Brain mode 7 (`FUN_0056ea24`): state 2 when it is not yet, else stop (`FUN_0056dbc6`)."""
    from . import movement as mv
    if u.state == PICK_STATE:
        u.mode_pick = False
        mv.stop_unit(world, u)
    else:
        u.state = PICK_STATE


def pickup_tick(world, u):
    """The state switch case 2 (`FUN_0050f12c`): the sack on the unit's own cell, if any, is picked up."""
    for i in sorted(world.items_at(u.x, u.y)):
        pick_up(world, u, world.items[i])
        break


# --- pick up all sacks in sight (message 0x13, key P; order 0x1a, Brain mode 12) -----------------------------------------------

def set_pickall(world, u):
    """`FUN_0056dafe`: cancel, order 0x1a, `mover+0x90 := 0`, Brain mode 0 (the group pass chooses the sack)."""
    from . import movement as mv
    mv.cancel(u, world)
    u.order = PICKALL_ORDER
    u.mode_go = u.mode_attack = u.mode_cast = u.mode_cell = u.mode_follow = u.mode_look = u.mode_pick = u.mode_loot = False
    u.anchor = None
    u.mover.waiting = u.mover.parked = False
    u.mover.arrived = False


def nearest_sack(world, u):
    """`FUN_00559eed(unit, 1)`: the unit's own cell when a sack lies there (no reachability test); else the square rings `r = 1 .. sight` round it
    (`sight` = the scan byte `+0xa5`), per ring `d = -r .. r` the cells `(x+d, y+r)`, `(x+d, y-r)` and, for `|d| != r`, `(x+r, y+d)`, `(x-r, y+d)`; a
    cell counts when a sack lies on it and the unit's footprint there is free in the live layer (`FUN_00555cd50`, `FUN_0055a10b`).  The scan stops after the
    first `d` that found a cell, and the list is pushed at its front (`FUN_0055f170`): **the last cell found is the target**.  None when nothing is in sight."""
    from . import orders
    from .ai.perception import _scan_range
    here = (u.x, u.y)
    if world.items_at(*here):
        return here
    sight = _scan_range(u, world)
    for r in range(1, sight + 1):
        found = None
        for d in range(-r, r + 1):
            cells = [(u.x + d, u.y + r), (u.x + d, u.y - r)]
            if abs(d) != r:
                cells += [(u.x + r, u.y + d), (u.x - r, u.y + d)]
            for c in cells:
                if 0 <= c[0] < world.width and 0 <= c[1] < world.height and world.items_at(*c) and orders._target_free(world, u, c):
                    found = c
            if found is not None:
                return found
    return None


def refresh_pickall(world, u):
    """`FUN_0056a909` (order 0x1a in the group-pass executor, every pass): Brain mode 12 towards the nearest sack with `brain+0xa` = its cell, else the
    unit stands (`FUN_0056d52b`: order 0xc)."""
    from . import movement as mv
    cell = nearest_sack(world, u)
    if cell is None:
        mv.set_stand(world, u)
        return
    m = u.mover
    u.mode_go = u.mode_attack = u.mode_cast = u.mode_cell = u.mode_follow = u.mode_look = u.mode_pick = False
    u.mode_loot = True
    if m.goal != cell:
        m.goal = cell
        m.arrived = m.failed = False
        m.waiting = m.parked = False


def loot_mode(world, u):
    """Brain mode 12 (`FUN_0056eb2d`): on the cell `brain+0xa` and at its centre (`FUN_00551383`) state 2 (the tick files the sack), the next time state 0
    and mode 0; elsewhere the move driver towards the cell (`FUN_0056e4ac`, as Brain mode 1) and state 1."""
    from . import movement as mv
    m = u.mover
    if (u.x, u.y) == m.goal and (u.sub_x, u.sub_y) == (mv.CENTRE, mv.CENTRE):
        if u.state != PICK_STATE:
            u.state = PICK_STATE
        else:
            u.state = 0
            u.mode_loot = False
    else:
        mv.go_tick(world, u)
        u.state = mv.MOVE_STATE


def command_pickup(world, u, cell, index):
    """Message `0x21` after the intake: the sack must exist at `cell` ("Sack not found" otherwise); the pack index becomes `index`, the unit gets
    order 2.  Returns False when there is no sack."""
    if not world.items_at(*cell):
        return False
    ensure_loadout(world, u)
    u.pack_index = index
    set_pickup(world, u, cell)
    return True


# --- the death drop ----------------------------------------------------------------------------------------------------------

def bag(world, u):
    """What a dying human with an explicit loadout drops (`FUN_00510a70` steps 1-3): the pack as it is, then the second hand, the weapon (only when its
    class `suitable_for` is non-zero) and the armour slots 3..12.  Returns (codes, mods) with stacks expanded."""
    table = world.item_table
    items = list(u.pack)
    slots = slots_of(u)
    if SLOT_SHIELD in slots:
        items.append(slots[SLOT_SHIELD])
    w = slots.get(SLOT_WEAPON)
    if w is not None:
        r = resolve(table, w)
        if r is not None and r.defn.fields.get("suitable_for", 0) != 0:
            items.append(w)
    for slot in range(3, SLOT_COUNT + 1):
        if slot in slots:
            items.append(slots[slot])
    codes, mods = [], []
    for it in items:
        for _ in range(max(1, it.count)):
            codes.append(it.code & 0xFFFF)
            mods.append(tuple(it.mods))
    return codes, (tuple(mods) if any(mods) else ())


def template_speeds(world):
    """The speed stat of every human that has no explicit loadout: the recompute of its template equipment (load penalty `load // capacity` once the
    equipped weight reaches Body * 10 + 1, and the speed modifiers of the strings, e.g. `Chain Boots{speed=2}`), which `FUN_0051366b` applies to
    every human.  Called once by `Simulation`; the hero units get theirs from `recompute`."""
    table = world.item_table
    if table is None:
        return
    cache = {}
    for u in world.units.values():
        if not u.human or u.stats is None or u.gear_speed is not None or u.equipment:
            continue
        key = (id(u.stats), u.type_id)
        if key not in cache:
            equipped, _ = cs.template_gear(u.stats, table)
            st = cs.human_stats(u.stats, table, gear=equipped)
            cache[key] = cs.human_speed(st, u.stats, u.type_id)
        u.gear_speed = cache[key]
