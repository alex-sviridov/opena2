"""casting: part of the monster AI (docs/engine/ai.md); see the package docstring in __init__."""

from allods2.formats import passability as pas
from engine.cellslots import pack
from ..commands import CastSpell
from .. import combat as cb, effects, movement as mv, spells
from ..pathfinding import chebyshev, foot, unit_size
from .brain import emit
from .perception import WANDER_DX, WANDER_DY, _detected, unword, word


# --- casters (docs/engine/ai.md 12) ----------------------------------------------------------------------------------------

ENEMY, CELL, SELF = "enemy", "cell", "self"                         # where `FUN_0056a981` aims a spell


SPECIAL_TARGET = {                                                   # FUN_0056a981 jump table 0x56abe7: spell -> aim
    **dict.fromkeys((1, 5, 10, 11, 16, 18, 26, 28, 29), ENEMY),      # cast at the enemy
    **dict.fromkeys((2, 3, 6, 7, 14, 15, 17), CELL),                 # at the enemy's cell
    **dict.fromkeys((4, 8, 12, 13, 19, 20, 21, 24, 25, 27), SELF),   # at itself
}


SPECIAL_ENEMY, SPECIAL_CELL, SPECIAL_SELF = (frozenset(n for n, k in SPECIAL_TARGET.items() if k == kind) for kind in (ENEMY, CELL, SELF))


SPECIAL_AHEAD = 9                                                    # the cell next to the caster towards the enemy


CLEVER_MIND, CLEVER_MELEE = 60, 29      # FUN_0057a769: mind >= 60 and rand(100) <= 29 -> the decision again, then mode 5


IDLE_MANA = 10                          # FUN_0056c592: an idle mage needs mana > 10


OWN_SPELLS = 0x1D                       # the cast lists loop n = 1..28 (`< 0x1d`): spell 29 is never in them


def is_mage(world, u):
    """`FUN_0053a5a0` = creature flag `+0x4c & 4` (ai.md 12.1)."""
    return cb.combat_stats(world, u).mage


def _divide(rng, n):
    """`FUN_0057afd0(n)` = `rand15 * n / 0x8000` (the order manager's helper; one draw, also for n == 0)."""
    return rng.rand15() * n // 0x8000


def _wrapper_ok(world, u, n, defensive):
    """The cast-list filter of `FUN_0057a769` / `FUN_0057a999`: spell n in the book, `cost <= mana` (signed words), `wrapper+0xa == defensive`."""
    if not (spells.known_mask(u) >> n) & 1:
        return False
    sp = world.spell_table.get(n) if world.spell_table is not None else None
    return sp is not None and sp.mana_cost <= u.mana and (sp.defensive == 1) == defensive


def cast_at(world, m, t, n):
    """`brain+0x60 := 1` + `FUN_0056c72b(m, t, wrapper n)`: Brain mode 8 at unit `t` (an `ai=True` `CastSpell`)."""
    emit(world, CastSpell(m.owner, (m.id,), n, t.id, ai=True))


def cast_cell(world, m, cell, n):
    """`brain+0x60 := 1` + `FUN_0056969c(m, cell, wrapper n)`: Brain mode 9 at the cell (an `ai=True` `CastSpell` with `cell`)."""
    emit(world, CastSpell(m.owner, (m.id,), n, None, ai=True, cell=(cell[0] & 0xFF, cell[1] & 0xFF)))


def can_stand(world, u, cell):
    """`FUN_0055cd50(u, cell)`: every cell of u's `size x size` footprint from `cell` is clear in the live layer (`pf+0x20000`: the static block
    layer and the unit stamps, u's own included) under u's mover mask (`mover+5`)."""
    mt = u.move_type if u.move_type in pas.MOVE_MASK else 1
    mask = pas.MOVE_MASK[mt]
    n = unit_size(u)
    for dy in range(n):
        for dx in range(n):
            x, y = (cell[0] + dx) & 0xFF, (cell[1] + dy) & 0xFF
            if world.blocked(x, y, mt):
                return False
            for air, bit in ((0, mv.UNIT_STAMP_GROUND), (1, mv.UNIT_STAMP_AIR)):
                if bit & mask and pack(x, y) in world.slots.stamp[air]:
                    return False
    return True


def special_attack(world, m, t, n):
    """`FUN_0056a981(m, t, n)` (ai.md 12.3): the target by spell number, then `brain+0x60 := 1`; nothing when n is not in the book."""
    if spells.wrapper_of(m, n) is None:
        return
    kind = SPECIAL_TARGET.get(n)
    if kind == ENEMY:
        cast_at(world, m, t, n)
    elif kind == CELL:
        cast_cell(world, m, (t.x, t.y), n)
    elif kind == SELF:
        cast_at(world, m, m, n)
    elif n == SPECIAL_AHEAD:
        o = (cb.octant(foot(m), foot(t)) & 0xFF) >> 5                   # FUN_005568e4 >> 5, tables pf+0x58e88 / 0x58e90
        cast_cell(world, m, (m.x + WANDER_DX[o], m.y + WANDER_DY[o]), n)
    elif n == spells.TELEPORT and chebyshev((t.x, t.y), (m.x, m.y)) > 2:
        base = word(t.x, t.y) - 0x101
        found = 0
        for row in range(3):
            for col in range(3):
                c = (base + row * 0x100 + col) & 0xFFFF
                if can_stand(world, m, unword(c)):
                    found = c
                    break
            if found:
                break
        if found:
            cast_cell(world, m, unword(found), n)
    m.ai_cast = True


def ring_cells(cell, r):
    """`FUN_0054ec6a(cell, r)` cell order: the centre, then per ring k = 1..r the cells (x+i, y+k), (x+i, y-k) for i = -k..k and, when |i| != k,
    (x+k, y+i), (x-k, y+i); packed 16-bit cell arithmetic (y << 8 | x)."""
    w0 = word(*cell)
    out = [cell]
    for k in range(1, (r & 0xFF) + 1):
        for i in range(-k, k + 1):
            out.append(unword((w0 + k * 0x100 + i) & 0xFFFF))
            out.append(unword((w0 - k * 0x100 + i) & 0xFFFF))
            if abs(i) != k:
                out.append(unword((w0 + i * 0x100 + k) & 0xFFFF))
                out.append(unword((w0 + i * 0x100 - k) & 0xFFFF))
    return out


def allied(world, owner, other):
    """Relation bit 2 of `owner`'s word for `other` (a player's word for itself is 0x12)."""
    pl = world.players.get(owner)
    return pl is not None and 0 < other <= len(pl.relations) and bool(pl.relations[other - 1] & 2)


def effect_active(u, n):
    """`u+0x144 & 1 << n`: the effect mask (`sim/effects.py`); Invisibility also when `Unit.hidden` was set without an effect object."""
    return effects.active(u, n) or (n == spells.INVISIBILITY and u.hidden)


def _ratio(o):
    """`(int)hp / (int)hp_max` as the exe divides (`idiv`, truncation toward zero), as a double."""
    return int(o.hp / o.hp_max) if o.hp_max else 2


def mage_idle(world, m):
    """`FUN_0056c592(m)` (ai.md 12.5): book and mana > 10, knows Heal: wounded -> heal itself; else the least healthy ally of the square of the heal
    range (`(int)(hp / hp_max) < 1`: the first wounded or dying one in ring order) -> heal it; else `friend_cast`."""
    if world.spell_table is None or not spells.known_mask(m) or m.mana <= IDLE_MANA:
        return
    if spells.wrapper_of(m, spells.HEAL) is None:
        return
    if m.hp != m.hp_max:
        cast_at(world, m, m, spells.HEAL)
        return
    sp = world.spell_table.get(spells.HEAL)
    r = spells.wrapper_range(sp, spells.Wrapper(spells.HEAL), spells.unit_level(m, sp))
    occ = mv._occupants(world, ring_cells((m.x, m.y), r))
    detectors = None
    keep = []
    for o in occ:                                       # FUN_00567b2d: allies only, a hidden one only when the group detects it
        if not allied(world, m.owner, o.owner):
            continue
        if o.hidden:
            if detectors is None:
                detectors = [d for d in world.units.values() if d.owner == m.owner and d.squad == m.squad and d.hp > 0]
            if not _detected(o, detectors):
                continue
        keep.append(o)
    best, bv = None, 2.0
    for o in keep:
        v = _ratio(o)
        if v < bv:
            best, bv = o, v
    if bv < 1.0:
        cast_at(world, m, best, spells.HEAL)
    else:
        friend_cast(world, m, keep)


def friend_cast(world, m, friends):
    """`FUN_0057a999(m, friends)` (ai.md 12.5): Shield (27) on itself when it knows it and it is not active; else a random friend of the list (one
    draw), of the same owner: wounded -> heal; else, at full mana, a random defensive spell (n = 1..28, not 24 / 27; one draw; an empty list leaves the
    loop's last lookup, Curse 28 when known) unless already active on it."""
    heal = spells.wrapper_of(m, spells.HEAL)
    if not (m.hp == m.hp_max or heal is None):
        cast_at(world, m, m, spells.HEAL)
        return True
    if spells.wrapper_of(m, spells.SHIELD) is not None and not effect_active(m, spells.SHIELD):
        cast_at(world, m, m, spells.SHIELD)
        return True
    k = _divide(world.rng, len(friends))
    f = friends[k] if k < len(friends) else None
    if f is None or f.owner != m.owner:
        return False
    if f.hp != f.hp_max and heal is not None:
        cast_at(world, m, f, spells.HEAL)
        return True
    if m.mana != m.mana_max:
        return False
    cands = [n for n in range(1, OWN_SPELLS) if n not in (spells.HEAL, spells.SHIELD) and _wrapper_ok(world, m, n, True)]
    k = _divide(world.rng, len(cands))
    n = cands[k] if cands else (spells.CURSE if spells.wrapper_of(m, spells.CURSE) is not None else 0)
    if not n or effect_active(f, n):
        return False
    cast_at(world, m, f, n)
    return True
