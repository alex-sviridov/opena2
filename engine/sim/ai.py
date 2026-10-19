"""Monster AI: the squad group handler `FUN_005728fa` and what it calls (docs/engine/ai.md; routine addresses in the comments).

Layer 4: reads and writes `engine.world` only.  The AI thinks inside the group pass (`tick & 15 == 6`, before the command drain) and
acts through the commands the player uses, `MoveUnits` / `AttackUnit` / `Stop` with `ai=True` (the brain-level executors at the end of
this file), so every action lands in the same log (`Simulation.log`).  State: `Unit.ai` (Brain fields), `World.ai_groups` (squads).
"""

import math
import struct

from engine.world import AiGroup, AiState

from . import combat as cb
from . import movement as mv
from . import spells
from .commands import AttackUnit, CastSpell, MoveUnits, Stop
from .pathfinding import chebyshev, follow_distance, foot, unit_size

GROUP_ORDER = 0x12                  # group order of the computer players' squads (FUN_00570aba)
PASS_ORDERS = (1, 2, 5, 0x11, 0x12, 0x13, 0xFF)    # the group orders `ai.run_group` handles for a command group (0, 3, 4 have their own branches)
# group orders (record+0x20, dispatch FUN_005700f3; docs/engine/ai.md 14).  0 = every member runs its own order executor, 4 = move (orders.py)
G_NONE, G_GUARD, G_HOLD, G_STAND, G_MOVE, G_SWARM, G_WANDER, G_COMPUTER, G_STILL, G_EMPTY = 0, 1, 2, 3, 4, 5, 0x11, 0x12, 0x13, 0xFF
WANDER_STEP = 20                    # FUN_00572ec4: the new destination is 20 cells away in one of the 8 directions
WANDER_NEAR, WANDER_LIMIT = 10, 0x32    # retarget when every member is within 9 cells of the destination, or after 51 passes
WANDER_DX = (0, 1, 1, 1, 0, -1, -1, -1)     # pf+0x58e88 / pf+0x58e90: the 8 directions, 0 = up, clockwise (0x553e4e..0x553eeb)
WANDER_DY = (-1, -1, 0, 1, 1, 1, 0, -1)
GUARD_ORDER = 0xB                   # unit order the squad set-up gives the members (FUN_0056d4ba)
MIN_GUARD_RANGE = 10                # registry Scanning\MinimalGuardRange (absent in the install: the default 10)
DEFAULT_RADIUS = 0x14               # pool radius of a squad whose reach is below MIN_GUARD_RANGE
SCAN_SHIFT = 7                      # registry Scanning\ScanShift (the install's value; default 7)
POOL_GROW = 4                       # first pass: radius := base + 4 + rand(-1..1)
STAMP_NEAR, STAMP_FAR = 10, 30      # block counters: |stamp - block| thresholds of the handler
HIT_WINDOW = 10                     # ticks: a member hit this recently runs to `hit_cell` when it has no target
RUN_AWAY = 10.0                     # cells beyond the victim on the ray attacker -> victim (FUN_0056e6b8)
FLEE_CELLS = 3                      # FUN_00558b92 distance of the wimpy / withdraw step
WIMPY_RADIUS, WITHDRAW_RADIUS = 10, 2
MARK_TURNS = 20                     # the attacker's cell stays revealed while mark_age <= 20
NO_TARGET = 0xFFFFFF
SLEEP_STATE = 0x1B                  # unit state of a member of a sleeping squad (FUN_0056dca2, docs/engine/ai.md 15)
WAKE_BLOCKS = 2                     # a human unit wakes the squads with a member within +-2 blocks of 8 cells (FUN_0055aca2 / 0x55b406)
# FUN_005711ea preference table (server+0xa54, built at 0x56827a..0x568310), index attacker class * 4 + candidate class
PREFERENCE = (2, 1, 2, 4, 4, 2, 1, 0, 2, 1, 4, 0, 2, 1, 2, 4)


# --- cell words -----------------------------------------------------------------------------------------------------------

def word(x, y):
    """The exe's packed cell `y << 8 | x`."""
    return ((y & 0xFF) << 8) | (x & 0xFF)


def unword(w):
    return w & 0xFF, (w >> 8) & 0xFF


def pos16(u):
    """`FUN_0054ff5b/7c`: the 16-bit position `cell * 256 + sub`."""
    return (u.x << 8) + u.sub_x, (u.y << 8) + u.sub_y


# --- sight flood (FUN_00552c28 + FUN_00552af8, tables FUN_00552244 / FUN_00552334) -------------------------------------------

def _build_tables():
    cost, par = {}, {}
    for i in range(-20, 21):
        for j in range(-20, 21):
            a, b = abs(i), abs(j)
            m = max(a, b)
            cost[i, j] = int(math.sqrt(a * a + b * b) * float(1 << SCAN_SHIFT) / m) if m else 0
            if (a, b) == (1, 0):
                sx, sy = 1, 0
            elif b < (a >> 1):
                sx, sy = 1, 0
            elif a * 2 < b:
                sx, sy = 0, 1
            else:
                sx, sy = 1, 1
            par[i, j] = ((-sx if i > 0 else sx) if i else 0, (-sy if j > 0 else sy) if j else 0)
    return cost, par


_COST, _PAR = _build_tables()
_SIGHT_CACHE_LIMIT = 8192


def sight(world, x0, y0, scan):
    """Cells the unit at (x0, y0) with scan range `scan` (`u+0xa5`) sees: a flood over rings 1..19 where each cell's light is its parent's
    minus the step cost minus the height difference to the observer (the heights are signed bytes), visible when positive."""
    key = (x0, y0, scan)
    got = world._sight.get(key)
    if got is not None:
        return got
    heights = world.heights
    h0 = int(heights[y0, x0])
    hi_x, hi_y = world.width - 9, world.height - 9
    acc = {(0, 0): (scan << SCAN_SHIFT) + (1 << (SCAN_SHIFT - 1))}
    seen = {(x0, y0)}
    for k in range(1, 20):
        dark = True
        for j in range(-k, k + 1):
            for i2, j2 in ((j, -k), (j, k), (-k, j), (k, -j)):
                wx, wy = x0 + i2, y0 + j2
                if 8 <= wx <= hi_x and 8 <= wy <= hi_y:
                    px, py = _PAR[i2, j2]
                    light = acc.get((i2 + px, j2 + py), 0) - (_COST[i2, j2] + int(heights[wy, wx]) - h0)
                    acc[i2, j2] = light
                    if light > 0:
                        seen.add((wx, wy))
                        dark = False
        if dark:
            break
    out = frozenset(seen)
    if len(world._sight) >= _SIGHT_CACHE_LIMIT:
        world._sight.clear()
    world._sight[key] = out
    return out


# --- the pool and the target score ----------------------------------------------------------------------------------------

def at_war(world, owner, other):
    """`FUN_0057994d`: bit 0 of the owner's relation word towards `other` (matrix server+0xa8bc)."""
    pl = world.players.get(owner)
    return pl is not None and 0 < other <= len(pl.relations) and bool(pl.relations[other - 1] & 1)


def _scan_range(u):
    return int(u.stats.get("scan_range", 0) or 0) if u.stats is not None else 0


def _visible(world, observers):
    """`FUN_00571c4d` steps 1-2: the union of the observers' sight, plus the attacker cells their hit marks reveal (the mark ages)."""
    vis = set()
    for m in observers:
        vis |= sight(world, m.x, m.y, _scan_range(m))
        pl = world.players.get(m.owner)
        if pl is not None and not pl.human and m.ai.mark_cell:
            vis.add(unword(m.ai.mark_cell))
            m.ai.mark_age += 1
            if m.ai.mark_age > MARK_TURNS:
                m.ai.mark_cell = 0
    return vis


def reach_gap(a, b):
    """`FUN_00556dcd`: the gap level between two objects, `(max over x, y of max(0, |centre distance| - (size_a + size_b) * 128) >> 8) + 1`
    (positions in 1/256 cell, the centre of a size-n footprint is `pos + (n - 1) * 128`): 1 = touching or overlapping."""
    sa, sb = unit_size(a), unit_size(b)
    (ax, ay), (bx, by) = pos16(a), pos16(b)
    gx = max(0, abs((ax + (sa - 1) * 128) - (bx + (sb - 1) * 128)) - (sa + sb) * 128)
    gy = max(0, abs((ay + (sa - 1) * 128) - (by + (sb - 1) * 128)) - (sa + sb) * 128)
    return (max(gx, gy) >> 8) + 1


def see_invisible(u):
    """brain+0x71, data.bin p36 (`see_invisible`): -1 or absent (humans) keeps the constructor default 1."""
    v = u.stats.get("see_invisible") if u.stats is not None else None
    return 1 if v is None or v < 0 else int(v)


def _detected(hidden, detectors):
    """`FUN_00567a16` hidden clause: a unit with flag `+0x144 & 0x1000` is kept only if some member of the first member's group has
    `reach_gap(hidden, member) <= member.see_invisible` (default 1: only touching units see it)."""
    return any(reach_gap(hidden, d) <= see_invisible(d) for d in detectors)


def _hostiles_on(world, owner, cells, detectors=()):
    """The units of cells, creation order, that `owner` is at war with (`FUN_00567a16` + `FUN_00567ddf`; a hidden unit (`Unit.hidden`) only
    when `_detected` by `detectors`): the living ones, or, when there is none, the dying ones (HP < 1, not yet removed)."""
    ids = set()
    for c in cells:
        ids |= world.units_at(*c)
    out = [world.units[i] for i in ids]
    out = [u for u in out if at_war(world, owner, u.owner) and (not u.hidden or _detected(u, detectors))]
    out.sort(key=lambda u: u.seq)
    living = [u for u in out if u.hp > 0]
    # FUN_00567ddf moves the HP < 1 units into the list server+0xa88; the callers (FUN_00571c4d, FUN_00569fd4, FUN_0056ed4e ...) put them back
    # when no living unit is left, so a dying body that is still in the world stays a target of an empty pool (A§4 step 6).
    return living or out


def class_of(u):
    return cb.move_class(u)


def attack_range(world, u):
    return cb.combat_stats(world, u).range


def score(world, me, cand):
    """`FUN_005711ea(me, cand)`: distance * 256 + facing difference, adjusted by the preference table; 0xffffff = not a target."""
    d = chebyshev((cand.x, cand.y), (me.x, me.y))
    cls = class_of(cand)
    if cls == 1 and attack_range(world, cand) > 1:
        cls = 0
    my_range = attack_range(world, me)
    if my_range > 1:
        pref = PREFERENCE[cls]
        d = d - my_range + 1 if d > my_range else 1
    else:
        pref = PREFERENCE[class_of(me) * 4 + cls]
    ang = mv._fold(me.facing, cb.octant(foot(me), foot(cand)) & 0xFF)
    s = d * 256 + ang
    if pref == 0:
        return NO_TARGET
    small = unit_size(me) < 2 and int(me.stats.get("mind", 0) if me.stats is not None else 0) >= 15
    if pref == 1 and small:
        s += s >> 1
    elif pref == 4 and small:
        s -= s >> 2
    return s


def score_stand(world, me, cand):
    """`FUN_005713f8(me, cand)`, the score of the stand-ground pass (group order 3, `FUN_005725a8`): the same terms as `score`, but the
    candidate must be within reach at once: the cell distance (melee) or `max(1, distance - range + 1)` (ranged) must be below 2, i.e. an
    adjacent cell or inside the attack range; the preference then only doubles (1) or halves (4) the score (no mind / HP clause, no `0x40000`)."""
    d = chebyshev((cand.x, cand.y), (me.x, me.y))
    cls = class_of(cand)
    if cls == 1 and attack_range(world, cand) > 1:
        cls = 0
    my_range = attack_range(world, me)
    if my_range > 1:
        pref = PREFERENCE[cls]
        d = d - my_range + 1 if d > my_range else 1
    else:
        pref = PREFERENCE[class_of(me) * 4 + cls]
    if d >= 2 or pref == 0:
        return NO_TARGET
    s = d * 256 + mv._fold(me.facing, cb.octant(foot(me), foot(cand)) & 0xFF)
    if pref == 1:
        s *= 2
    elif pref == 4:
        s >>= 1
    return s


def centroid_stats(world, g):
    """`FUN_0056fa63`: mean cell, widest member distance, and reach (distance + scan range) of the living-or-dying members."""
    mem = [world.units[i] for i in g.members if i in world.units]
    n = len(mem)
    if not n:
        return None
    cx, cy = sum(u.x for u in mem) // n, sum(u.y for u in mem) // n
    g.centre = word(cx, cy)
    g.spread = max(chebyshev((u.x, u.y), (cx, cy)) for u in mem)
    g.reach = max(chebyshev((u.x, u.y), (cx, cy)) + _scan_range(u) for u in mem)
    return mem


# --- command emission --------------------------------------------------------------------------------------------------------

def emit(world, cmd):
    """Log the command (`Simulation.step` drains `ai_emitted` into the session log) and apply it at once, as the group pass does."""
    world.ai_emitted.append(cmd)
    apply(world, cmd)


def go(world, m, w):
    """`FUN_0056c8af(m, cell word)`: brain mode 1 towards the cell."""
    emit(world, MoveUnits(m.owner, (m.id,), unword(w), ai=True))


def attack(world, m, t):
    """`FUN_0056acc8` / `FUN_0056c840`: brain mode 5 / 6 on the target (a melee unit: the same driver)."""
    emit(world, AttackUnit(m.owner, (m.id,), t.id, ai=True))


def _human(world, m):
    pl = world.players.get(m.owner)
    return pl is not None and pl.human


def idle(world, m):
    """`FUN_0056afd9`: a computer-owned unit with nothing to do looks around (brain mode 0xb) and a computer-owned mage then runs
    `FUN_0056c592` (`mage_idle`: heal, Shield, friends; ai.md 12.5); a human's unit gets brain mode 0 (`FUN_0056b025`; a human mage would run
    the caster scan `FUN_0056bc7b`, not built: ai.md 12.6).  Already in that mode = a no-op in the exe (the mode is set to the value it has),
    so the command is not issued again (log size)."""
    if _human(world, m):
        if not (m.mode_look or m.mode_go or m.mode_attack):
            return
        emit(world, Stop(m.owner, (m.id,), ai=True))
        return
    if not (m.mode_look and not m.mode_go and not m.mode_attack and not m.mode_cast and not m.mode_cell):
        emit(world, Stop(m.owner, (m.id,), ai=True))
    if is_mage(world, m):
        mage_idle(world, m)


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
    from . import orders
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
        u.mode_go = u.mode_attack = u.mode_look = u.mode_cast = False
        u.mover.waiting = u.mover.parked = False
    g.order = GROUP_ORDER
    record_stats(world, g, mem)
    if g.radius < MIN_GUARD_RANGE:
        g.radius = g.base = DEFAULT_RADIUS


def record_stats(world, g, mem):
    """`FUN_0057026e` = `FUN_0056f850` + `+0x2d = +0x38 := +0x2c`: centroid of the 16-bit positions, widest member distance, reach (distance +
    scan range); the pool radius starts as the reach."""
    n = len(mem)
    sx, sy = sum(pos16(u)[0] for u in mem), sum(pos16(u)[1] for u in mem)
    cx, cy = (sx // n) >> 8 & 0xFF, (sy // n) >> 8 & 0xFF
    g.centre = word(cx, cy)
    g.spread = max(chebyshev((u.x, u.y), (cx, cy)) for u in mem)
    g.reach = max(chebyshev((u.x, u.y), (cx, cy)) + _scan_range(u) for u in mem)
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
        from . import triggers
        triggers.run_pass(world)
    for owner in sorted({g.key[0] for g in world.ai_groups.values()}):
        for g in [g for g in world.ai_groups.values() if g.key[0] == owner]:
            g.members = [i for i in g.members if i in world.units]
            if not g.members:
                g.order = G_EMPTY
                continue
            if not g.awake:                             # FUN_00570087: a sleeping squad's pass is skipped (handler and post step)
                continue
            run_group(world, g)


def run_group(world, g):
    """`FUN_005700f3` for one non-empty group (a squad `AiGroup` or a command group `OrderGroup`): the handler of its group order, then the post
    step `FUN_00573713` on every member (whatever the order).  Called by `ai_system` and by `orders.group_pass`."""
    from . import orders
    block = (world.tick + 1) >> 4                       # server+0, the 16-tick block counter (Simulation.block)
    order = g.order
    if order == G_COMPUTER:
        handler(world, g, block)
    elif order == G_GUARD:
        guard_pass(world, g)
    elif order == G_HOLD:
        hold_pass(world, g)
    elif order == G_STAND:
        stand_pass(world, g)
    elif order == G_MOVE:
        orders._pass_move(world, g)
    elif order == G_SWARM:
        swarm_pass(world, g)
    elif order == G_WANDER:
        wander_pass(world, g)
    elif order == G_STILL:
        for i in list(g.members):
            idle(world, world.units[i])                 # FUN_0057311c: FUN_0056afd9 for every member
    elif order == G_EMPTY:
        for i in list(g.members):
            guard_scan(world, world.units[i])           # FUN_00573159: FUN_0056afac(m, 0)
    elif order == G_NONE:
        orders._pass_orders(world, g)
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


def _act(world, m, post):
    """The per-member clause of the handlers `57275f`, `572d57`, `572e1e`: a target -> `FUN_0056acc8`; none -> `post(m)`."""
    t = world.units.get(m.ai.target) if m.ai.target is not None else None
    if t is not None:
        engage(world, m, t)
    elif post is not None:
        post(m)


def guard_pass(world, g):
    """`FUN_0057275f` (group order 1, the G key and the scripted guard): the machinery of `handler` without the hit / stamp branch table:
    centroid stats, pool, radius filter, assign, first-pass radius growth; act: no target -> on the post (`brain+0`, at a centre) `idle`, else `go(anchor)`."""
    mem = centroid_stats(world, g)
    if not mem:
        return
    _assign_targets(world, mem, _pool(world, g, mem))
    _grow(world, g)
    for m in mem:
        _act(world, m, lambda m: idle(world, m) if _on_post(m) else go(world, m, word(*m.anchor) if m.anchor is not None else 0))


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
    dest = tuple(g.target)
    for m in mem:
        _act(world, m, lambda m: idle(world, m) if ((m.x, m.y) == dest and (m.sub_x, m.sub_y) == (mv.CENTRE, mv.CENTRE))
             else go(world, m, word(*dest)))


def swarm_pass(world, g):
    """`FUN_00572e1e(group, dest)` (group order 5, swarm): the pool; empty -> `FUN_00573198` (the move group pass towards the members' own
    destinations, `brain+0xa`); else assign (no radius), act: no target -> `FUN_0056afac(m, 1)` = `idle`, target -> `FUN_0056acc8`."""
    from . import orders
    mem = _live(world, g)
    if not mem:
        return
    pool = _pool_all(world, mem)
    if not pool:
        orders._pass_move(world, g)
        return
    _assign_targets(world, mem, pool)
    for m in mem:
        _act(world, m, lambda m: idle(world, m))


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


def _assign_targets(world, mem, pool):
    """`FUN_0057240b`: each member's best-scoring pool unit (first wins a tie), or none."""
    for m in mem:
        best, best_s = None, NO_TARGET
        for c in pool:
            s = score(world, m, c)
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
    for m in mem:
        best, best_s = None, NO_TARGET
        for c in pool:
            s = score_stand(world, m, c)
            if s < best_s:
                best, best_s = c, s
        m.ai.target = best.id if best is not None else None
    for m in mem:
        t = world.units.get(m.ai.target) if m.ai.target is not None else None
        if t is None:
            m.ai.target = None
            idle(world, m)
        else:
            engage(world, m, t)


def engage(world, m, t):
    """`FUN_0056acc8(m, t)` (docs/engine/ai.md 12.2): the special-attack roll over the monster's three slots (one `rand15` per used slot, the last
    slot whose `rand15 < probability * 0x147` wins; Teleport only when the target is more than 2 cells away), else a computer-owned mage tries
    `FUN_0057a769` (`caster_attack`), else brain mode 5 on the target.  A human-owned unit takes mode 5 (`FUN_0056b059` does nothing without the
    hero's selected spell, which the engine does not have; the scan `FUN_0056bc7b` is not built).  The target flag `+0x4c & 8` (off the map) and
    the `m == t` branch (`FUN_00567988`) are never reached from the pools (§10)."""
    pick = 0
    if not m.human:
        for n, p in spells.monster_slots(m.stats):
            if n and world.rng.rand15() < p:            # FUN_0057afc0 = rand(); only used slots draw
                pick = n
    if pick and (pick != spells.TELEPORT or chebyshev((t.x, t.y), (m.x, m.y)) > 2):
        special_attack(world, m, t, pick)
        return
    if m is t:
        return
    if not _human(world, m) and is_mage(world, m) and caster_attack(world, m, t):
        return
    attack(world, m, t)


# --- casters (docs/engine/ai.md 12) ----------------------------------------------------------------------------------------

SPECIAL_ENEMY = frozenset((1, 5, 10, 11, 16, 18, 26, 28, 29))      # FUN_0056a981 jump table 0x56abe7: cast at the enemy
SPECIAL_CELL = frozenset((2, 3, 6, 7, 14, 15, 17))                  # at the enemy's cell
SPECIAL_SELF = frozenset((4, 8, 12, 13, 19, 20, 21, 24, 25, 27))    # at itself
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
    from allods2.formats import passability as pas
    from engine.cellslots import pack
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
    if n in SPECIAL_ENEMY:
        cast_at(world, m, t, n)
    elif n in SPECIAL_CELL:
        cast_cell(world, m, (t.x, t.y), n)
    elif n in SPECIAL_SELF:
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


def caster_attack(world, m, t):
    """`FUN_0057a769(m, t)` (ai.md 12.4): a computer-owned mage picks a random offensive spell it can pay (n = 1..28) and casts it at the target;
    with mind >= 60 it first draws `rand(100)` and on <= 29 runs the whole decision again and reports 0 (the caller then sets mode 5)."""
    if spells.mind_of(m) >= CLEVER_MIND and _divide(world.rng, 100) <= CLEVER_MELEE:
        engage(world, m, t)
        return False
    cands = [n for n in range(1, OWN_SPELLS) if _wrapper_ok(world, m, n, False)]
    k = _divide(world.rng, len(cands))
    if not cands:
        return False
    cast_at(world, m, t, cands[k])
    return True


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
    """`u+0x144 & 1 << n`: only Invisibility (12, `Unit.hidden`) exists in the engine; every other effect is never active (no effect system)."""
    return n == spells.INVISIBILITY and u.hidden


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


# --- guard scan (FUN_0056a1fb), auto scan (FUN_0056ed4e) ---------------------------------------------------------------------

def guard_scan(world, u):
    """`FUN_0056a1fb`: the best enemy within the unit's attack range among those in its own sight, else `FUN_0056afd9`."""
    rng_ = attack_range(world, u)
    best, best_gap, best_ang = None, rng_ + 1, 0xFF
    for c in _hostiles_on(world, u.owner, _visible(world, [u])):
        if score(world, u, c) == NO_TARGET:
            continue
        gap = follow_distance(foot(u), foot(c)) + (1 if class_of(c) == 3 and class_of(u) != 3 else 0)
        ang = mv._fold(cb.octant(foot(u), foot(c)) & 0xFF, u.facing)
        if gap < best_gap:
            best, best_gap, best_ang = c, gap, ang
        elif gap == best_gap and gap <= rng_ and ang <= best_ang:
            best, best_ang = c, ang
    if rng_ < best_gap:
        best = None
    if best is None:
        idle(world, u)
    else:
        attack(world, u, best)
    mv.restamp_displaced(world, u)                      # 0x56a592-0x56a5f0: a displaced stamp cell is stamped again


def auto_scan(world, u):
    """`FUN_0056ed4e` (the mover event of a unit under a stand order): the enemy in attack range with the smallest facing change."""
    rng_ = attack_range(world, u)
    near, best_d = [], 0xFF
    for c in world.units.values():                      # creation order: the exe walks its creature list
        d = chebyshev((c.x, c.y), (u.x, u.y))
        if d <= rng_ and d <= best_d and c is not u:
            near.append(c)
            best_d = d
    near = [c for c in near if c.hp > 0 and at_war(world, u.owner, c.owner)]
    target, best = None, 300
    for c in near:
        a = mv._fold(u.facing, cb.octant(foot(u), foot(c)) & 0xFF)
        if a <= best:
            target, best = c, a
    if target is None:
        idle(world, u)
    else:
        attack(world, u, target)


# --- hit reaction (FUN_0056e6b8) ----------------------------------------------------------------------------------------------

def _set_war(world, a, b):
    pl = world.players.get(a)
    if pl is not None and 0 < b <= len(pl.relations) and not pl.relations[b - 1] & 3:
        rel = list(pl.relations)
        rel[b - 1] |= 1
        pl.relations = tuple(rel)


def declare_war(world, attacker_owner, victim_owner):
    """`FUN_0057977a(relations, attacker, victim, 0)`: a hit between two neutral owners (relation & 3 == 0) sets the war bit both ways
    (attacker -> victim first, then victim -> attacker; the exe also posts a notice for a human attacker, not modelled)."""
    _set_war(world, attacker_owner, victim_owner)
    _set_war(world, victim_owner, attacker_owner)


def on_hit(world, attacker, victim):
    """Called by the fight code for every resolved attack: alert the victim, reveal the attacker's cell to its squad, and store the cell
    10 cells beyond the victim on the ray attacker -> victim."""
    declare_war(world, attacker.owner, victim.owner)
    b = victim.ai
    b.alerted = 1
    b.mark_cell = word(attacker.x, attacker.y)
    b.mark_age = 0
    b.hit_by = attacker.id
    b.hit_tick = world.tick + 1                         # the exe's counter is already incremented in the creature pass
    ax, ay = pos16(attacker)
    vx, vy = pos16(victim)
    dx, dy = vx - ax, vy - ay
    big = max(abs(dx), abs(dy))
    if big == 0:
        b.hit_cell = 0
        return
    s = RUN_AWAY / big
    y = int(victim.y + dy * s)
    x = int(victim.x + dx * s)
    b.hit_cell = ((y << 8) + x) & 0xFFFF


# --- flee step (FUN_00573713) --------------------------------------------------------------------------------------------------

def _enemies(world, u, r):
    """`FUN_0054ec6a` + `FUN_00567a16`: the occupants of the Chebyshev square of radius r that the owner is at war with (dying ones included).
    The list holds creatures only: a cell with bit 0x20 and a record yields its occupant slot rec+4 (`FUN_00551edb`), which is written for
    ground classes 1, 2 only (flyers use rec+8, structures rec+0xc, piles another slot), once per cell of the occupant's own `size x size`
    footprint (a big unit is listed once for each footprint cell inside the square, no de-duplication: it weighs more in the mean position),
    first come per cell.  Hidden units (`Unit.hidden`) need a detector among the unit's group (squad)."""
    cells = [(u.x + dx, u.y + dy) for dy in range(-r, r + 1) for dx in range(-r, r + 1)]
    out = mv._occupants(world, cells)                   # the occupant slot of each cell (first come; a loser of the race is missing)
    detectors = [m for m in world.units.values() if m.owner == u.owner and m.squad == u.squad and m.hp > 0] if any(c.hidden for c in out) else ()
    return [c for c in out if at_war(world, u.owner, c.owner) and (not c.hidden or _detected(c, detectors))]


def flee_cell(world, u, near):
    """`FUN_00558b92(u, mean position of the hostiles, 3)`: 3 cells beyond u on the ray from their centre through u, along the dominant
    axis (float32 slope), clamped to the playable area."""
    n = len(near)
    px = sum(pos16(c)[0] for c in near) // n
    py = sum(pos16(c)[1] for c in near) // n
    ux, uy = pos16(u)
    dx, dy = ux - px, uy - py
    dx, dy = dx or 1, dy or 1
    f32 = lambda v: struct.unpack("<f", struct.pack("<f", v))[0]       # noqa: E731
    if abs(dx) > abs(dy):
        s = f32(dy / dx)
        b = f32(uy - ux * s)
        nx = ux + FLEE_CELLS * 256 if dx > 0 else ux - FLEE_CELLS * 256
        ny = int(nx * s + b)
    else:
        s = f32(dx / dy)
        b = f32(ux - uy * s)
        ny = uy + FLEE_CELLS * 256 if dy > 0 else uy - FLEE_CELLS * 256
        nx = int(ny * s + b)
    nx, ny = nx >> 8, ny >> 8
    nx = min(max(nx, 8), world.width - 9)
    ny = min(max(ny, 8), world.height - 9)
    return word(nx, ny)


def post_step(world, g, m):
    """`FUN_00573713`, after the handler for each member: the wimpy test (hostile within 10), else the withdraw test (within 2)."""
    if m.stats is None or m.hp <= 0:
        return
    wimpy, withdraw = int(m.stats.get("wimpy", 0) or 0), int(m.stats.get("withdraw", 0) or 0)
    if m.tweak == 1:
        wimpy >>= 1                                                                # easy mode halves brain+0x44 at load (0x561e96)
    if m.hp <= wimpy and _enemies(world, m, WIMPY_RADIUS):
        near = [c for c in _enemies(world, m, WIMPY_RADIUS) if c.hp > 0]          # FUN_0056c9bc counts the living
    elif m.hp <= withdraw and _enemies(world, m, WITHDRAW_RADIUS):
        near = _enemies(world, m, WITHDRAW_RADIUS)                                 # FUN_0056ce0f: any
    else:
        return
    if near:
        go(world, m, flee_cell(world, m, near))
    else:
        guard_scan(world, m)


# --- brain-level executors of the AI commands ------------------------------------------------------------------------------

def apply(world, cmd):
    """Execute an `ai=True` command: the Brain mode changes of `FUN_0056c8af` (1), `FUN_0056acc8` (5), `FUN_0056afd9` (0xb).  The unit's
    order, anchor, stopped flag and squad are untouched (the exe writes the Brain, not the order)."""
    for uid in cmd.unit_ids:
        u = world.units.get(uid)
        if u is None or u.hp <= 0:
            continue
        m = u.mover
        if isinstance(cmd, MoveUnits):
            cell = cmd.cell                                     # CONFIRMED: the exe feeds the raw cell to its planner (ai.md 3)
            u.mode_go, u.mode_attack, u.mode_look = True, False, False
            u.mode_cast = u.mode_cell = False
            if m.goal != cell:
                m.goal = cell
                m.arrived = m.failed = False
            m.waiting = m.parked = False
        elif isinstance(cmd, AttackUnit):
            t = world.find_unit(cmd.target_id)
            if t is None:
                continue
            u.target = t.id
            u.range = cb.combat_stats(world, u).range
            u.mode_attack, u.mode_go, u.mode_look = True, False, False
            u.mode_cast = u.mode_cell = False
            m.waiting = m.parked = False
        elif isinstance(cmd, CastSpell):
            apply_cast(world, u, cmd)
        elif isinstance(cmd, Stop):
            u.mode_look, u.mode_go, u.mode_attack, u.mode_cast = not _human(world, u), False, False, False
            u.mode_cell = False


def apply_cast(world, u, cmd):
    """The AI cast (`brain+0x60 := 1`, then `FUN_0056c72b` or `FUN_0056969c`): Brain mode 8 at the unit (target, wrapper, range = wrapper `+9`, the
    target's `brain+0xa4/+0xa8` := spell number / tick) or Brain mode 9 at the cell.  Order, anchor and group untouched."""
    if world.spell_table is None or world.spell_table.get(cmd.spell_id) is None:
        return
    w = spells.Wrapper(cmd.spell_id)
    sp = world.spell_table.get(cmd.spell_id)
    if cmd.cell is None:
        t = world.find_unit(cmd.target_id)
        if t is None:
            return
        u.mode_cast, u.mode_cell = True, False
        u.cast_target = t.id
        t.ai.spell_mark, t.ai.spell_tick = cmd.spell_id, world.tick
    else:
        u.mode_cell, u.mode_cast = True, False
        u.cast_cell = tuple(cmd.cell)
    u.mode_go = u.mode_attack = u.mode_look = False
    u.cast_wrapper = w
    u.range = spells.wrapper_range(sp, w, spells.unit_level(u, sp))
    u.ai_cast = True
    u.mover.waiting = u.mover.parked = False


def look_around(world, u):
    """Brain mode 0xb (`FUN_0056e5bc`), every tick: an idle computer-owned unit turns to a random direction now and then.  A settled unit
    turns on `rand() <= 0xcc` (about 0.6 % of the ticks) or at once after a hit; a turn in progress continues."""
    m = u.mover
    if u.facing == m.target_facing:
        if u.ai.alerted == 0 and world.rng.rand15() > 0xCC:
            u.state = mv.IDLE_STATE
            mv._set_action(world, u, mv.IDLE)
            return
        new = (u.facing + 0x21 + world.rng.rand(0xBD)) & 0xFF
        m.target_facing = new
        u.ai.alerted = 0
    face = m.target_facing
    if u.facing != face or m.turning:
        mv._set_action(world, u, mv.TURN)
    mv._turn_toward(u, face)
    u.state = mv.MOVE_STATE


def on_static_plan(world, u, res, target):
    """The class-0x12 clause of the static plan request (`0x54e245`, simulation 7.4): a unit of a squad in attack mode whose plan ended
    on a fallback cell still farther than its range from the target stamps the failure (`brain+0x16 := block counter`)."""
    from .pathfinding import footprint_gap
    if not (world.ai_on and u.mode_attack and group_order(world, u) == GROUP_ORDER):
        return
    here = res.cells[-1] if res.cells else (0, 0)
    if footprint_gap(here, target, unit_size(u)) > attack_range(world, u):
        u.ai.stamp = ((world.tick + 1) >> 4) & 0xFFFF


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
    from . import orders
    group.members = [i for i in group.members if i in world.units]      # a squad keeps the ids of its dead
    if order == G_GUARD:
        orders.guard_group(world, group, int(target or 0))
    elif order == G_HOLD:
        orders.hold_group(world, group, *target)
    elif order == G_STAND:
        orders.stop_group(world, group)
    elif order == G_MOVE:
        orders.move_group(world, group, *target)
    elif order == G_SWARM:
        orders.move_group(world, group, *target, swarm=True)
    elif order == G_WANDER:
        orders.wander_group(world, group)
    elif order == G_COMPUTER:
        orders.guard_group(world, group, int(target or 0), computer=True)
    elif order == G_STILL:
        orders.still_group(world, group)
    else:
        raise ValueError("group order %#x has no scripted setter" % order)


def mode_name(u):
    """The Brain mode of a unit as the debug overlay names it."""
    if u.hp <= 0:
        return "dead"
    for flag, name in ((u.mode_attack, "attack"), (u.mode_go, "go"), (u.mode_look, "look")):
        if flag:
            return name
    return "idle"


def overlay(world, u):
    """What the `ai` debug overlay draws for unit `u` (None when it is not in a squad): its sight (the aggro area), the ring at the
    squad's pool radius round the centroid, the post, the target's cell and a label with the mode."""
    g = next((g for g in world.ai_groups.values() if u.id in g.members), None)
    if g is None:
        return None
    cx, cy = unword(g.centre)
    r = g.radius
    ring = {(x, y) for x in range(cx - r, cx + r + 1) for y in (cy - r, cy + r) if 0 <= x < world.width and 0 <= y < world.height}
    ring |= {(x, y) for y in range(cy - r, cy + r + 1) for x in (cx - r, cx + r) if 0 <= x < world.width and 0 <= y < world.height}
    t = world.units.get(u.ai.target) if u.ai.target is not None else None
    label = "%s order %#x t=%s R=%d stamp=%d" % (mode_name(u), u.order, "-" if t is None else t.uid, r, u.ai.stamp)
    return {"sight": set(sight(world, u.x, u.y, _scan_range(u))), "ring": ring, "post": u.anchor,
            "target": (t.x, t.y) if t is not None else None, "label": label}


__all__ = ["enable", "ai_system", "on_hit", "apply", "AiState"]
