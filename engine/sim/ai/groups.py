"""groups: part of the monster AI (docs/engine/ai.md); see the package docstring in __init__."""

from engine.world import AiGroup
from .. import movement as mv, orders, triggers
from .. import combat as cb
from ..pathfinding import chebyshev, footprint_gap, unit_size
from .actions import engage, idle
from .brain import go
from .perception import NO_TARGET, WANDER_DX, WANDER_DY, _hostiles_on, _visible, centroid_stats, unword, word
from .reaction import guard_scan, post_step
from .targeting import score, score_stand


GROUP_ORDER = 0x12                  # group order of the computer players' squads (FUN_00570aba)


PASS_ORDERS = (1, 2, 5, 0x11, 0x12, 0x13, 0xFF)    # the group orders `ai.run_group` handles for a command group (0, 3, 4 have their own branches)


# group orders (record+0x20, dispatch FUN_005700f3; docs/engine/ai.md 14).  0 = every member runs its own order executor, 4 = move (orders.py)
G_NONE, G_GUARD, G_HOLD, G_STAND, G_MOVE, G_SWARM, G_WANDER, G_COMPUTER, G_STILL, G_EMPTY = 0, 1, 2, 3, 4, 5, 0x11, 0x12, 0x13, 0xFF


WANDER_STEP = 20                    # FUN_00572ec4: the new destination is 20 cells away in one of the 8 directions


WANDER_NEAR, WANDER_LIMIT = 10, 0x32    # retarget when every member is within 9 cells of the destination, or after 51 passes


GUARD_ORDER = 0xB                   # unit order the squad set-up gives the members (FUN_0056d4ba)


MIN_GUARD_RANGE = 10                # registry Scanning\MinimalGuardRange (absent in the install: the default 10)


DEFAULT_RADIUS = 0x14               # pool radius of a squad whose reach is below MIN_GUARD_RANGE


POOL_GROW = 4                       # first pass: radius := base + 4 + rand(-1..1)


STAMP_NEAR, STAMP_FAR = 10, 30      # block counters: |stamp - block| thresholds of the handler


HIT_WINDOW = 10                     # ticks: a member hit this recently runs to `hit_cell` when it has no target


SLEEP_STATE = 0x1B                  # unit state of a member of a sleeping squad (FUN_0056dca2, docs/engine/ai.md 15)


WAKE_BLOCKS = 2                     # a human unit wakes the squads with a member within +-2 blocks of 8 cells (FUN_0055aca2 / 0x55b406)


# --- set-up ---------------------------------------------------------------------------------------------------------------

def enable(world):
    """Build the squads of the computer players and run `FUN_00570aba(group, 0)` on each (map load, `FUN_00562745`)."""
    world.ai_on = True
    world.ai_groups.clear()
    _stand_squads(world)
    for u in world.units.values():
        pl = world.players.get(u.owner)
        if pl is None or pl.human or not u.known:
            continue
        key = (u.owner, u.squad)
        g = world.ai_groups.get(key)
        if g is None:
            g = world.ai_groups[key] = AiGroup(key)
        g.members.append(u.id)
    for g in world.ai_groups.values():
        init_group(world, g)
    wake(world)                                         # 0x4f212b: the awake map is built at map load


def _stand_squads(world):
    """`FUN_00562745` for the human players (map load, new game): every squad of a human player becomes a command group under group order 3
    (`FUN_00570f2b` -> `FUN_00570b8b`: members order `0xc` on their own cell), so that the stand-ground pass (`stand_pass`) runs for them.
    Units that already belong to a command group (a test or a save that issued commands) are left alone."""
    squads = {}
    for u in world.units.values():
        pl = world.players.get(u.owner)
        if pl is not None and pl.human and u.known and not u.order_group:
            squads.setdefault((u.owner, u.squad), []).append(u)
    for (owner, _), mem in squads.items():
        g = orders._new_group(world, owner)
        for u in mem:
            orders._join(world, g, u)
        orders.stop_group(world, g)


def init_group(world, g):
    """`FUN_00570aba` + `FUN_0057026e` + `FUN_0056f850`: members stand (order 0xb, anchor = own cell), centroid of the 16-bit positions,
    radius = reach, at least the default."""
    mem = [world.units[i] for i in g.members]
    for u in mem:
        mv.cancel(u, world)
        u.order = GUARD_ORDER
        u.anchor = (u.x, u.y)
        u.set_mode(cell=u.mode_cell)                    # mode_cell is left as it was
        u.mover.waiting = u.mover.parked = False
    g.order = GROUP_ORDER
    record_stats(world, g, mem)
    if g.radius < MIN_GUARD_RANGE:
        g.radius = g.base = DEFAULT_RADIUS


def record_stats(world, g, mem):
    """`FUN_0057026e` = `FUN_0056f850` + `+0x2d = +0x38 := +0x2c`: centroid of the 16-bit positions, widest member distance, reach (distance +
    scan range); the pool radius starts as the reach."""
    centroid_stats(world, g, mem, fine=True)
    g.radius = g.base = g.reach


# --- the pass (FUN_0056fe4d -> FUN_00570087 -> FUN_005728fa) ---------------------------------------------------------------

def wake(world):
    """`FUN_0055b5f1` (map load `0x4f212b` and every group pass `0x56fe9c`): which computer squads are awake (GroupAI record `+0x45`).  A
    squad is awake when one of its members stands within two 8-cell blocks (a 5 x 5 block neighbourhood, 16..23 cells) of a unit of a
    human player (`FUN_0055aca2` marks, `FUN_0055b406` reads), or is wounded (`hp < max hp`, `FUN_0055aca2` computer branch), or has
    `keep_awake` (record `+0x48`).  Everything else sleeps until the next pass (docs/engine/ai.md 15)."""
    if not world.ai_sleep:
        for g in world.ai_groups.values():
            g.awake = True
        return
    marks = set()
    for u in world.units.values():
        pl = world.players.get(u.owner)
        if u.hp > 0 and pl is not None and pl.human:
            bx, by = u.x >> 3, u.y >> 3
            marks.update((bx + i, by + j) for i in range(-WAKE_BLOCKS, WAKE_BLOCKS + 1) for j in range(-WAKE_BLOCKS, WAKE_BLOCKS + 1))
    for g in world.ai_groups.values():
        g.awake = g.keep_awake or any(
            (u.x >> 3, u.y >> 3) in marks or u.hp < u.hp_max for u in (world.units.get(i) for i in g.members) if u is not None)


def asleep(world, u):
    """`FUN_0056dca2` pre-check (a): `server+0xbbe8 == 0` and the squad's record `+0x45 == 0` and Brain order 0 (no swing, no step in progress)."""
    g = world.ai_groups.get((u.owner, u.squad)) if world.ai_sleep else None
    return g is not None and not g.awake and u.brain_order == 0 and not u.mover.step_ticks


def ai_system(world, commands):
    """Run the squads' handler at `tick & 15 == 6`, before the command drain; players in id order, squads in creation order."""
    if not world.ai_on or (world.tick & 15) != 6:
        return
    wake(world)
    if world.script is not None:                        # FUN_0057485b: the scenario triggers, after the awake map, before the handlers
        triggers.run_pass(world)
    for g in sorted(world.ai_groups.values(), key=lambda g: g.owner):      # stable: creation order inside an owner
        g.members = [i for i in g.members if i in world.units]
        if not g.members:
            g.order = G_EMPTY
            continue
        if not g.awake:                                 # FUN_00570087: a sleeping squad's pass is skipped (handler and post step)
            continue
        run_group(world, g)


def run_group(world, g):
    """`FUN_005700f3` for one non-empty group (a squad `AiGroup` or a command group `OrderGroup`): the handler of its group order, then the post
    step `FUN_00573713` on every member (whatever the order).  Called by `ai_system` and by `orders.group_pass`."""
    block = (world.tick + 1) >> 4                       # server+0, the 16-tick block counter (Simulation.block)
    run = GROUP_PASSES.get(g.order)
    if run is not None:
        run(world, g, block)
    if world.ai_on:
        for i in list(g.members):
            if i in world.units:
                post_step(world, g, world.units[i])


def _grow(world, g):
    """The pass counter of the guard handlers (`57275f`, `5728fa`): the first pass sets the radius to the base + 4 + rand(-1..1)."""
    if not g.seen:
        g.radius = g.base + POOL_GROW + world.rng.rand(2) - 1       # FUN_005726f7: FUN_0057aff0(-1, 1)
        g.passes = 0
    else:
        g.passes += 1
    g.seen = 1


def _on_post(m):
    return m.anchor is not None and (m.x, m.y) == tuple(m.anchor) and (m.sub_x, m.sub_y) == (mv.CENTRE, mv.CENTRE)


def handler(world, g, block):
    """`FUN_005728fa`."""
    mem = centroid_stats(world, g)
    pool = _pool(world, g, mem)
    _assign_targets(world, mem, pool)
    _grow(world, g)
    for m in mem:
        b = m.ai
        stamp_gap = abs(b.stamp - block)
        damaged = m.hp != m.hp_max
        if damaged and stamp_gap < STAMP_FAR:
            go(world, m, b.hit_cell)
        elif stamp_gap < STAMP_NEAR:
            go(world, m, b.hit_cell)
        elif b.target is not None:
            t = world.units.get(b.target)
            if t is not None:
                engage(world, m, t)
        elif damaged and abs(b.hit_tick - world.tick) < HIT_WINDOW:
            go(world, m, b.hit_cell)
        elif _on_post(m):
            idle(world, m)
        else:
            go(world, m, word(*m.anchor) if m.anchor is not None else 0)


def _idle_post(world, m):
    idle(world, m)


def _return_to_post(world, m):
    """The no-target clause of the guard handlers: on the post (`_on_post`) `idle`, else `go(anchor)`."""
    if _on_post(m):
        idle(world, m)
    else:
        go(world, m, word(*m.anchor) if m.anchor is not None else 0)


def _return_to(dest):
    """The no-target clause of the hold pass: on `dest` (cell equal, at a centre) `idle`, else `go(dest)`."""
    def post(world, m):
        if (m.x, m.y) == dest and (m.sub_x, m.sub_y) == (mv.CENTRE, mv.CENTRE):
            idle(world, m)
        else:
            go(world, m, word(*dest))
    return post


def _act(world, m, post):
    """The per-member clause of the handlers `57275f`, `572d57`, `572e1e`: a target -> `FUN_0056acc8`; none -> `post(world, m)`."""
    t = world.units.get(m.ai.target) if m.ai.target is not None else None
    if t is not None:
        engage(world, m, t)
    elif post is not None:
        post(world, m)


def guard_pass(world, g):
    """`FUN_0057275f` (group order 1, the G key and the scripted guard): the machinery of `handler` without the hit / stamp branch table:
    centroid stats, pool, radius filter, assign, first-pass radius growth; act: no target -> on the post (`brain+0`, at a centre) `idle`, else `go(anchor)`."""
    mem = centroid_stats(world, g)
    if not mem:
        return
    _assign_targets(world, mem, _pool(world, g, mem))
    _grow(world, g)
    for m in mem:
        _act(world, m, _return_to_post)


def _live(world, g):
    return [world.units[i] for i in g.members if i in world.units]


def _pool_all(world, mem):
    """`FUN_00571c4d` over the members, no radius filter (the pools of the orders 2, 5, 0x11): empty when the AI is off."""
    if not world.ai_on:
        return []
    return _hostiles_on(world, mem[0].owner, _visible(world, mem), mem)


def hold_pass(world, g):
    """`FUN_00572d57(group, dest)` (group order 2, go and hold): pool and assign without a radius; act: no target -> on `dest` (cell word equal, at
    a centre) `idle`, else `go(dest)`."""
    mem = _live(world, g)
    if not mem:
        return
    _assign_targets(world, mem, _pool_all(world, mem))
    post = _return_to(tuple(g.target))
    for m in mem:
        _act(world, m, post)


def swarm_pass(world, g):
    """`FUN_00572e1e(group, dest)` (group order 5, swarm): the pool; empty -> `FUN_00573198` (the move group pass towards the members' own
    destinations, `brain+0xa`); else assign (no radius), act: no target -> `FUN_0056afac(m, 1)` = `idle`, target -> `FUN_0056acc8`."""
    mem = _live(world, g)
    if not mem:
        return
    pool = _pool_all(world, mem)
    if not pool:
        orders._pass_move(world, g)
        return
    _assign_targets(world, mem, pool)
    for m in mem:
        _act(world, m, _idle_post)


def wander_pass(world, g):
    """`FUN_00572ec4` (group order 0x11): `d` = the widest Chebyshev distance of a member from the destination `+0x0a`; when `d < 10` or the counter
    `+0x15` is above 0x32 the destination becomes the cell 20 away in a random one of the 8 directions (`rand(0..7)`, redrawn until it lies in
    [8, size - 9] on both axes) and the counter restarts; then the swarm pass, counter + 1."""
    mem = _live(world, g)
    d = max((chebyshev((m.x, m.y), g.target) for m in mem), default=0)
    if d < WANDER_NEAR or g.counter > WANDER_LIMIT:
        for _ in range(1000):                           # the exe loops until the cell is inside (a map under 40 cells could hang it)
            k = world.rng.rand(7)                       # FUN_0057aff0(0, 7): inclusive
            x, y = g.target[0] + WANDER_DX[k] * WANDER_STEP, g.target[1] + WANDER_DY[k] * WANDER_STEP
            if 8 <= x <= world.width - 9 and 8 <= y <= world.height - 9:
                g.target, g.counter = (x, y), 0
                break
    swarm_pass(world, g)
    g.counter = (g.counter + 1) & 0xFF


def _pool(world, g, mem):
    """`FUN_00571c4d` + `FUN_00567e92`: the hostile living units on the squad's visible cells within `radius` of the centroid."""
    owner = g.owner
    cells = _visible(world, mem)
    cen = unword(g.centre)
    return [u for u in _hostiles_on(world, owner, cells, mem) if chebyshev((u.x, u.y), cen) <= g.radius]


def _assign_targets(world, mem, pool, scorer=score):
    """`FUN_0057240b` (`scorer` = `score_stand` for `FUN_005725a8`): each member's best-scoring pool unit (first wins a tie), or none."""
    for m in mem:
        best, best_s = None, NO_TARGET
        for c in pool:
            s = scorer(world, m, c)
            if s < best_s:
                best, best_s = c, s
        m.ai.target = best.id if best is not None else None


def stand_pass(world, g):
    """`FUN_0057309d`, the group pass of group order 3 (stand ground; `g` is a command group, `orders.OrderGroup`).  Every 16 ticks: the pool of
    hostiles in the members' sight (`FUN_00571c4d`, no radius filter), each member's best `score_stand` candidate (`FUN_005725a8`), then per
    member in list order: no target -> `FUN_0056afd9` (human: brain mode 0), else `FUN_0056acc8` (brain mode 5 on the target).  There is no
    guard scan: the reach test is inside the score (adjacent for a melee unit, inside the range for a ranged one)."""
    mem = [world.units[i] for i in g.members if i in world.units]
    if not mem:
        return
    pool = _hostiles_on(world, mem[0].owner, _visible(world, mem))
    _assign_targets(world, mem, pool, score_stand)
    for m in mem:
        t = world.units.get(m.ai.target) if m.ai.target is not None else None
        if t is None:
            m.ai.target = None
            idle(world, m)
        else:
            engage(world, m, t)


def group_order(world, u):
    """The group order (record `+0x20`) of the unit's group: its command group, else its squad; None when it has none."""
    g = world.groups.get(u.order_group) if u.order_group else None
    if g is None:
        g = world.ai_groups.get((u.owner, u.squad))
        if g is not None and u.id not in g.members:
            g = None
    return None if g is None else g.order


def pool_driven(world, u):
    """True when the unit's group order picks its targets from the pool (guard 1, hold 2, swarm 5, wander 0x11, computer guard 0x12): its brain
    mode 5 is the group's, not an attack order of its own."""
    return group_order(world, u) in (G_GUARD, G_HOLD, G_SWARM, G_WANDER, G_COMPUTER)


def find_squad(world, owner, squad):
    """The group that holds the units of `(owner, squad)`: the `AiGroup` of a computer player, else the command group (`OrderGroup`) of the first
    such unit (a human's squad, `_stand_squads`); None when there is none."""
    g = world.ai_groups.get((owner, squad))
    if g is not None:
        return g
    for u in world.units.values():
        if u.owner == owner and u.squad == squad and u.order_group in world.groups:
            return world.groups[u.order_group]
    return None


def set_group_order(world, group, order, target=None):
    """The scripted group orders (the Scenario instant `FUN_00577cee`, sub-commands 1-5, 17, 18) on `group` (an `AiGroup` or an `OrderGroup`):
    1 guard (`target` = radius byte, 0 = default), 2 go and hold (`FUN_005708bc`, `target` = (x, y)), 3 stand ground, 4 move, 5 swarm
    (`FUN_0057063e`, `target` = (x, y)), 0x11 wander (`FUN_005708ff`: the destination starts on the first member's cell), 0x12 computer guard
    (`FUN_00570aba`, `target` = radius byte), 0x13 stand still.  Each cancels the members first (`FUN_00570e83`) like the exe."""
    group.members = [i for i in group.members if i in world.units]      # a squad keeps the ids of its dead
    setter = GROUP_SETTERS.get(order)
    if setter is None:
        raise ValueError("group order %#x has no scripted setter" % order)
    setter(world, group, target)


def _still_pass(world, g, block):
    for i in list(g.members):
        idle(world, world.units[i])                 # FUN_0057311c: FUN_0056afd9 for every member


def _empty_pass(world, g, block):
    for i in list(g.members):
        guard_scan(world, world.units[i])           # FUN_00573159: FUN_0056afac(m, 0)


# group order -> the pass `run_group` runs (handlers take `(world, g, block)`)
GROUP_PASSES = {
    G_COMPUTER: handler,
    G_GUARD: lambda world, g, block: guard_pass(world, g),
    G_HOLD: lambda world, g, block: hold_pass(world, g),
    G_STAND: lambda world, g, block: stand_pass(world, g),
    G_MOVE: lambda world, g, block: orders._pass_move(world, g),
    G_SWARM: lambda world, g, block: swarm_pass(world, g),
    G_WANDER: lambda world, g, block: wander_pass(world, g),
    G_STILL: _still_pass,
    G_EMPTY: _empty_pass,
    G_NONE: lambda world, g, block: orders._pass_orders(world, g),
}

# group order -> the scripted setter of `set_group_order` (`(world, group, target)`)
GROUP_SETTERS = {
    G_GUARD: lambda world, group, target: orders.guard_group(world, group, int(target or 0)),
    G_HOLD: lambda world, group, target: orders.hold_group(world, group, *target),
    G_STAND: lambda world, group, target: orders.stop_group(world, group),
    G_MOVE: lambda world, group, target: orders.move_group(world, group, *target),
    G_SWARM: lambda world, group, target: orders.move_group(world, group, *target, swarm=True),
    G_WANDER: lambda world, group, target: orders.wander_group(world, group),
    G_COMPUTER: lambda world, group, target: orders.guard_group(world, group, int(target or 0), computer=True),
    G_STILL: lambda world, group, target: orders.still_group(world, group),
}


def on_static_plan(world, u, res, target):
    """The class-0x12 clause of the static plan request (`0x54e245`, simulation 7.4): a unit of a squad in attack mode whose plan ended
    on a fallback cell still farther than its range from the target stamps the failure (`brain+0x16 := block counter`)."""
    if not (world.ai_on and u.mode_attack and group_order(world, u) == GROUP_ORDER):
        return
    here = res.cells[-1] if res.cells else (0, 0)
    if footprint_gap(here, target, unit_size(u)) > cb.attack_range(world, u):
        u.ai.stamp = ((world.tick + 1) >> 4) & 0xFFFF
