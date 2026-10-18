"""Combat: the hit formulas, geometry and timers (pure functions), then the order, approach and swing (system parts).

Spec: docs/engine/combat.md (C§ numbers in the comments); routine addresses are there.  Layer 4: reads and writes `engine.world` only.
"""

from typing import NamedTuple

from .combatstats import u8
from .pathfinding import centre_x, centre_y
from .pathfinding import follow_distance as reach_gap       # `FUN_00556dcd`: whole cells between footprints + 1 (touching = 1)

# --- hit resolution (C§5.2, `FUN_00516f6f`) -----------------------------------------------------


class HitResult(NamedTuple):
    damage: int         # what `take_hit` returns (>= 0)
    hit: bool           # the physical part passed the roll (`T + roll > D`, the 90 rule or the sure-hit flag)
    roll: int           # rand(200) - 100, or 0 when the defender was immune (nothing was drawn)
    phys: int           # physical part after absorption and resistance (before the total is floored)
    second: int         # second part
    elemental: int      # elemental part


def resist(x, percent):
    """`trunc(x * (100 - p) / 100 + 0.75)` with the x87 constants 100.0 and 0.75 (`__ftol` truncates toward zero)."""
    return int(x * (100 - percent) / 100.0 + 0.75)


def take_hit_detail(rec, block, rng, *, human=False, sure_hit=False, bless=None, curse=None, immune=False):
    """`FUN_00516f6f`: the damage of one blow of attack record `rec` against armour block `block`, drawing from `rng` in the exe's order
    (Bless draw, Curse draw, physical spread, roll, second spread, elemental spread).  `human`: the attacker is a human (no x15
    scaling); `sure_hit`: attacker flag `+0x4c & 0x10`; `bless` / `curse`: chance 0..100 of the active effect, None when absent;
    `immune`: defender flag `+0x4c & 8`."""
    if immune:
        return HitResult(0, False, 0, 0, 0, 0)
    lo, sp = rec.lo, rec.sp
    if lo & 0x80 and not human:
        lo = (lo & 0x7F) * 15
        sp = sp * 15
    fixed = False
    if bless is not None and bless > rng.rand(100):
        lo += sp
        fixed = True
    if curse is not None and curse > rng.rand(100):
        fixed = True
    phys = lo if fixed else lo + rng.rand(sp)
    roll = rng.rand(200) - 100
    attack = rec.skill + roll
    hit = attack > block.defence or sure_hit or roll >= 90
    d1 = phys if hit else 0
    if d1 > 0:
        if not sure_hit:
            d1 = max(d1 - block.absorb, 0)
        pct = block.res[rec.kind] if 0 <= rec.kind < len(block.res) else 0
        if pct:
            d1 = resist(d1, pct)
    total = d1
    d2 = 0
    if rec.lo2 + rec.sp2 > 0:                      # not gated by the roll
        d2 = rec.lo2 + rng.rand(rec.sp2)
        if block.prot[2]:
            d2 = max(resist(d2, block.prot[2]), 0)
        total += d2
    d3 = 0
    if rec.elo + rec.esp > 0 and (attack > block.defence or rec.lo + rec.sp == 0):
        d3 = rec.elo + rng.rand(rec.esp)
        if 1 <= rec.elem <= 5 and block.prot[rec.elem]:
            d3 = max(resist(d3, block.prot[rec.elem]), 0)
        if d3 > 0:
            total += d3
    return HitResult(max(total, 0), hit, roll, d1, d2, d3)


def take_hit(rec, block, rng, **kw):
    """Damage only (see `take_hit_detail`)."""
    return take_hit_detail(rec, block, rng, **kw).damage


# --- geometry (C§3.1, C§5.1) --------------------------------------------------------------------

def attack_gap(a, b):
    """`FUN_005169de`: the range test of the hit.  `D` = Chebyshev distance of the centres in 1/256 cells; `D' = D - (size_a + size_b - 2) * 128`;
    1 when `D' <= 384`, else `(D' + 64) >> 8`."""
    d = max(abs(centre_x(a) - centre_x(b)), abs(centre_y(a) - centre_y(b)))
    d -= (a.size + b.size) * 128 - 256
    return 1 if d <= 0x180 else (d + 0x40) >> 8


def in_attack_range(a, b, rng_byte):
    """C§5.1: the hit lands when `attack_gap <= range` (the byte `+0x12c`)."""
    return attack_gap(a, b) <= rng_byte


def octant(frm, to):
    """`FUN_005568e4`: the 8-way facing (multiples of 32, 0 = north, clockwise) from `frm` towards `to`, by the sign quadrants and the 2:1 ratio
    rule; `dx == 0` / `dy == 0` count as non-positive.  16-bit centres as in the exe."""
    dx = (centre_x(to) - centre_x(frm))
    dy = (centre_y(to) - centre_y(frm))
    a = (-dx if dx < 1 else dx) & 0xFFFF
    b = (-dy if dy < 1 else dy) & 0xFFFF
    if dx < 1:
        if dy < 1:
            code = (12 if b * 2 < a else 13) if b < a else (15 if a * 2 < b else 14)
        else:
            code = (11 if b * 2 < a else 10) if b < a else (8 if a * 2 < b else 9)
    elif dy < 1:
        code = (3 if b * 2 < a else 2) if b < a else (0 if a * 2 < b else 1)
    else:
        code = (4 if b * 2 < a else 5) if b < a else (7 if a * 2 < b else 6)
    if code:
        code += 1
    return u8((code >> 1) << 5)


# --- timers (C§4) -------------------------------------------------------------------------------

def hero_delay(weapon_weight, reaction):
    """`L`: `clamp((weight + (30 - Reaction) * 5) / 12, 0, 12)`, C integer division (truncation toward zero)."""
    v = int((weapon_weight + (30 - reaction) * 5) / 12)
    return 0 if v < 0 else 12 if v >= 12 else v


def attack_extra(gap):
    """Arrow flight added to the wind-up (`FUN_00516b2f`): `(gap * 256 + 128) / 200` when `gap > 1`, else 0."""
    return (gap * 256 + 128) // 200 if gap > 1 else 0


# --- who may attack whom (C§2.2, `FUN_005711ea`) ------------------------------------------------

# 4 x 4 bytes built in the order manager's constructor (0x56827a..0x568310): row = attacker class, column = target class.
ATTACK_MATRIX = ((2, 1, 2, 4), (4, 2, 1, 0), (2, 1, 4, 0), (2, 1, 2, 4))


def can_attack(att_move, att_range, tgt_move, tgt_range):
    """False when the matrix byte is 0: melee ground units and ghosts cannot attack flyers.  The target class is its movement type,
    0 for a ground unit that shoots; a shooter always reads row 0."""
    col = 0 if tgt_move == 1 and tgt_range > 1 else tgt_move
    row = 0 if att_range > 1 else att_move
    return ATTACK_MATRIX[row][col] != 0
