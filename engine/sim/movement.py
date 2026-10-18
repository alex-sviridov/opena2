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

from .commands import Command
from .pathfinding import DEFAULT_CONFIG, PathGrid, plan_dynamic, plan_static, chebyshev
from allods2.formats import passability as pas

# Direction tables (path-finder object, CONFIRMED 0x553e4e..0x553f2f): 0 N, 1 NE, 2 E ... 7 NW.
DIR_DX = (0, 1, 1, 1, 0, -1, -1, -1)
DIR_DY = (-1, -1, 0, 1, 1, 1, 0, -1)
DIAGONAL = struct.unpack("<d", struct.pack("<Q", 0x3FE69FBE76C8B439))[0]    # double at 0x5d1aa8, 0.70699...
CENTRE = 128
MIN_STEP, MAX_STEP = 1, 63
SNAP_TURN = 0x20                # a turn of at most 45 degrees snaps (FUN_00556454)

IDLE_STATE, MOVE_STATE = 0, 1   # unit.state (+0x54)
NO_ORDER, MOVE_ORDER = 0, 1     # unit.order (+0x50)
STATIC_PLAN_FORCED = 0xFF       # mover.consumed value that forces a static re-plan (brain wrapper 0x56e4b0)
IDLE, MOVE, TURN = "idle", "move", "turn"       # unit.action (the client's actions 0, 1, 5)


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
    """Order 1: walk `unit_id` to cell (x, y), planning the way as the exe does (docs/engine/simulation.md
    section 7).  The click mapping (H3) issues these.  Rejected: unknown or dead unit, cell outside the map."""
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
    base = unit_speed(u)
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
        _set_action(world, u, TURN)
        _turn_toward(u, face)
        return
    u.path.pop(0)
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
    return True


def unit_size(u):
    """Footprint side in cells: token size (+0x49, vtable +0x1c `0x542360`, CONFIRMED)."""
    return max(1, int(getattr(u.stats, "token_size", 1) or 1)) if u.stats is not None else 1


def path_grid(world, move_type):
    """Static PathGrid for a mover class (block layer masked with the mover byte, terrain costs), cached
    per block revision."""
    cache = world.__dict__.setdefault("_path_grids", {})
    key = (move_type, world.block_rev, id(world.cost))
    g = cache.get(key)
    if g is None:
        cache.clear()
        blocked = (world.block & pas.MOVE_MASK[move_type]) != 0
        g = cache[key] = PathGrid.from_arrays(blocked, world.cost if move_type == 1 else None)
    return g


def live_cells(world, u):
    """Cells the other living units hold (footprint at their cell, and the cell being entered): the
    dynamic stamps over the static layer.  INFERRED, docs/engine/simulation.md 7.3."""
    out = set()
    for o in world.units.values():
        if o is u or o.hp <= 0:
            continue
        n = unit_size(o)
        for j in range(n):
            for i in range(n):
                out.add((o.x + i, o.y + j))
        if o.mover.step_target:
            tx, ty = o.mover.step_target
            for j in range(n):
                for i in range(n):
                    out.add((tx + i, ty + j))
    return out


def _is_human(world, u):
    p = world.players.get(u.owner)
    return bool(p and p.human)


def apply_move_to(world, cmd):
    u = world.units.get(cmd.unit_id)
    if u is None or u.hp <= 0 or not _in_map(world, (cmd.x, cmd.y)):
        return False
    u.order, u.state = MOVE_ORDER, MOVE_STATE
    u.mover.goal = (cmd.x, cmd.y)
    return True


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


def _hop_plan(world, u):
    """FUN_00555dc2: plan a short hop towards a point of the static plan over the live layer."""
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
    res = plan_dynamic(grid, here, goal, size=unit_size(u), walker=u.move_type == 1)
    u.path = list(res.cells)
    m.last_hop = res
    if not u.path and final:
        m.failed = True
    if n and d <= cfg.dynamic_by_static_lookup:
        m.static_path.pop(0)


def _drive(world, u):
    """The move driver at a cell centre (FUN_00555411 steps 2-4, wrapper 0x56e4b0).  Returns False when
    the order ended."""
    m, cfg, here = u.mover, DEFAULT_CONFIG, (u.x, u.y)
    if m.dest != m.goal:                                # wrapper: target changed -> force a static re-plan
        m.consumed = STATIC_PLAN_FORCED
    if here == m.goal:
        return False
    m.since_hop = min(255, m.since_hop + 1)
    if m.dest != m.goal or m.consumed > cfg.static_refresh_rate:
        _static_plan(world, u)
    if here == m.tail:
        m.arrived = True
        return False
    if not u.path or m.since_hop > cfg.dynamic_refresh_rate:
        _hop_plan(world, u)
        m.consumed = (m.consumed + 1) & 255
        m.since_hop = 0
    return True


def _stop(world, u):
    m = u.mover
    u.order, u.state = NO_ORDER, IDLE_STATE
    m.target_facing = u.facing
    m.goal = m.dest = None          # DECISION: a finished order forgets its plan (the exe keeps +0x74; open)
    m.static_path = []
    _set_action(world, u, IDLE)


def _tick_unit(world, u):
    m = u.mover
    if m.step_ticks:                                    # a step is in progress (FUN_00555b38)
        _advance(world, u)
        if (u.sub_x, u.sub_y) == (CENTRE, CENTRE):
            _end_step(u)
            if m.goal is not None:
                u.path = []             # FUN_00555b38 clears the dynamic list (+0x1e4) at every step end
        return
    if u.order != MOVE_ORDER:
        return
    if m.goal is not None and not _drive(world, u):
        _stop(world, u)
        return
    if u.path:
        _start_step(world, u)
    else:                                               # arrived (mover+0x90) -> auto stop
        u.order, u.state = NO_ORDER, IDLE_STATE
        m.target_facing = u.facing
        _set_action(world, u, IDLE)


def movement_system(world, commands):
    """Apply the tick's movement commands, then update every unit in list order (the exe:
    FUN_004f84c6 drains the commands, FUN_004f04cf walks the creature list)."""
    for cmd in commands:
        if isinstance(cmd, FollowPath):
            apply_follow_path(world, cmd)
        elif isinstance(cmd, MoveTo):
            apply_move_to(world, cmd)
    for u in list(world.units.values()):
        _tick_unit(world, u)
