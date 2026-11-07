"""autocast: part of the monster AI (docs/engine/ai.md); see the package docstring in __init__."""

from ..commands import CastSpell, Stop
from engine.world import DEAD
from ..pathfinding import chebyshev
from .. import movement as mv, spells
from .brain import attack, emit
from .casting import _ratio, cast_at, effect_active, is_mage, ring_cells
from .perception import WANDER_DX, WANDER_DY, _detected, _visible, at_war


# --- the player's own casters (docs/engine/ai.md 12.8) ---------------------------------------------------------------------

AUTO_HEAL, AUTO_BUFF, AUTO_PROT = 0x08, 0x10, 0x20        # party-AI byte (player +0x34 record +0x20): the three auto-cast levels


FRIEND_OWN, FRIEND_ALLY, FRIEND_NEUTRAL = 0x01, 0x02, 0x04   # ... and the kinds of friend `FUN_0056bb53` accepts


SCAN_MANA = (5, 10, 40)                                   # mana the three levels need (`FUN_0056bc7b`)


BLESS, HASTE = 20, 21                                     # spell numbers of the buffs (`fresh` compares the mark with Bless for every spell)


FRESH_TICKS = 20                                          # a unit is not enchanted again within 20 ticks of the last cast aimed at it


BUFF_PROTECTIONS = ((13, 1 << 13), (19, 1 << 19), (4, 1 << 4), (8, 1 << 8))     # the order of `FUN_0056bc7b`: spell, effect bit


def castable(world, u, n):
    """`FUN_0056bb0d(u, n)`: the wrapper of spell n when the book has it and `cost <= mana` (signed words), else None."""
    if world.spell_table is None or spells.wrapper_of(u, n) is None:
        return None
    sp = world.spell_table.get(n)
    return spells.Wrapper(n) if sp is not None and u.mana >= sp.mana_cost else None


def friend_of(world, u, o):
    """`FUN_0056bb53(u, o)`: `o` is a target for the owner's friendly spells: not allied and not at war (relation bits 0, 1 clear) with party-AI
    bit 4; allied (bit 1 set) with bit 2; the same owner with bit 1; or `o` is `u`.  A player's word for itself is `0x12`."""
    pl = world.players.get(u.owner)
    flags = pl.autocast if pl is not None else 0
    rel = 0
    if pl is not None and 0 < o.owner <= len(pl.relations):
        rel = pl.relations[o.owner - 1]
    if not rel & 3 and flags & FRIEND_NEUTRAL:
        return True
    if rel & 2 and flags & FRIEND_ALLY:
        return True
    if u.owner == o.owner and flags & FRIEND_OWN:
        return True
    return u is o


def in_cast_range(world, u, o, w):
    """`FUN_0056bc2e(u, o, wrapper)`: the Chebyshev cell distance is at most the wrapper's range byte."""
    sp = world.spell_table.get(w.number)
    return chebyshev((u.x, u.y), (o.x, o.y)) <= spells.wrapper_range(sp, w, spells.unit_level(u, sp)) & 0xFF


def _members_of(world, u):
    g = world.groups.get(u.order_group) if u.order_group else None
    mem = [world.units[i] for i in g.members if i in world.units] if g is not None else []
    return mem or [u]


def caster_lists(world, u):
    """`FUN_00571e9b(u+0x70)` + `FUN_00567c56` (ai.md 4, caster lists): the pool is every unit on the cells the caster's group sees (no relation
    filter; the dying ones only when no living one is there), minus units in state `0x10` and hidden ones the group does not detect; at war with
    the caster -> `foes` (`server+0xac8`), else `friends` (`server+0xaa8`: allies, neutrals, the caster itself).  Creation order."""
    mem = _members_of(world, u)
    ids = set()
    for c in _visible(world, mem):
        ids |= world.units_at(*c)
    pool = sorted((world.units[i] for i in ids), key=lambda o: o.seq)
    living = [o for o in pool if o.hp > 0]
    foes, friends = [], []
    for o in living or pool:
        if o.state == DEAD or (o.hidden and not _detected(o, mem)):
            continue
        (foes if at_war(world, u.owner, o.owner) else friends).append(o)
    return foes, friends


def fresh(world, o):
    """`B+0xa4 != 20 || |B+0xa8 - tick| > 20` of the target (the test compares with 20 = Bless for every spell)."""
    return o.ai.spell_mark != BLESS or abs(o.ai.spell_tick - world.tick) > FRESH_TICKS


def mode0(world, m):
    """`brain+8 := 0` of a human-owned unit (the exe writes the byte: no order, anchor or group change)."""
    if m.has_mode:
        emit(world, Stop(m.owner, (m.id,), ai=True))


def human_scan(world, m):
    """`FUN_0056bc7b(m)` (ai.md 12.6, 12.8): a player-owned mage looks after its friends by the owner's party-AI byte: mana < 5 or bit 8 clear -> mode 0.
    Wounded: Heal itself; Shield itself; Heal the friend of the caster list in range with the smallest `(int)(hp / hp_max)` when it is below 1
    (needs more than one friend in the list).  Bit 0x10 and mana >= 10: Bless (non-mages, not blessed) then Haste per friend.  Bit 0x20 and
    mana >= 40: per friend the protections 13, 19, 4, 8 and Invisibility (not the caster, relation `& 3`); Invisibility on itself; else mode 0."""
    pl = world.players.get(m.owner)
    flags = pl.autocast if pl is not None else 0
    if world.spell_table is None or m.mana < SCAN_MANA[0] or not flags & AUTO_HEAL:
        mode0(world, m)
        return
    if _heal_self_shield(world, m):
        return
    _, friends = caster_lists(world, m)
    if _heal_friend(world, m, friends):
        return
    if not flags & AUTO_BUFF or m.mana < SCAN_MANA[1]:
        mode0(world, m)
        return
    if _buff_step(world, m, friends):
        return
    if not flags & AUTO_PROT or m.mana < SCAN_MANA[2]:
        mode0(world, m)
        return
    if _protect_step(world, m, friends):
        return
    if not _invisible_self(world, m):
        mode0(world, m)


def _heal_self_shield(world, m):
    """Heal itself when wounded, else Shield itself when not active.  True when a cast was issued."""
    if m.hp != m.hp_max and castable(world, m, spells.HEAL) is not None:
        cast_at(world, m, m, spells.HEAL)
        return True
    if not effect_active(m, spells.SHIELD) and castable(world, m, spells.SHIELD) is not None:
        cast_at(world, m, m, spells.SHIELD)
        return True
    return False


def _heal_friend(world, m, friends):
    """Heal the friend in range with the smallest ratio when below 1 (needs more than one friend in the list).  True when cast."""
    w = castable(world, m, spells.HEAL)
    if w is None or len(friends) <= 1:
        return False
    best, bv = None, 2.0
    for f in friends:
        if friend_of(world, m, f) and in_cast_range(world, m, f, w):
            v = _ratio(f)
            if v < bv:
                best, bv = f, v
    if bv < 1.0:
        cast_at(world, m, best, spells.HEAL)
        return True
    return False


def _buff_step(world, m, friends):
    """Per friend: Bless (non-mages, not blessed) then Haste.  True when cast."""
    for f in friends:
        if not friend_of(world, m, f):
            continue
        w = castable(world, m, BLESS)
        if (w is not None and not is_mage(world, f) and not effect_active(f, BLESS) and fresh(world, f)
                and in_cast_range(world, m, f, w)):
            cast_at(world, m, f, BLESS)
            return True
        w = castable(world, m, HASTE)
        if w is not None and not effect_active(f, HASTE) and fresh(world, f) and in_cast_range(world, m, f, w):
            cast_at(world, m, f, HASTE)
            return True
    return False


def _protect_step(world, m, friends):
    """Per friend: the protections of `BUFF_PROTECTIONS`, then Invisibility (not the caster, relation `& 3`).  True when cast."""
    for f in friends:
        if not friend_of(world, m, f):
            continue
        for n, _ in BUFF_PROTECTIONS:
            w = castable(world, m, n)
            if w is not None and in_cast_range(world, m, f, w) and not effect_active(f, n) and fresh(world, f):
                cast_at(world, m, f, n)
                return True
        w = castable(world, m, spells.INVISIBILITY)
        pl_rel = world.players[m.owner].relations
        rel = pl_rel[f.owner - 1] if 0 < f.owner <= len(pl_rel) else 0
        if (w is not None and in_cast_range(world, m, f, w) and not effect_active(f, spells.INVISIBILITY) and f is not m and rel & 3
                and fresh(world, f)):
            cast_at(world, m, f, spells.INVISIBILITY)
            return True
    return False


def _invisible_self(world, m):
    """Invisibility on itself when known and not active.  True when cast."""
    if castable(world, m, spells.INVISIBILITY) is None or effect_active(m, spells.INVISIBILITY):
        return False
    cast_at(world, m, m, spells.INVISIBILITY)
    return True


def _sel_target(world, m, t, n):
    cast_at(world, m, t, n)
    return 1


def _sel_area(world, m, t, n):
    foes, _ = caster_lists(world, m)
    radius = 1 if n == 2 else 2
    best = -1000
    for f in foes:
        cell = (f.x, f.y)
        if n in (2, 3) and (f.sub_x, f.sub_y) != (mv.CENTRE, mv.CENTRE):     # FUN_00551383 false: the cell ahead of the unit
            o = (f.facing & 0xFF) >> 5
            cell = ((cell[0] + WANDER_DX[o]) & 0xFF, (cell[1] + WANDER_DY[o]) & 0xFF)
        enemies = others = 0
        for o in mv._occupants(world, ring_cells(cell, radius)):
            if at_war(world, m.owner, o.owner):
                enemies += 1
            else:
                others += 100 if o is m else 1
        best = max(best, enemies - others)
    if best < 1:
        return 0
    cast_at(world, m, t, n)
    return 1


def _sel_debuff(world, m, t, n):
    if not effect_active(t, n):
        cast_at(world, m, t, n)
        return 1
    foes, _ = caster_lists(world, m)
    if any(not effect_active(f, n) for f in foes):
        cast_at(world, m, t, n)
        return 1
    return 0


def _sel_heal(world, m, t, n):
    _, friends = caster_lists(world, m)
    best, bv = None, 2.0
    for f in friends:
        if friend_of(world, m, f):
            v = _ratio(f)
            if v < bv:
                best, bv = f, v
    if bv >= 1.0:
        mode0(world, m)
        return 1
    cast_at(world, m, best, n)
    return 1


def _sel_self_cast(world, m, t, n):
    emit(world, CastSpell(m.owner, (m.id,), n, m.id, ai=True))
    m.ai_cast = False                                               # no `brain+0x60 := 1` here: a player's cast (stop after it)
    return 1


def _sel_shield(world, m, t, n):
    if effect_active(m, n):
        return 0
    cast_at(world, m, m, n)
    return 1


SELECTED = {**dict.fromkeys((1, 5, 10, 11, 16, 26), _sel_target), **dict.fromkeys((2, 3, 6, 7), _sel_area),
            **dict.fromkeys((18, 28), _sel_debuff), spells.HEAL: _sel_heal, 25: _sel_self_cast, spells.SHIELD: _sel_shield}


def selected_cast(world, m, t):
    """`FUN_0056b059(m, t)` (ai.md 12.6): the player-owned mage's selected spell `brain+0x78` (Ctrl+A) is cast instead of the melee mode 5 when it is
    in the book and `cost <= mana`.  Returns 1 when it handled the pass.  Attack spells 1 5 10 11 16 26 hit `t`; 2 3 6 7 only when the best
    square round a foe (radius 1 / 2 / 2 / 2; 2 and 3 aim ahead of a unit that is between cells) has more foes than friends; 18 28 when `t` lacks the
    effect, else when some foe lacks it (still aimed at `t`); 24 the friend with the smallest `(int)(hp / hp_max)` (healed below 1, else mode 0);
    25 at itself; 27 Shield at itself unless active; 22 and the rest: 0."""
    n = m.auto_spell
    if not n or world.spell_table is None:
        return 0
    if castable(world, m, n) is None:
        return 0
    handler = SELECTED.get(n)
    return handler(world, m, t, n) if handler is not None else 0


def human_attack(world, m, t):
    """`FUN_0056acc8`'s player-owned branch after the slot roll: a mage tries `selected_cast`; else Brain mode 5 at `t` (range `FUN_0056ac5b`) and a
    mage with that range below 2 runs the scan `human_scan` (which may replace the mode)."""
    mage = is_mage(world, m)
    if mage and selected_cast(world, m, t):
        return
    attack(world, m, t)
    if mage and m.range < 2:
        human_scan(world, m)
