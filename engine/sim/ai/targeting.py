"""targeting: part of the monster AI (docs/engine/ai.md); see the package docstring in __init__."""

from .. import combat as cb, effects, movement as mv
from ..pathfinding import chebyshev, foot, unit_size
from .perception import NO_TARGET


# FUN_005711ea preference table (server+0xa54, built at 0x56827a..0x568310), index attacker class * 4 + candidate class
PREFERENCE = (2, 1, 2, 4, 4, 2, 1, 0, 2, 1, 4, 0, 2, 1, 2, 4)


def _pref_and_distance(world, me, cand):
    """The shared prologue of `score` and `score_stand`: the preference-table entry and the cell distance (a ranged attacker's is
    `max(1, distance - range + 1)`)."""
    d = chebyshev((cand.x, cand.y), (me.x, me.y))
    cls = cb.move_class(cand)
    if cls == 1 and cb.attack_range(world, cand) > 1:
        cls = 0
    my_range = cb.attack_range(world, me)
    if my_range > 1:
        pref = PREFERENCE[cls]
        d = d - my_range + 1 if d > my_range else 1
    else:
        pref = PREFERENCE[cb.move_class(me) * 4 + cls]
    return pref, d


def score(world, me, cand):
    """`FUN_005711ea(me, cand)`: distance * 256 + facing difference, adjusted by the preference table; 0xffffff = not a target."""
    pref, d = _pref_and_distance(world, me, cand)
    ang = mv._fold(me.facing, cb.octant(foot(me), foot(cand)) & 0xFF)
    s = d * 256 + ang
    if pref == 0:
        return NO_TARGET
    small = unit_size(me) < 2 and int(me.stats.get("mind", 0) if me.stats is not None else 0) >= 15
    if pref == 1 and small:
        s += s >> 1
    elif pref == 4 and small:
        s -= s >> 2
    if cand.effect_mask & effects.STONE_BIT:            # 0x5713c7: a stoned target scores 0x7f worse (at least 1)
        s += 0x7F
        if s < 1:
            s = 1
    return s


def score_stand(world, me, cand):
    """`FUN_005713f8(me, cand)`, the score of the stand-ground pass (group order 3, `FUN_005725a8`): the same terms as `score`, but the
    candidate must be within reach at once: the cell distance (melee) or `max(1, distance - range + 1)` (ranged) must be below 2, i.e. an
    adjacent cell or inside the attack range; the preference then only doubles (1) or halves (4) the score (no mind / HP clause, no `0x40000`)."""
    pref, d = _pref_and_distance(world, me, cand)
    if d >= 2 or pref == 0:
        return NO_TARGET
    s = d * 256 + mv._fold(me.facing, cb.octant(foot(me), foot(cand)) & 0xFF)
    if pref == 1:
        s *= 2
    elif pref == 4:
        s >>= 1
    return s
