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

from engine.cellslots import pack
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
GUARD_ORDER, STILL_ORDER = 0xB, 0x17                             # guard post (G, the squads), stand still (L)
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
    (a test / debug offset) and the effects' `fx.speed` (Haste / Slow: docs/engine/effects.md 5)."""
    t = u.stats
    if t is None:
        base = 0
    elif u.human:
        base = prog.derived_speed(t, u.type_id)
    else:
        base = t.speed
    return base + u.speed_mod + u.fx.speed           # Haste / Slow: a monster's +0x8c, a human's bonus +0xd8 (docs/engine/effects.md 5)


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
        world.move_unit(u.id, nx >> 8, ny >> 8, nx & 255, ny & 255, crossing=True)
    if m.steps >= m.step_ticks:
        u.sub_x = u.sub_y = CENTRE
    u.odometer = int(u.odometer + math.hypot(m.dx, m.dy))


def _end_step(world, u):
    """`FUN_00555b38` at the centre: counters cleared, `FUN_0055be86` mode 2 then mode 1 (the origin stamp is dropped, the own cell stamped)."""
    m = u.mover
    world.slots.be86(u, 0, 2)
    world.slots.be86(u, 0, 1)
    u.state = IDLE_STATE            # the Brain tick clears the state at a centre (R 3.4); the next step sets it again
    m.step_len = m.step_ticks = m.steps = 0
    m.step_target = m.step_from = None


def _start_step(world, u):
    """Next waypoint at a cell centre (FUN_00555c7e): face it (turning takes ticks, no move),
    then compute the step and make its first move in the same tick."""
    m = u.mover
    here = (u.x, u.y)
    target = u.path[0]
    world.slots.be86(u, 0, 2)                                   # FUN_00555c7e 0x555cee-0x555d15, before the facing test: every call with a
    world.slots.be86(u, pack(*target), 0)                       # waypoint (also a turn tick) stamps the next cell and the own cell
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
    u.step_end = world.tick + m.step_ticks              # +0x138 (message 0x6b): the regeneration rest test
    _set_action(world, u, MOVE)
    _advance(world, u)


def _step_or_turn(world, u):
    """`FUN_00555c7e`: with a waypoint in the dynamic list start the step (`_start_step`); with an EMPTY list (the hop plan found no cell,
    or a follow driver skipped the plan while the facing differs from the target facing) the routine runs one tick of `FUN_005551ef`
    towards `mover+1` and nothing else: no step, no turn bookkeeping (`turning` / `turn_ticks` untouched).  At a centre with
    facing == target facing that is a no-op (docs/engine/simulation.md 7.2)."""
    if u.path:
        _start_step(world, u)
        return
    old = u.facing
    _turn_step(u)
    if u.facing != old:
        u.state = MOVE_STATE
        _set_action(world, u, TURN)
    elif not u.mover.turning:
        _set_action(world, u, IDLE)


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
    u.mode_attack = u.mode_cast = False
    u.mode_follow = False
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
    """Cells the other units stamp into the live layer as seen by mover `u` (CONFIRMED docs/engine/simulation.md 7.3, 7.4): the stamp
    slots of the cell records (`World.cells.stamp`, rec+0x2c ground / rec+0x30 flyers), whoever holds them; the unit's own are left out
    (it releases them before it plans).  The slots are filled and cleared by `FUN_0055be86` as the exe does it (step start, border
    crossing, step end, planner, removal: `engine/cellslots.py`), so a unit that lost a first-come race holds nothing and a cell can be free
    while the loser stands on it.  The stamp is 0x40 (ground classes) or 0x80 (flyers): only movers whose mask contains it are blocked.
    A unit with HP <= 0 keeps its stamps until it is removed (FUN_00510a70 -> FUN_00553891)."""
    seen = pas.MOVE_MASK.get(u.move_type, pas.MOVE_MASK[1])
    out = set()
    for air, bit in ((0, UNIT_STAMP_GROUND), (1, UNIT_STAMP_AIR)):
        if bit & seen:
            out.update((idx & 255, idx >> 8) for idx, h in world.slots.stamp[air].items() if h != u.id)
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
    world.slots.be86(u, 0, 2)                           # FUN_0054d76e dynamic mode 0x54dd04: the unit's own ring is released for the wave ...
    grid = path_grid(world, u.move_type).with_blocked(live_cells(world, u))
    res = plan_dynamic(grid, here, goal, size=unit_size(u), walker=u.move_type == 1,
                       follow=None if follow is None else (foot(u), foot(follow)))
    world.slots.be86(u, 0, 1)                           # ... and the own cell stamped again before the walk back (0x54e109)
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
    """The units `FUN_00551edb` returns for `cells`, one entry per cell, in order: the ground occupant slot (rec+4, ground classes 1, 2
    only: class 3 uses rec+8, which nothing reads) of each cell, dead units included.  A unit that only stamps a cell (entering it, or
    leaving it after the border), or that lost the first-come race for it, is no occupant; a sized unit appears once per footprint cell
    it holds."""
    out = []
    for c in cells:
        uid = world.slots.occupant(pack(c[0], c[1]))
        o = world.units.get(uid) if uid is not None else None
        if o is not None and o is not skip:
            out.append(o)
    return out


def _blocker(world, u, cell):
    """`FUN_00551edb(cell)`: the occupant of the cell record, or None."""
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


def restamp_displaced(world, u):
    """The tail of `FUN_0056d969` (0x56d9a7-0x56da01) and of the guard scan `FUN_0056a1fb` (0x56a592-0x56a5f0): a unit at a cell centre whose
    stamp cell (`mover+0x80`) is neither 0 nor its own cell stamps its own cell again (`FUN_00558b75` = `FUN_0055be86(unit, 0, 1)`), which
    releases the next-cell stamp a turning unit took."""
    m = u.mover
    if (u.sub_x, u.sub_y) == (CENTRE, CENTRE) and m.stamp_cell and m.stamp_cell != pack(u.x, u.y):
        world.slots.be86(u, 0, 1)


def cancel(u, world=None):
    """`FUN_0056dbfb` = `FUN_0056d969` + `brain+0x50 := 0` (R 3.4): the target facing becomes the facing (a turn in
    progress stops where it is), the state is 0.  A step in progress is NOT aborted (the Brain tick keeps running
    it) and a reservation is kept mid-step; at a centre the engine has no reservation to release (the live layer is
    derived from positions).  Plans, `dest`, `turning` and the dynamic list are untouched."""
    u.mover.target_facing = u.facing
    u.mover.follow = None                       # FUN_0056d969: mover+0x7c := 0
    u.ai_cast = False                           # FUN_0056d969 0x56da27: brain+0x60 := 0 (docs/engine/ai.md 12.7)
    u.state = IDLE_STATE
    u.stopped = False
    if world is not None:
        restamp_displaced(world, u)


def stop_unit(world, u):
    """`FUN_0056dbc6`: cancel, then order 0xc with the anchor on the own cell and Brain mode 0 (`FUN_0056dba1` ->
    `FUN_0056d52b`), and `brain+0x50 := 1`.  Used by the group pass at arrival (the only caller of the move
    group's handler, `FUN_00573198`)."""
    cancel(u, world)
    set_stand(world, u)
    u.stopped = True


def fail_stop(world, u):
    """`FUN_0056dc24` (the failure of an order 1, `0x56e1d9`): `FUN_0056d969` then `FUN_0056dba1` = cancel (which
    clears `brain+0x50`) and `FUN_0056d52b`.  Unlike `FUN_0056dbc6` it does NOT set `brain+0x50` (CONFIRMED
    asm 0x56dc24-0x56dc46, 0x56dba1-0x56dbc3): the group pass will restart the unit (unit-struct 8.1)."""
    cancel(u, world)
    set_stand(world, u)


def set_stand(world, u):
    """`FUN_0056d52b`: order 0xc (stand/guard), anchor = the own cell, mode 0."""
    cancel(u, world)
    u.mode_go = False
    u.mode_attack = u.mode_cast = u.mode_cell = False
    u.mode_follow = False
    u.order = STAND_ORDER
    u.anchor = (u.x, u.y)
    u.mover.waiting = u.mover.parked = False
    if not u.mover.step_ticks:
        _set_action(world, u, IDLE)


def _set_post(world, u, order, anchor):
    cancel(u, world)
    u.mode_go = False
    u.mode_attack = u.mode_cast = u.mode_cell = False
    u.mode_follow = False
    u.mode_look = False
    u.order = order
    u.anchor = anchor
    u.mover.waiting = u.mover.parked = False
    if not u.mover.step_ticks:
        _set_action(world, u, IDLE)


def set_guard(world, u):
    """`FUN_0056d4ba` (cmd 0x17 G, `FUN_00570aba`, the squad set-up): order 0xb, Brain mode 0, anchor = the cell being entered (`mover+6`)
    when the unit is between cells, else its own cell (docs/engine/click-to-move-research.md 5)."""
    centred = (u.sub_x, u.sub_y) == (CENTRE, CENTRE)
    step = u.mover.step_target
    _set_post(world, u, GUARD_ORDER, (u.x, u.y) if centred or step is None else tuple(step))


def set_still(world, u):
    """`FUN_0056d572` (cmd 0x12 L): order 0x17 (stand still), anchor = the own cell, Brain mode 0."""
    _set_post(world, u, STILL_ORDER, (u.x, u.y))


def set_move(world, u, x, y):
    """`FUN_0056d032` after the clamp: order 1, destination (x, y), `mover+0x90` (arrived) and the failure flag
    cleared, Brain mode 1.  The cancel comes first."""
    cancel(u, world)
    m = u.mover
    u.order = MOVE_ORDER
    u.mode_go = True
    u.mode_attack = u.mode_cast = u.mode_cell = False
    u.mode_follow = False
    u.anchor = None
    m.goal = (x, y)
    m.arrived = m.failed = False
    m.waiting = m.parked = False


def _tick_unit(world, u):
    """One creature tick (`FUN_0050f12c`): the Brain tick (`FUN_0056dca2`), then the failure event, then the state switch: state 3 runs the
    swing phases (`sim/combat.py`).  A unit with HP <= 0 is dying (`sim/death.py`): no Brain tick, no state switch.

    The failure event: `mover+0x98` ends an order 1 at once (`0x56e1b0` -> `FUN_0056dc24` = cancel + order `0xc`, `brain+0x50`
    stays 0), unlike arrival, which waits for the group pass.  Under any other order the event sets Brain mode 0 (`0x56e320`: the auto
    target scan `FUN_0056ed4e` finds no enemy; the scan and the computer players' mode 0xb are phase I, combat.md 9.3)."""
    effects.tick_unit(world, u)                         # step 2 of the creature tick: the effect list (docs/engine/effects.md 7)
    if u.hp <= 0:                                       # the HP <= 0 branch replaces the Brain tick and the state switch (combat.md 12.1)
        if death.dying_tick(world, u):
            death.remove_dead(world, u)
        return
    m = u.mover
    if world.ai_on:
        if ai.asleep(world, u):                         # 0x56dca2 pre-check (a): a sleeping squad's idle members do nothing (state 0x1b)
            u.state = ai.SLEEP_STATE
            return
        if u.state == ai.SLEEP_STATE:                   # 0x56dd0b: the Brain tick clears the state unless it is 2 or 0xf
            u.state = IDLE_STATE
    effects.stone_check(u)                              # 0x56dd24: Stone Curse -> brain order 4
    old_pos, old_face = (u.x, u.y, u.sub_x, u.sub_y), m.target_facing
    _tick_inner(world, u)
    if u.state == MOVE_STATE and m.target_facing != old_face and (u.x, u.y, u.sub_x, u.sub_y) == old_pos:
        u.step_end = world.tick + ((m.target_facing + 8) >> 4)  # FUN_0050ff2d message 0x6d (a turn): +0x138 = tick + dir16 (not a duration: combat.md 12.5)
    if m.failed:
        m.failed = False
        if u.order == MOVE_ORDER:
            fail_stop(world, u)
        else:
            u.mode_go = False
            u.mode_attack = u.mode_cast = u.mode_cell = False
            u.mode_follow = False
            if world.ai_on and u.order == ai.GUARD_ORDER:       # 0x56e320: mode 0 and the auto target scan FUN_0056ed4e
                ai.auto_scan(world, u)
    if u.state == ATTACK_STATE:
        combat.swing_tick(world, u)
    elif u.state in (spells.CAST_STATE, spells.CELL_STATE):
        spells.cast_tick(world, u)


def _tick_inner(world, u):
    m = u.mover
    if u.brain_order == effects.BRAIN_STONE:            # Brain order 4: state 0x1b while stoned (effects.md 7)
        effects.brain_stone(u)
        return
    if u.brain_order == combat.BRAIN_SWING:              # Brain order 1: the swing runs, no mode (FUN_0056dca2 order switch)
        combat.brain_swing(u)
        return
    if u.brain_order == spells.BRAIN_CAST:              # Brain order 2: a cast runs, no mode
        spells.brain_cast(u)
        return
    if m.step_ticks:                                    # a step is in progress (FUN_00555b38)
        u.state = MOVE_STATE
        _advance(world, u)
        if (u.sub_x, u.sub_y) == (CENTRE, CENTRE):
            _end_step(world, u)
            if m.goal is not None:
                u.path = []             # FUN_00555b38 clears the dynamic list (+0x1e4) at every step end
        return
    if u.mode_cast and (u.mode_attack or u.mode_go or u.mode_look):
        u.mode_cast = False                             # the exe has one mode byte: the last writer wins
    if u.mode_cell and (u.mode_attack or u.mode_go or u.mode_look or u.mode_cast):
        u.mode_cell = False
    if u.mode_attack:                                   # Brain mode 5 (FUN_0056eab5)
        combat.attack_mode(world, u)
        return
    if u.mode_follow:                                   # Brain mode 4 (FUN_0056ea52): approach brain+0x18 (follow.py)
        follow.approach_mode(world, u)
        return
    if u.mode_cast:                                     # Brain mode 8 (FUN_0056ebc0)
        spells.cast_mode(world, u)
        return
    if u.mode_cell:                                     # Brain mode 9 (FUN_0056ec3f)
        spells.cell_mode(world, u)
        return
    if u.mode_look:                                     # Brain mode 0xb (FUN_0056e5bc): the idle look-around of a computer-owned unit
        ai.look_around(world, u)
        return
    if not u.mode_go or m.parked:
        return
    go_tick(world, u)


def go_tick(world, u):
    """The body of the move driver at a cell centre (`FUN_0056e4ac` -> `FUN_00555411` with stop distance 0): the blocker wait, the plan,
    the step.  Brain mode 1 and the out-of-range branch of mode 9 (`spells.cell_mode`) run it."""
    m = u.mover
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
    else:                                               # the hop plan found nothing: FUN_00555c7e's empty-list turn tick
        u.state = IDLE_STATE
        _step_or_turn(world, u)


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
                ai.on_static_plan(world, u, res, tcell)         # the class-0x12 clause stamps brain+0x16 (docs/engine/ai.md 3)
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


from . import ai, combat, death, effects, follow, spells    # noqa: E402  the fight code imports this module: bound here, used at call time (circular on purpose)
