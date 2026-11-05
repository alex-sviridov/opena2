"""Follow, defend and patrol orders and Brain mode 4 (docs/engine/ai.md 14.2).

The scripted group sub-commands 11 (defend), 14 (patrol) and 15 (follow) of the Scenario instant `FUN_00577cee` give every member a unit order:
`FUN_0056d5b9` (order 8, defend), `FUN_0056d6b7` (order 0xa, patrol), `FUN_0056d638` (order 0x11, follow).  The executors run in the group
pass of a group with order 0 (`FUN_00569321`, every 16 ticks): `FUN_005696e8`, `FUN_00569b62`, `FUN_00569857`.  Layer 4: reads and writes
`engine.world` only.
"""

from engine.world import DEAD

from . import ai, combat as cb, movement as mv
from .pathfinding import chebyshev

FOLLOW_DEFAULT = 3              # `FUN_0056d5b9` / `FUN_0056d638`: brain+0x70 when the range argument is 0
DEFEND_ORDER, PATROL_ORDER, FOLLOW_ORDER = 8, 0xA, 0x11
DEFEND_RADIUS = 5               # `FUN_00567945` / `FUN_00567988`: the square of radius mover+8 (5) round the leader / the anchor


def _clear_modes(u):
    u.mode_go = u.mode_attack = u.mode_cast = u.mode_cell = u.mode_look = u.mode_follow = False


def _set_leader(world, u, leader, rng, order):
    """`FUN_0056d5b9` (order 8) / `FUN_0056d638` (order 0x11): cancel; a member that is its own leader stands (`FUN_0056dba1`); else the order, the
    leader `brain+0x10`, Brain mode 0, the range `brain+0x70` (3 when the argument is 0)."""
    mv.cancel(u, world)
    if u is leader:
        mv.set_stand(world, u)
        return
    u.order = order
    u.leader = leader.id
    _clear_modes(u)
    u.mover.waiting = u.mover.parked = False
    u.follow_range = (rng & 0xFF) or FOLLOW_DEFAULT


def set_defend(world, u, leader, rng):
    _set_leader(world, u, leader, rng, DEFEND_ORDER)


def set_follow(world, u, leader, rng):
    _set_leader(world, u, leader, rng, FOLLOW_ORDER)


def set_patrol(world, u, x, y):
    """`FUN_0056d6b7(unit, x, y)`: cancel; order 0xa; anchor `brain+0` := the own cell; the waypoint list (`brain+0xb4`) := [own cell, `y << 8 | x`]
    (the bytes as given: no clamp); the first waypoint `brain+2` := the list's tail, i.e. the target; `brain+4` := 0; Brain mode 0."""
    mv.cancel(u, world)
    u.order = PATROL_ORDER
    u.anchor = (u.x, u.y)
    u.patrol = [(u.x, u.y), (x & 0xFF, y & 0xFF)]
    u.patrol_wp = u.patrol[-1]
    u.patrol_walk = False
    _clear_modes(u)
    u.mover.waiting = u.mover.parked = False


def set_mode4(world, u, leader, rng):
    """`FUN_0056c960(unit, object, range)`: Brain mode 4 towards the object; `brain+0x14` := the range (the scan range byte `+0xa5` when 0)."""
    _clear_modes(u)
    u.mode_follow = True
    u.follow_target = leader.id
    u.range = rng if rng else ai._scan_range(u, world)
    u.mover.waiting = u.mover.parked = False


def approach_mode(world, u):
    """Brain mode 4 (`FUN_0056ea52`): the follow driver towards `brain+0x18` within `brain+0x14`, state 1 -- the approach half of mode 5
    (`combat.attack_mode`).  A target id the world freed ends the mode (INFERRED: the exe dereferences a dangling pointer)."""
    t = world.find_unit(u.follow_target)
    if t is None:
        u.mode_follow = False
        return
    step = mv.follow_drive(world, u, t)
    u.state = mv.MOVE_STATE
    if step:
        mv._step_or_turn(world, u)
    elif not u.mover.turning:
        mv._set_action(world, u, mv.IDLE)


# --- the executors (FUN_00569321 cases 8, 0xa, 0x11) ---------------------------------------------------------------------------------

def _leader(world, u):
    """The followed object; a leader in state 0x10 (or one the world freed) ends the order with a stop (`FUN_00569321` `0x569361`)."""
    t = world.find_unit(u.leader)
    if t is None or t.state == DEAD:
        mv.stop_unit(world, u)
        return None
    return t


def _gap(u, t):
    """`FUN_00551463`: the Chebyshev distance of the two cell positions (a byte)."""
    return chebyshev((u.x, u.y), (t.x, t.y)) & 0xFF


def _step_away(world, u, t, rng):
    """`FUN_00558b92(u, the leader's cell origin, range)` then `FUN_0056c8af`: a follower inside the leader's cell neighbourhood walks `range` cells away."""
    ai.go(world, u, ai.away_cell(world, u, t.x << 8, t.y << 8, rng))


def exec_follow(world, u):
    """`FUN_00569857` (order 0x11): beyond the range Brain mode 4 on the leader; touching (distance < 2) a step away; else the guard scan."""
    t = _leader(world, u)
    if t is None:
        return
    d, rng = _gap(u, t), u.follow_range
    if rng < d:
        set_mode4(world, u, t, rng)
    elif d < 2:
        _step_away(world, u, t, rng)
    elif world.ai_on:
        ai.guard_scan(world, u)                         # FUN_0056afac(u, 0); AI-off sims have no enemies to scan


def exec_defend(world, u):
    """`FUN_005696e8` (order 8): beyond the range Brain mode 4; in range the leader's surroundings are scanned (`FUN_0056a73b`; a unit with a
    spell list takes `FUN_00569968` first, which may Heal the leader: not built, the plain scan runs instead) and, when no attack or cast mode
    resulted and the distance is below 2, the unit steps away."""
    t = _leader(world, u)
    if t is None:
        return
    d, rng = _gap(u, t), u.follow_range
    if rng < d:
        set_mode4(world, u, t, rng)
        return
    if world.ai_on:
        defend_scan(world, u, t)
    if not (u.mode_attack or u.mode_cast or u.mode_cell) and d < 2:
        _step_away(world, u, t, rng)


def defend_scan(world, u, leader):
    """`FUN_0056a73b(u, leader)`: the hostiles in the square of radius 5 round the **leader** (`FUN_00567945`, relation of the leader's owner;
    class-3 units are dropped when the leader's range is below 2, `FUN_00567f49`).  Class-3 candidates win: the one with the smallest
    `FUN_00556dcd` gap to `u` (first on a tie); else the smallest gap overall (starts at 0xff, strict `<`); the pick is attacked (`FUN_0056acc8`).
    No candidate at all: the guard scan."""
    lst = ai.enemies_around(world, leader, leader.x, leader.y, DEFEND_RADIUS)
    if lst and ai.attack_range(world, leader) < 2:
        lst = [c for c in lst if cb.move_class(c) != 3]
    if not lst:
        ai.guard_scan(world, u)
        return
    best = None
    for c in lst:
        if cb.move_class(c) == 3 and (best is None or ai.reach_gap(u, c) < ai.reach_gap(u, best)):
            best = c
    if best is None:
        gap = 0xFF
        for c in lst:
            g = ai.reach_gap(u, c) & 0xFF
            if g < gap:
                best, gap = c, g
    if best is not None:
        ai.engage(world, u, best)


def guard_around(world, u):
    """`FUN_0056a5fc` (order 0xb's executor `FUN_00569cc9`, and the first step of a patrol): the anchor `brain+0` (0 -> the own cell); at or beyond the
    unit's scan range (`+0xa5`) from it, walk back; the hostiles in the square of radius 5 round the anchor (`FUN_00567988`): the first one is
    attacked; none: walk back when off the anchor, else the guard scan."""
    if u.anchor is None:
        u.anchor = (u.x, u.y)
    a = u.anchor
    if chebyshev((u.x, u.y), a) & 0xFF >= ai._scan_range(u, world):
        ai.go(world, u, ai.word(*a))
    lst = ai.enemies_around(world, u, a[0], a[1], DEFEND_RADIUS) if world.ai_on else []
    if lst:
        ai.engage(world, u, lst[0])
    elif (u.x, u.y) != tuple(a):
        ai.go(world, u, ai.word(*a))
    elif world.ai_on:
        ai.guard_scan(world, u)


def exec_patrol(world, u):
    """`FUN_00569b62` (order 0xa): Brain mode := 0; when the last pass left a walk running (`brain+4`) the anchor moves to the own cell; the guard
    around the anchor runs (a fight or a walk back wins); if the Brain is then idle (mode 0, or the look-around 0xb) the unit walks on: at the
    waypoint it takes the next one of the list (the one after the first equal entry, wrapping to the head) and goes there."""
    _clear_modes(u)
    if u.patrol_walk:
        u.anchor = (u.x, u.y)
        u.patrol_walk = False
    guard_around(world, u)
    if not (u.mode_go or u.mode_attack or u.mode_cast or u.mode_cell or u.mode_follow):
        u.patrol_walk = True
        wp = u.patrol_wp
        if (u.x, u.y) == wp:
            i = u.patrol.index(wp)                      # CList::Find: the first equal entry
            wp = u.patrol[i + 1] if i + 1 < len(u.patrol) else u.patrol[0]
        u.patrol_wp = wp
        ai.go(world, u, ai.word(*wp))


# --- the group sub-commands (FUN_00577cee 10, 11, 14, 15) ------------------------------------------------------------------------------

def defend_group(world, g, leader, rng):
    """`FUN_00570c84(g, u, n1)`: cancel the group, every member `FUN_0056d5b9`."""
    from . import orders
    orders._cancel_group(world, g)
    for i in list(g.members):
        set_defend(world, world.units[i], leader, rng)


def follow_group(world, g, leader, rng):
    """`FUN_00570cd5(g, u, n1)`."""
    from . import orders
    orders._cancel_group(world, g)
    for i in list(g.members):
        set_follow(world, world.units[i], leader, rng)


def patrol_group(world, g, x, y):
    """`FUN_00570d26(g, n1, n2)`."""
    from . import orders
    orders._cancel_group(world, g)
    for i in list(g.members):
        set_patrol(world, world.units[i], x, y)
