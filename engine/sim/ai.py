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
from .commands import AttackUnit, MoveUnits, Stop
from .pathfinding import chebyshev, follow_distance, foot, unit_size

GROUP_ORDER = 0x12                  # group order of the computer players' squads (FUN_00570aba)
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


def _hostiles_on(world, owner, cells):
    """The units of cells, creation order, that `owner` is at war with (`FUN_00567a16` + `FUN_00567ddf`; the hidden-unit clause
    is skipped: no effect sets flag 0x1000 yet): the living ones, or, when there is none, the dying ones (HP < 1, not yet removed)."""
    ids = set()
    for c in cells:
        ids |= world.units_at(*c)
    out = [world.units[i] for i in ids]
    out = [u for u in out if at_war(world, owner, u.owner)]
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


def idle(world, m):
    """`FUN_0056afd9`: a computer-owned unit with nothing to do looks around (brain mode 0xb).  Already looking = a no-op in the exe
    (the mode is set to the value it has), so the command is not issued again (log size)."""
    if m.mode_look and not m.mode_go and not m.mode_attack:
        return
    emit(world, Stop(m.owner, (m.id,), ai=True))


# --- set-up ---------------------------------------------------------------------------------------------------------------

def enable(world):
    """Build the squads of the computer players and run `FUN_00570aba(group, 0)` on each (map load, `FUN_00562745`)."""
    world.ai_on = True
    world.ai_groups.clear()
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


def init_group(world, g):
    """`FUN_00570aba` + `FUN_0057026e` + `FUN_0056f850`: members stand (order 0xb, anchor = own cell), centroid of the 16-bit positions,
    radius = reach, at least the default."""
    mem = [world.units[i] for i in g.members]
    for u in mem:
        mv.cancel(u)
        u.order = GUARD_ORDER
        u.anchor = (u.x, u.y)
        u.mode_go = u.mode_attack = u.mode_look = False
        u.mover.waiting = u.mover.parked = False
    g.order = GROUP_ORDER
    n = len(mem)
    sx, sy = sum(pos16(u)[0] for u in mem), sum(pos16(u)[1] for u in mem)
    cx, cy = (sx // n) >> 8 & 0xFF, (sy // n) >> 8 & 0xFF
    g.centre = word(cx, cy)
    g.spread = max(chebyshev((u.x, u.y), (cx, cy)) for u in mem)
    g.reach = max(chebyshev((u.x, u.y), (cx, cy)) + _scan_range(u) for u in mem)
    g.radius = g.base = g.reach
    if g.radius < MIN_GUARD_RANGE:
        g.radius = g.base = DEFAULT_RADIUS


# --- the pass (FUN_0056fe4d -> FUN_00570087 -> FUN_005728fa) ---------------------------------------------------------------

def ai_system(world, commands):
    """Run the squads' handler at `tick & 15 == 6`, before the command drain; players in id order, squads in creation order."""
    if not world.ai_on or (world.tick & 15) != 6:
        return
    block = (world.tick + 1) >> 4                       # server+0, the 16-tick block counter (Simulation.block)
    for owner in sorted({g.key[0] for g in world.ai_groups.values()}):
        for g in [g for g in world.ai_groups.values() if g.key[0] == owner]:
            g.members = [i for i in g.members if i in world.units]
            if not g.members:
                g.order = 0xFF
                continue
            handler(world, g, block)
            for i in list(g.members):
                post_step(world, g, world.units[i])


def handler(world, g, block):
    """`FUN_005728fa`."""
    mem = centroid_stats(world, g)
    pool = _pool(world, g, mem)
    _assign_targets(world, mem, pool)
    if not g.seen:
        g.radius = g.base + POOL_GROW + world.rng.rand(2) - 1       # FUN_005726f7: FUN_0057aff0(-1, 1)
        g.passes = 0
    else:
        g.passes += 1
    g.seen = 1
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
        elif (m.x, m.y) == m.anchor and (m.sub_x, m.sub_y) == (mv.CENTRE, mv.CENTRE):
            idle(world, m)
        else:
            go(world, m, word(*m.anchor))


def _pool(world, g, mem):
    """`FUN_00571c4d` + `FUN_00567e92`: the hostile living units on the squad's visible cells within `radius` of the centroid."""
    owner = g.key[0]
    cells = _visible(world, mem)
    cen = unword(g.centre)
    return [u for u in _hostiles_on(world, owner, cells) if chebyshev((u.x, u.y), cen) <= g.radius]


def _assign_targets(world, mem, pool):
    """`FUN_0057240b`: each member's best-scoring pool unit (first wins a tie), or none."""
    for m in mem:
        best, best_s = None, NO_TARGET
        for c in pool:
            s = score(world, m, c)
            if s < best_s:
                best, best_s = c, s
        m.ai.target = best.id if best is not None else None


def engage(world, m, t):
    """`FUN_0056acc8` for a unit without a spell list: brain mode 5 on the target (spell / special attacks: phase K)."""
    if m is t:
        return
    attack(world, m, t)


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
    """`FUN_0054ec6a` + `FUN_00567a16`: units in the Chebyshev square of radius r the owner is at war with (dying ones included)."""
    out = []
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            for i in world.units_at(u.x + dx, u.y + dy):
                c = world.units[i]
                if at_war(world, u.owner, c.owner):
                    out.append(c)
    out.sort(key=lambda c: c.seq)
    return out


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

def _clamp_cell(world, cell):
    return min(max(cell[0], 8), world.width - 9), min(max(cell[1], 8), world.height - 9)


def apply(world, cmd):
    """Execute an `ai=True` command: the Brain mode changes of `FUN_0056c8af` (1), `FUN_0056acc8` (5), `FUN_0056afd9` (0xb).  The unit's
    order, anchor, stopped flag and squad are untouched (the exe writes the Brain, not the order)."""
    for uid in cmd.unit_ids:
        u = world.units.get(uid)
        if u is None or u.hp <= 0:
            continue
        m = u.mover
        if isinstance(cmd, MoveUnits):
            cell = _clamp_cell(world, cmd.cell)                 # DECISION: the exe feeds the raw cell to its planner (unreachable border)
            u.mode_go, u.mode_attack, u.mode_look = True, False, False
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
            m.waiting = m.parked = False
        elif isinstance(cmd, Stop):
            u.mode_look, u.mode_go, u.mode_attack = True, False, False


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
    if not (world.ai_on and u.mode_attack and u.order == GUARD_ORDER):
        return
    here = res.cells[-1] if res.cells else (0, 0)
    if footprint_gap(here, target, unit_size(u)) > attack_range(world, u):
        u.ai.stamp = ((world.tick + 1) >> 4) & 0xFFFF


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
