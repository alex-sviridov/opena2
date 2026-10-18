"""Movement system: a unit walks along `unit.path` cell by cell with the exe's rules.

Spec: docs/engine/simulation.md (formulas, exe addresses, update order).  Layer 4: reads and
writes `engine.world` only.  Fixed-point throughout: positions are cell * 256 + sub-cell, a
step is `step_len` units per tick, a cell takes `step_ticks` ticks.  No pathfinding and no
dynamic blocking for `FollowPath`: the path is taken as given.  `MoveTo` plans with the exe's two
layers (static plan, dynamic hops: `pathfinding.py`, docs/engine/simulation.md section 7).
"""

import math
import struct
from dataclasses import dataclass

from allods2.formats import progression as prog

from engine.world import NoWay

from .commands import Command
from .pathfinding import DEFAULT_CONFIG, PathGrid, chebyshev, follow_distance, foot, plan_dynamic, plan_static, unit_size
from allods2.formats import passability as pas

# Direction tables (path-finder object, CONFIRMED 0x553e4e..0x553f2f): 0 N, 1 NE, 2 E ... 7 NW.
DIR_DX = (0, 1, 1, 1, 0, -1, -1, -1)
DIR_DY = (-1, -1, 0, 1, 1, 1, 0, -1)
DIAGONAL = struct.unpack("<d", struct.pack("<Q", 0x3FE69FBE76C8B439))[0]    # double at 0x5d1aa8, 0.70699...
CENTRE = 128
MIN_STEP, MAX_STEP = 1, 63
SNAP_TURN = 0x20                # a turn of at most 45 degrees snaps (FUN_00556454)

IDLE_STATE, MOVE_STATE = 0, 1   # unit.state (+0x54)
NO_ORDER, MOVE_ORDER, ATTACK_ORDER, STAND_ORDER = 0, 1, 3, 0xC   # unit.order (+0x50): none, move to cell, attack, stand/guard
ATTACK_STATE = 3                # unit.state: melee swing (docs/engine/combat.md section 4)
STATIC_PLAN_FORCED = 0xFF       # mover.consumed value that forces a static re-plan (brain wrapper 0x56e4b0)
WAIT = "wait"                    # _drive result: a blocker wait began (not an ended order)
IDLE, MOVE, TURN, ATTACK = "idle", "move", "turn", "attack"       # unit.action (the client's actions 0, 1, 5, 3)


@dataclass(frozen=True)
class FollowPath(Command):
    """Debug order (not a player command): walk `unit_id` through `cells`, each entered in turn.
    Replaces the unit's path; a step already in progress is finished first."""
    unit_id: int
    cells: tuple

    def __post_init__(self):
        object.__setattr__(self, "cells", tuple((int(x), int(y)) for x, y in self.cells))


@dataclass(frozen=True)
class MoveTo(Command):
    """Debug order (not a player command; the player's is `MoveUnits`): a one-unit group move to cell (x, y),
    raw: no intake validation, no `& 0xff` wrap, no clamp.  Executed by `orders.py`.  Rejected: unknown or dead
    unit, cell outside the map."""
    unit_id: int
    x: int
    y: int


def expand_line(start, ends):
    """Cells from `start` (excluded) through each of `ends`, straight or at 45 degrees.
    ValueError if a leg is neither."""
    out, (x, y) = [], start
    for ex, ey in ends:
        dx, dy = ex - x, ey - y
        if dx and dy and abs(dx) != abs(dy):
            raise ValueError("(%d, %d) -> (%d, %d) is neither straight nor diagonal" % (x, y, ex, ey))
        sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
        for _ in range(max(abs(dx), abs(dy))):
            x, y = x + sx, y + sy
            out.append((x, y))
    return out


def unit_speed(u):
    """Speed stat (+0x8c): monsters the data.bin `speed`; humans the Reaction rule of the
    recompute (`progression.derived_speed`; the load penalty is not modelled); plus `speed_mod`
    (Haste/Slow effect delta)."""
    t = u.stats
    if t is None:
        base = 0
    elif u.human:
        base = prog.derived_speed(t, u.type_id)
    else:
        base = t.speed
    return base + u.speed_mod


def walk_speed(world, u):
    """Base speed of a step (`FUN_0055915a`): the unit's group speed byte (`record+0x44`) when non-zero, else the
    speed stat.  The group byte is set only by a formation move (docs/engine/simulation.md "Orders (H3)")."""
    g = world.groups.get(u.order_group)
    return g.speed if g is not None and g.speed else unit_speed(u)


def turn_rate(u):
    """Facing units per tick (mover+0xa).  Humans: the recompute copies the low byte of the speed
    stat (`FUN_0051366b`, `0x513ffc`-`0x514005`), so a hero turns as fast as it walks; the
    constructor default 8 of `FUN_0050ec60` is overwritten.  Others: the data.bin value."""
    if u.human and u.stats is not None:
        return max(1, unit_speed(u) & 255)
    return max(1, u.mover.turn_rate)


def dir8(facing):
    return ((facing + 16) & 255) >> 5


def facing_to(frm, to):
    """Target facing of a step (FUN_0054f618): dir8 * 32 from the signs of the cell delta."""
    sx, sy = (to[0] > frm[0]) - (to[0] < frm[0]), (to[1] > frm[1]) - (to[1] < frm[1])
    for d in range(8):
        if (DIR_DX[d], DIR_DY[d]) == (sx, sy):
            return d * 32
    return None


def step_length(world, u, frm, d):
    """Units per tick (1..63) of a step from cell `frm` in direction `d` (FUN_00559195).
    Ground units: speed * SpeedMultiplier, +- v*|dh|/64 for the height step (dh = from - to,
    clamped to +-32; downhill is faster), divided by the mean of the two cell costs (8 when 0);
    other movers keep the speed."""
    base = walk_speed(world, u)
    if u.move_type == 1:
        to = (frm[0] + DIR_DX[d], frm[1] + DIR_DY[d])
        dh = max(-32, min(32, int(world.heights[frm[1], frm[0]]) - int(world.heights[to[1], to[0]])))
        v = base * world.speed_multiplier
        v += (v * dh) >> 6 if dh >= 0 else -((v * -dh) >> 6)
        c = ((int(world.cost[frm[1], frm[0]]) + int(world.cost[to[1], to[0]])) & 255) >> 1
        v //= c or 8
    else:
        v = base
    return max(MIN_STEP, min(MAX_STEP, v))


def step_components(v, d):
    """(dx, dy) per tick: v on an axis, trunc(v * 0.707) on each axis of a diagonal."""
    sx, sy = DIR_DX[d], DIR_DY[d]
    if sx * sy == 0:
        return v * sx, v * sy
    return int(v * sx * DIAGONAL), int(v * sy * DIAGONAL)


def step_ticks(dx, dy):
    """Ticks to cross one cell: ceil(256 / the larger component) (the x one when non-zero)."""
    mag = abs(dx) if dx else abs(dy)
    return -(-256 // (mag or 1))


def _fold(a, b):
    """Angle between two bytes, 0..128."""
    d = abs(a - b)
    return d if d <= 0x80 else 0x100 - d


def _turn_step(u):
    """One tick of turning (FUN_005551ef): snap when closer than the rate, else one rate step."""
    m, rate = u.mover, turn_rate(u)
    d = _fold(u.facing, m.target_facing)
    if d < rate:
        u.facing = m.target_facing
    elif (u.facing + d) & 255 == m.target_facing:
        u.facing = (u.facing + rate) & 255
    elif (u.facing - d) & 255 == m.target_facing:
        u.facing = (u.facing - rate) & 255


def _turn_toward(u, target):
    """Start or continue a turn (FUN_00556454).  Within 45 degrees a fresh turn snaps (1 tick);
    otherwise one `turn_rate` step per tick, `turn_ticks` = ceil(angle / rate)."""
    m = u.mover
    m.target_facing = target
    d = _fold(u.facing, target)
    if not m.turning:
        m.turn_done = 0
    if not m.turning and d <= SNAP_TURN:
        u.facing = target
        m.turn_ticks = 1
    else:
        _turn_step(u)
        m.turn_ticks = -(-d // turn_rate(u))
    m.turning = True
    m.turn_done += 1
    if u.facing == target:
        m.turning = False


def _set_action(world, u, action):
    if u.action != action:
        u.action, u.action_start_tick = action, world.tick


def _advance(world, u):
    """One tick of an ongoing step (FUN_00554fd2): move by (dx, dy); the unit enters the next
    cell (spatial index updated) when the position crosses a cell boundary; at `step_ticks` the
    sub-cell offset snaps to the centre."""
    m = u.mover
    m.steps += 1
    x16, y16 = (u.x << 8) | u.sub_x, (u.y << 8) | u.sub_y
    nx, ny = (x16 + m.dx) & 0xFFFF, (y16 + m.dy) & 0xFFFF
    if m.step_dir in (1, 5) and nx & 255 == 0 and ny & 255 == 0:
        nx = (nx - 1) & 0xFFFF                                  # corner quirk of the exe
    if (nx >> 8, ny >> 8) == (u.x, u.y):
        u.sub_x, u.sub_y = nx & 255, ny & 255
    else:
        world.move_unit(u.id, nx >> 8, ny >> 8, nx & 255, ny & 255)
    if m.steps >= m.step_ticks:
        u.sub_x = u.sub_y = CENTRE
    u.odometer = int(u.odometer + math.hypot(m.dx, m.dy))


def _end_step(u):
    m = u.mover
    u.state = IDLE_STATE            # the Brain tick clears the state at a centre (R 3.4); the next step sets it again
    m.step_len = m.step_ticks = m.steps = 0
    m.step_target = m.step_from = None


def _start_step(world, u):
    """Next waypoint at a cell centre (FUN_00555c7e): face it (turning takes ticks, no move),
    then compute the step and make its first move in the same tick."""
    m = u.mover
    here = (u.x, u.y)
    target = u.path[0]
    face = facing_to(here, target)
    m.target_facing = face
    if u.facing != face:
        u.state = MOVE_STATE
        _set_action(world, u, TURN)
        _turn_toward(u, face)
        return
    u.path.pop(0)
    u.state = MOVE_STATE
    d = dir8(u.facing)
    m.step_target, m.step_from, m.step_dir = target, here, d
    m.step_len = step_length(world, u, here, d)
    m.dx, m.dy = step_components(m.step_len, d)
    m.step_ticks = step_ticks(m.dx, m.dy)
    m.steps = 0
    _set_action(world, u, MOVE)
    _advance(world, u)


def _in_map(world, c):
    return 0 <= c[0] < world.width and 0 <= c[1] < world.height


def apply_follow_path(world, cmd):
    """Order 1 with a hand-given path.  Rejected (unit unchanged): unknown or dead unit, empty
    path, a cell outside the map, a cell that is not adjacent to the previous one (the exe walks
    one cell per step)."""
    u = world.units.get(cmd.unit_id)
    if u is None or u.hp <= 0 or not cmd.cells or not all(_in_map(world, c) for c in cmd.cells):
        return False
    prev = u.mover.step_target or (u.x, u.y)
    for c in cmd.cells:
        if max(abs(c[0] - prev[0]), abs(c[1] - prev[1])) != 1:
            return False
        prev = c
    u.path = list(cmd.cells)
    u.mover.goal = u.mover.dest = u.mover.tail = None
    u.mover.static_path = []
    u.order, u.state = MOVE_ORDER, MOVE_STATE
    u.mode_go = True
    u.mode_attack = False
    u.mover.waiting = u.mover.parked = False
    return True


def path_grid(world, move_type):
    """Static PathGrid for a mover class (block layer masked with the mover byte, terrain costs), cached
    per block revision."""
    cache = world.__dict__.setdefault("_path_grids", {})
    if move_type not in pas.MOVE_MASK:
        move_type = 1                   # humans carry movementType -1 in data.bin and take the walker mask (map.md part 3)
    key = (move_type, world.block_rev, id(world.cost))
    g = cache.get(key)
    if g is None:
        cache.clear()
        blocked = (world.block & pas.MOVE_MASK[move_type]) != 0
        g = cache[key] = PathGrid.from_arrays(blocked, world.cost if move_type == 1 else None)
    return g


UNIT_STAMP_GROUND, UNIT_STAMP_AIR = 0x40, 0x80   # live-layer bits of FUN_00550de0 / FUN_00550e12 (CONFIRMED)


def unit_stamp(u):
    """Live-layer bit a unit's footprint sets: 0x80 for movement class 3 (flyer), else 0x40
    (`FUN_0055c2ce` picks the slot by the class from vtable +0x20, `FUN_00550a96` stamps it)."""
    return UNIT_STAMP_AIR if u.move_type == 3 else UNIT_STAMP_GROUND


def _footprint(o, cell):
    """The `size x size` cells of unit `o` anchored at `cell` (FUN_00550697 / FUN_0055020a loop order)."""
    n = unit_size(o)
    return [(cell[0] + i, cell[1] + j) for j in range(n) for i in range(n)]


def live_cells(world, u):
    """Cells the other units stamp into the live layer as seen by mover `u` (CONFIRMED
    docs/engine/simulation.md 7.3, 7.4): every other unit holds its `size x size` footprint at its cell and, while
    a step is in progress, at the other end of the step: the cell it is entering until it crosses the border,
    the cell it left after (FUN_00554fd2 0x555173: `FUN_0055be86(unit, old cell, 0)` after the move, so the old
    cell is held until the step end, FUN_00555b38).  The stamp is 0x40 (ground classes) or 0x80 (flyers), so only
    movers whose mask contains it (0x41/0x44 resp. 0x82) are blocked.  A unit with HP <= 0 keeps its stamps until
    it is removed (FUN_00510a70 -> FUN_00553891 is the only release, at state 0x10).  The exe's first-come slot
    per cell does not change the set of blocked cells, only who owns the record (`_blocker`)."""
    seen = pas.MOVE_MASK.get(u.move_type, pas.MOVE_MASK[1])
    out = set()
    for o in world.units.values():
        if o is u or not (unit_stamp(o) & seen):
            continue
        origins = [(o.x, o.y)]
        if o.mover.step_target:
            origins.append(tuple(o.mover.step_target))
        if o.mover.step_from:
            origins.append(tuple(o.mover.step_from))
        for origin in origins:
            out.update(_footprint(o, origin))
    return out


def _is_human(world, u):
    p = world.players.get(u.owner)
    return bool(p and p.human)


def _static_plan(world, u):
    """FUN_00555411 step 2: plan the whole way, reset the hop state."""
    m, here = u.mover, (u.x, u.y)
    res = plan_static(path_grid(world, u.move_type), here, m.goal, size=unit_size(u),
                      walker=u.move_type == 1, human=_is_human(world, u))
    m.static_path = list(res.cells)
    m.dest = m.goal
    m.arrived = False
    m.tail = m.static_path[-1] if m.static_path else here
    m.failed = not m.static_path
    m.consumed = 0
    u.path = []                                         # the dynamic list is cleared
    m.last_plan = res
    if res.reason in ("fallback", "unreachable"):
        _maybe_no_way(world, u, res)


def _maybe_no_way(world, u, res, goal=None):
    """`FUN_0054d76e` 0x54e1c7..0x54e240: after the cell fallback the planner posts message 0x92 ("No way") when
    the end cell is more than 1 cell from the target (more than 2 when the target is a building cell:
    `FUN_00559bc9` = the cell record holds a structure).  No fallback cell: the packed end is 0, cell (0, 0)."""
    goal = u.mover.goal if goal is None else goal
    end = res.end if res.end is not None else (0, 0)
    limit = 2 if world._claim.get(tuple(goal)) is not None else 1
    if chebyshev(end, goal) > limit:
        world.events.append(NoWay(u.owner, world.tick))


def _hop_plan(world, u, follow=None):
    """FUN_00555dc2: plan a short hop towards a point of the static plan over the live layer.  `follow`: the target `Unit` of a follow
    driver (`FUN_00555dc2(unit, target)`): the hop plan then uses the follow fallback round that unit."""
    m, cfg, here = u.mover, DEFAULT_CONFIG, (u.x, u.y)
    n = len(m.static_path)
    head = m.static_path[0] if n else None
    d = chebyshev(here, head) if n else 0
    if n > cfg.static_isnt_needed:
        goal = head if d > cfg.dynamic_by_static_lookup else m.static_path[cfg.dynamic_by_static_lookup]
        final = False
    else:
        goal, final = m.tail, True
    grid = path_grid(world, u.move_type).with_blocked(live_cells(world, u))
    res = plan_dynamic(grid, here, goal, size=unit_size(u), walker=u.move_type == 1,
                       follow=None if follow is None else (foot(u), foot(follow)))
    # FUN_0054e886 push-fronts the new cells onto the list it is given and never clears it (only the static
    # plan, mode != 0, clears its list first, FUN_0054d76e 0x54d7be): a non-empty dynamic list (a turn in
    # progress at the centre re-planning after DynamicRefreshRate ticks) keeps its old cells behind the hop.
    # A walk of more than 1000 steps empties the whole list (RemoveAll, 0x54eb5c); no end cell leaves it alone.
    u.path = [] if res.reason == "too long" else list(res.cells) + u.path
    m.last_hop, m.last_hop_goal = res, goal
    if not u.path and final:
        m.failed = True
    if n and d <= cfg.dynamic_by_static_lookup:
        m.static_path.pop(0)


def _occupants(world, cells, skip=None):
    """Units whose cell-record occupant slot (rec+4, FUN_005503af / FUN_00551edb) covers one of `cells`: ground
    classes (1, 2) only (class 3 uses rec+8, which FUN_00551edb never reads), at the current `size x size` footprint
    only (the slot moves at the border crossing, not with the live stamps), dead units included.  Several units
    on one cell: the one that entered it first keeps the slot (`Unit.cell_seq`)."""
    want = set(cells)
    found = [o for o in world.units.values()
             if o is not skip and o.move_type != 3 and want.intersection(_footprint(o, (o.x, o.y)))]
    found.sort(key=lambda o: o.cell_seq)
    return found


def _blocker(world, u, cell):
    """`FUN_00551edb(cell)`: the occupant of the cell record (the first-come unit whose current footprint holds
    `cell`), or None.  A unit that only stamps the cell (entering it, or leaving it after the border) is not one."""
    found = _occupants(world, [tuple(cell)], skip=u)
    return found[0] if found else None


def _at_centre(o):
    return (o.sub_x, o.sub_y) == (CENTRE, CENTRE)           # FUN_00551383


def _mode_move(o):
    """Brain mode 1 or 4 (CONFIRMED consumers 0x56fdca/0x56fddd): a unit walking a move order.  Mode 4 (approach
    an object, FUN_0056ea52 -> follow driver FUN_0055574d) gets the same verdict as mode 1 (CONFIRMED); it needs
    attack orders and is not modelled."""
    return o.mode_go and not o.mover.waiting and not o.mover.parked


def blocker_verdict(world, u, cell):
    """FUN_0056fc69: 0 = re-plan around the blocker, 1 or 2 = wait for it (the driver treats both alike).
    Only a size-1 unit of the human player waits (vtable +0x1c == 1, owner +0x2c == 0)."""
    if unit_size(u) != 1 or not _is_human(world, u):
        return 0
    b = _blocker(world, u, cell)
    if b is None:
        # no occupant: `FUN_0054ec6a(cell, 1)` lists the occupants of the 3x3 around the cell; one that began its
        # step on `cell` (mover+0x70) and is still off-centre (it crossed the border and left `cell`) -> 2
        ring = [(cell[0] + i, cell[1] + j) for j in (-1, 0, 1) for i in (-1, 0, 1)]
        for o in _occupants(world, ring, skip=u):
            if o.mover.step_from and tuple(o.mover.step_from) == tuple(cell) and not _at_centre(o):
                return 2
        return 0
    if b.hp < 1:
        return 0
    if not _at_centre(b):                                   # mid-step: wait unless I last entered `cell`
        return 0 if u.mover.step_target == tuple(cell) else 1
    if not _mode_move(b):                                   # idle, waiting, turning: go round
        return 0
    return 0 if u.mover.goal == tuple(cell) else 2          # never wait for the cell I am walking to


def _begin_wait(world, u, cell):
    """FUN_00555411 after a non-zero verdict: face the blocker (FUN_00556b2c/da2); already facing it ->
    brain mode 0 at once, else mode 10 and the turn."""
    m = u.mover
    face = facing_to((u.x, u.y), cell)
    m.target_facing = face
    if u.facing == face:
        m.parked = True
        _set_action(world, u, IDLE)
        return
    m.waiting = True
    u.state = MOVE_STATE
    _set_action(world, u, TURN)
    _turn_toward(u, face)


def _tick_wait(world, u):
    """Brain mode 10 (FUN_0056e55d): keep turning to mover+1; once facing it, mode 0 (the move order stays but
    nothing drives it any more, INFERRED: only a new command restarts it)."""
    m = u.mover
    if u.facing != m.target_facing:
        u.state = MOVE_STATE
        _turn_toward(u, m.target_facing)
        return
    u.state = IDLE_STATE
    m.waiting, m.parked = False, True
    _set_action(world, u, IDLE)


def _drive(world, u):
    """The move driver at a cell centre (FUN_00555411 steps 2-4, wrapper 0x56e4b0).  Returns False when
    the order ended."""
    m, cfg, here = u.mover, DEFAULT_CONFIG, (u.x, u.y)
    if m.dest != m.goal:                                # wrapper: target changed -> force a static re-plan
        m.consumed = STATIC_PLAN_FORCED
    if here == m.goal:
        return False                                    # nothing to do; the group pass ends the order
    m.since_hop = (m.since_hop + 1) & 255              # byte at mover+0x78, wraps (0x55549a)
    if m.dest != m.goal or m.consumed > cfg.static_refresh_rate:
        _static_plan(world, u)
    if here == m.tail:
        m.arrived = True                                # mover+0x90; the order ends at the group pass
        return False
    if not u.path or m.since_hop > cfg.dynamic_refresh_rate:
        head = m.static_path[0] if m.static_path else None
        if (head is not None and chebyshev(here, head) == 1
                and head in live_cells(world, u) and blocker_verdict(world, u, head)):
            _begin_wait(world, u, head)
            return WAIT                                     # no hop plan, no step; the order stays
        _hop_plan(world, u)
        m.consumed = (m.consumed + 1) & 255
        m.since_hop = 0
    return True


def cancel(u):
    """`FUN_0056dbfb` = `FUN_0056d969` + `brain+0x50 := 0` (R 3.4): the target facing becomes the facing (a turn in
    progress stops where it is), the state is 0.  A step in progress is NOT aborted (the Brain tick keeps running
    it) and a reservation is kept mid-step; at a centre the engine has no reservation to release (the live layer is
    derived from positions).  Plans, `dest`, `turning` and the dynamic list are untouched."""
    u.mover.target_facing = u.facing
    u.mover.follow = None                       # FUN_0056d969: mover+0x7c := 0
    u.state = IDLE_STATE
    u.stopped = False


def stop_unit(world, u):
    """`FUN_0056dbc6`: cancel, then order 0xc with the anchor on the own cell and Brain mode 0 (`FUN_0056dba1` ->
    `FUN_0056d52b`), and `brain+0x50 := 1`.  Used by the group pass at arrival (the only caller of the move
    group's handler, `FUN_00573198`)."""
    cancel(u)
    set_stand(world, u)
    u.stopped = True


def fail_stop(world, u):
    """`FUN_0056dc24` (the failure of an order 1, `0x56e1d9`): `FUN_0056d969` then `FUN_0056dba1` = cancel (which
    clears `brain+0x50`) and `FUN_0056d52b`.  Unlike `FUN_0056dbc6` it does NOT set `brain+0x50` (CONFIRMED
    asm 0x56dc24-0x56dc46, 0x56dba1-0x56dbc3): the group pass will restart the unit (unit-struct 8.1)."""
    cancel(u)
    set_stand(world, u)


def set_stand(world, u):
    """`FUN_0056d52b`: order 0xc (stand/guard), anchor = the own cell, mode 0."""
    cancel(u)
    u.mode_go = False
    u.mode_attack = False
    u.order = STAND_ORDER
    u.anchor = (u.x, u.y)
    u.mover.waiting = u.mover.parked = False
    if not u.mover.step_ticks:
        _set_action(world, u, IDLE)


def set_move(world, u, x, y):
    """`FUN_0056d032` after the clamp: order 1, destination (x, y), `mover+0x90` (arrived) and the failure flag
    cleared, Brain mode 1.  The cancel comes first."""
    cancel(u)
    m = u.mover
    u.order = MOVE_ORDER
    u.mode_go = True
    u.mode_attack = False
    u.anchor = None
    m.goal = (x, y)
    m.arrived = m.failed = False
    m.waiting = m.parked = False


def _tick_unit(world, u):
    """One creature tick (`FUN_0050f12c`): the Brain tick (`FUN_0056dca2`), then the failure event, then the state switch: state 3 runs the
    swing phases (`sim/combat.py`).  A unit without HP gets no Brain tick (death is phase I2).

    The failure event: `mover+0x98` ends an order 1 at once (`0x56e1b0` -> `FUN_0056dc24` = cancel + order `0xc`, `brain+0x50`
    stays 0), unlike arrival, which waits for the group pass.  Under any other order the event sets Brain mode 0 (`0x56e320`: the auto
    target scan `FUN_0056ed4e` finds no enemy; the scan and the computer players' mode 0xb are phase I, combat.md 9.3)."""
    if u.hp <= 0:
        return
    _tick_inner(world, u)
    m = u.mover
    if m.failed:
        m.failed = False
        if u.order == MOVE_ORDER:
            fail_stop(world, u)
        else:
            u.mode_go = False
            u.mode_attack = False
    if u.state == ATTACK_STATE:
        combat.swing_tick(world, u)


def _tick_inner(world, u):
    m = u.mover
    if u.brain_order == combat.BRAIN_SWING:              # Brain order 1: the swing runs, no mode (FUN_0056dca2 order switch)
        combat.brain_swing(u)
        return
    if m.step_ticks:                                    # a step is in progress (FUN_00555b38)
        u.state = MOVE_STATE
        _advance(world, u)
        if (u.sub_x, u.sub_y) == (CENTRE, CENTRE):
            _end_step(u)
            if m.goal is not None:
                u.path = []             # FUN_00555b38 clears the dynamic list (+0x1e4) at every step end
        return
    if u.mode_attack:                                   # Brain mode 5 (FUN_0056eab5)
        combat.attack_mode(world, u)
        return
    if not u.mode_go or m.parked:
        return
    if m.waiting:
        _tick_wait(world, u)
        return
    if m.goal is not None:
        r = _drive(world, u)
        if r is WAIT:
            return
        if not r:                                       # at the goal or at the end of the plan: stand, order stays
            u.state = IDLE_STATE
            _set_action(world, u, IDLE)
            return
    if u.path:
        _start_step(world, u)
    elif m.goal is None:                                # FollowPath (debug): the path is done
        u.order, u.state = NO_ORDER, IDLE_STATE
        m.target_facing = u.facing
        _set_action(world, u, IDLE)
    else:                                               # no hop yet: wait for the next tick's driver
        u.state = IDLE_STATE
        _set_action(world, u, IDLE)


def follow_drive(world, u, t):
    """The follow driver `FUN_0055574d(unit, target, range)` (docs/engine/simulation.md 7.4, combat.md 3.4), called by Brain mode 5 with
    `range = u.range` while the target is out of range.  Same two layers as the move driver, planned towards the target's cell:
    at a centre and within range it turns to the target and nothing else; otherwise a static re-plan when the target changed or
    `consumed > len(static) / 3 + 1`, arrival at the hop goal, a hop plan with the follow fallback, and (by the caller) the step.
    The not-at-centre branch (`FUN_00555b38`) is the step branch of `_tick_inner`: the Brain never gets here mid-step."""
    m, cfg, here = u.mover, DEFAULT_CONFIG, (u.x, u.y)
    tcell = (t.x, t.y)
    if follow_distance(foot(u), foot(t)) <= u.range:
        face = combat.octant(foot(u), foot(t))          # FUN_00556d78 = FUN_00556454(unit, FUN_005568e4(unit, target))
        if u.facing != face or m.turning:
            _set_action(world, u, TURN)
        _turn_toward(u, face)
        return False
    m.since_hop = (m.since_hop + 1) & 255               # byte at mover+0x78
    if m.follow != t.id:                                # a new object: force the static re-plan
        m.consumed = STATIC_PLAN_FORCED
        m.static_path = []
        m.static_len = 0xFF
        m.tail = m.follow_cell = tcell
    if m.consumed > len(m.static_path) // 3 + 1:
        if m.static_len <= cfg.static_isnt_needed:      # short list: no search, the list becomes its old tail cell
            m.static_path = [m.tail]
        else:
            res = plan_static(path_grid(world, u.move_type), here, tcell, size=unit_size(u),
                              walker=u.move_type == 1, human=_is_human(world, u))
            m.static_path = list(res.cells)
            m.last_plan = res
            if res.reason in ("fallback", "unreachable"):
                _maybe_no_way(world, u, res, tcell)
        m.static_len = len(m.static_path)
        m.dest = tcell
        if not m.static_path:
            m.tail, m.follow_cell, m.failed = here, tcell, True
        else:
            m.tail, m.follow_cell = m.static_path[-1], tcell
        m.follow = t.id
        m.consumed = 0
        if m.static_len > cfg.static_isnt_needed:
            u.path = []
    if here == m.tail and m.follow_cell == tcell:       # arrived at the hop goal: no step this tick
        m.consumed = (m.consumed + 1) & 255
        m.follow = None
        return False
    if not u.path or m.since_hop > cfg.dynamic_refresh_rate:
        if u.facing == m.target_facing:
            _hop_plan(world, u, follow=t)
            m.consumed = (m.consumed + 1) & 255
            m.since_hop = 0
    return True


def movement_system(world, commands):
    """Apply the tick's `FollowPath` commands, then update every unit in list order (the exe:
    FUN_004f84c6 drains the commands, FUN_004f04cf walks the creature list).  The player's orders are
    applied by `orders.orders_system`, which runs before."""
    for cmd in commands:
        if isinstance(cmd, FollowPath):
            apply_follow_path(world, cmd)
    for u in list(world.units.values()):
        _tick_unit(world, u)


from . import combat    # noqa: E402  the fight code imports this module: bound here, used at call time (circular on purpose)
