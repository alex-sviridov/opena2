"""reaction: part of the monster AI (docs/engine/ai.md); see the package docstring in __init__."""

import struct
from engine.world import DEAD
from .. import combat as cb, movement as mv
from ..pathfinding import chebyshev, follow_distance, foot
from .actions import idle
from .autocast import _members_of
from .brain import attack, go
from .perception import NO_TARGET, _detected, _hostiles_on, _visible, at_war, pos16, reach_gap, word
from .targeting import score


RUN_AWAY = 10.0                     # cells beyond the victim on the ray attacker -> victim (FUN_0056e6b8)


FLEE_CELLS = 3                      # FUN_00558b92 distance of the wimpy / withdraw step


WIMPY_RADIUS, WITHDRAW_RADIUS = 10, 2


# --- guard scan (FUN_0056a1fb), auto scan (FUN_0056ed4e) ---------------------------------------------------------------------

def _attack_or_idle(world, u, target):
    """The end of both scans: no target -> `idle` (`FUN_0056afd9`), else `attack` (`FUN_0056acc8`)."""
    if target is None:
        idle(world, u)
    else:
        attack(world, u, target)


def guard_scan(world, u):
    """`FUN_0056a1fb`: the best enemy within the unit's attack range among those in its own sight, else `FUN_0056afd9`."""
    rng_ = cb.attack_range(world, u)
    best, best_gap, best_ang = None, rng_ + 1, 0xFF
    for c in _hostiles_on(world, u.owner, _visible(world, [u])):
        if score(world, u, c) == NO_TARGET:
            continue
        gap = follow_distance(foot(u), foot(c)) + (1 if cb.move_class(c) == 3 and cb.move_class(u) != 3 else 0)
        ang = mv._fold(cb.octant(foot(u), foot(c)) & 0xFF, u.facing)
        if gap < best_gap:
            best, best_gap, best_ang = c, gap, ang
        elif gap == best_gap and gap <= rng_ and ang <= best_ang:
            best, best_ang = c, ang
    if rng_ < best_gap:
        best = None
    _attack_or_idle(world, u, best)
    mv.restamp_displaced(world, u)                      # 0x56a592-0x56a5f0: a displaced stamp cell is stamped again


def auto_scan(world, u):
    """`FUN_0056ed4e` (the mover event of a unit under a stand order): the enemy in attack range with the smallest facing change."""
    rng_ = cb.attack_range(world, u)
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
    _attack_or_idle(world, u, target)


# --- hit reaction (FUN_0056e6b8) ----------------------------------------------------------------------------------------------

def _set_war(world, a, b):
    pl = world.players.get(a)
    if pl is not None and 0 < b <= len(pl.relations) and not pl.relations[b - 1] & 3:
        rel = list(pl.relations)
        rel[b - 1] |= 1
        pl.relations = tuple(rel)


def declare_war(world, attacker_owner, victim_owner, area=False, victim=None):
    """`FUN_0057977a(relations, attacker, victim, area)`: a hit between two neutral owners (relation & 3 == 0) sets the war bit attacker ->
    victim, then victim -> attacker; for an area hit (`area`, the carriers' `FUN_00518681`) the second only when the victim's counter
    `brain+0xac > 10`, its HP < max / 2 or it is dead, and every such area hit adds 1 to the counter (docs/engine/effects.md 6.3).  The exe
    also posts a notice for a human attacker (not modelled)."""
    _set_war(world, attacker_owner, victim_owner)
    if not area or victim is None:
        _set_war(world, victim_owner, attacker_owner)
        return
    pl = world.players.get(victim_owner)
    if pl is None or not 0 < attacker_owner <= len(pl.relations) or pl.relations[attacker_owner - 1] & 3:
        return
    if victim.ai.area_hits > 10 or victim.hp < int(victim.hp_max / 2) or victim.state == DEAD:
        _set_war(world, victim_owner, attacker_owner)
    victim.ai.area_hits += 1


def on_hit(world, attacker, victim, area=False):
    """Called by the fight code for every resolved attack: alert the victim, reveal the attacker's cell to its squad, and store the cell
    10 cells beyond the victim on the ray attacker -> victim.  `area`: the third argument 1 of the area carriers (`declare_war`)."""
    declare_war(world, attacker.owner, victim.owner, area, victim)
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


# --- the Prismatic Spray target list (FUN_00579ddf, docs/engine/effects.md 11) ----------------------------------------------------------

def spray_distance(caster, u):
    """`FUN_00579d62(caster, u)`: `(gap level << 8) + facing difference` as a word: `FUN_00556dcd` (`reach_gap`, low byte) and `FUN_0055aa21(caster
    facing, octant(caster, u))` (the same terms as the score of `FUN_005711ea`)."""
    ang = mv._fold(caster.facing, cb.octant(foot(caster), foot(u)) & 0xFF)
    return (((reach_gap(caster, u) & 0xFF) << 8) + ang) & 0xFFFF


def spray_targets(world, caster, target, count, reach):
    """`FUN_00579ddf(caster, target, out, count, reach)`: the hit reaction on the target first (`FUN_0056e6b8`, with the AI on), then the caster's
    group pool (`FUN_00571c4d`: the living at-war units on the cells the group sees, creation order; the dying ones only when no living one is
    there) is scored by `spray_distance` and filtered by `score <= reach << 8` (so the gap level is below `reach`, or equal with no turn); `count`
    selection rounds each take the lowest score strictly below the best so far (ties keep the earlier unit; a picked unit is marked 0xffdc and
    its word is what the later test reads).  The list is the target, then the picked units that are not the target, cut from the tail to
    `count` entries.  An empty pool gives just the target.  CONFIRMED (`0x579ddf`-`0x57a235`, `FUN_0057b080` = remove tail); the second pool
    `+0xa88` is always empty here (`FUN_00571c4d` merges the dead list back into an empty pool, ai.md 4 step 6)."""
    if world.ai_on:
        on_hit(world, caster, target)
    mem = _members_of(world, caster)
    pool = _hostiles_on(world, mem[0].owner, _visible(world, mem), mem)
    out = [target]
    if not pool:
        return out
    limit = (reach & 0xFF) << 8
    cand, scores = [], []
    for u in pool:
        d = spray_distance(caster, u)
        if d <= limit:
            cand.append(u)
            scores.append(d)
    best_s, best_i = [0xFFFA] * count, [0xFFFA] * count
    for i in range(count):
        for j, d in enumerate(scores):
            if d < best_s[i]:
                best_s[i], best_i[i] = d & 0xFFFF, j
        if best_i[i] < 60000:
            scores[best_i[i]] = 0xFFDC
    for i in range(count):
        if best_i[i] < 0xFDE8 and best_s[i] < 0xFDE8 and cand[best_i[i]] is not target:
            out.append(cand[best_i[i]])
    return out[:count] if count > 0 else out


# --- flee step (FUN_00573713) --------------------------------------------------------------------------------------------------

def _enemies(world, u, r):
    """`FUN_0054ec6a` + `FUN_00567a16`: the occupants of the Chebyshev square of radius r that the owner is at war with (dying ones included).
    The list holds creatures only: a cell with bit 0x20 and a record yields its occupant slot rec+4 (`FUN_00551edb`), which is written for
    ground classes 1, 2 only (flyers use rec+8, structures rec+0xc, piles another slot), once per cell of the occupant's own `size x size`
    footprint (a big unit is listed once for each footprint cell inside the square, no de-duplication: it weighs more in the mean position),
    first come per cell.  Hidden units (`Unit.hidden`) need a detector among the unit's group (squad)."""
    return enemies_around(world, u, u.x, u.y, r)


def enemies_around(world, u, cx, cy, r):
    """`FUN_00567988(u, cell word)` (the same square round any cell; `u` supplies the owner and the squad that detects hidden units)."""
    cells = [(cx + dx, cy + dy) for dy in range(-r, r + 1) for dx in range(-r, r + 1)]
    out = mv._occupants(world, cells)                   # the occupant slot of each cell (first come; a loser of the race is missing)
    detectors = [m for m in world.units.values() if m.owner == u.owner and m.squad == u.squad and m.hp > 0] if any(c.hidden for c in out) else ()
    return [c for c in out if at_war(world, u.owner, c.owner) and (not c.hidden or _detected(c, detectors))]


def flee_cell(world, u, near):
    """`FUN_00558b92(u, mean position of the hostiles, 3)`: 3 cells beyond u on the ray from their centre through u, along the dominant
    axis (float32 slope), clamped to the playable area."""
    n = len(near)
    px = sum(pos16(c)[0] for c in near) // n
    py = sum(pos16(c)[1] for c in near) // n
    return away_cell(world, u, px, py, FLEE_CELLS)


def away_cell(world, u, px, py, cells):
    """`FUN_00558b92(u, point (px, py) in 1/256 cell, cells)`: `cells` cells beyond u on the ray from the point through u, along the dominant
    axis (float32 slope), clamped to the playable area (the wimpy / withdraw step and the follower that stands too close, ai.md 14.2)."""
    ux, uy = pos16(u)
    dx, dy = ux - px, uy - py
    dx, dy = dx or 1, dy or 1
    f32 = lambda v: struct.unpack("<f", struct.pack("<f", v))[0]       # noqa: E731
    if abs(dx) > abs(dy):
        s = f32(dy / dx)
        b = f32(uy - ux * s)
        nx = ux + cells * 256 if dx > 0 else ux - cells * 256
        ny = int(nx * s + b)
    else:
        s = f32(dx / dy)
        b = f32(ux - uy * s)
        ny = uy + cells * 256 if dy > 0 else uy - cells * 256
        nx = int(ny * s + b)
    nx, ny = nx >> 8, ny >> 8
    nx = min(max(nx, 8), world.width - 9)
    ny = min(max(ny, 8), world.height - 9)
    return word(nx, ny)


def post_step(world, g, m):
    """`FUN_00573713`, after the handler for each member: the wimpy test (hostile within 10), else the withdraw test (within 2)."""
    if m.hp <= 0:
        return
    if m.wimpy_hp is not None:                                                     # the retreat mode message rewrote both (0x4f67d5)
        wimpy, withdraw = m.wimpy_hp, m.withdraw_hp
    elif m.stats is None:
        return
    else:
        wimpy, withdraw = int(m.stats.get("wimpy", 0) or 0), int(m.stats.get("withdraw", 0) or 0)
        if m.tweak == 1:
            wimpy >>= 1                                                            # easy mode halves brain+0x44 at load (0x561e96)
    if wimpy <= 0 and withdraw <= 0:                                               # HP > 0 never reaches a threshold of 0
        return
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


def retreat_exec(world, u):
    """`FUN_0056c9bc`, the executor of order 0x16 (the R key) in the group pass of order 0: the hostiles within `mover+8 + 5` = 10 cells; none alive
    -> the guard scan; else Brain mode 1 towards the flee cell 3 beyond the unit (the order stays 0x16, so it repeats at every pass).  A unit that can
    cast Teleport takes `FUN_0056cb8c` in the exe: not built (no shipped unit knows it), it flees on foot."""
    near = [c for c in _enemies(world, u, WIMPY_RADIUS) if c.hp > 0]
    if not near:
        if world.ai_on:
            guard_scan(world, u)
        return
    go(world, u, flee_cell(world, u, near))
