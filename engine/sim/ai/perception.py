"""perception: part of the monster AI (docs/engine/ai.md); see the package docstring in __init__."""

import math
from .. import combat as cb, combatstats, effects
from ..pathfinding import chebyshev, unit_size



WANDER_DX = (0, 1, 1, 1, 0, -1, -1, -1)     # pf+0x58e88 / pf+0x58e90: the 8 directions, 0 = up, clockwise (0x553e4e..0x553eeb)


WANDER_DY = (-1, -1, 0, 1, 1, 1, 0, -1)


SCAN_SHIFT = 7                      # registry Scanning\ScanShift (the install's value; default 7)


MARK_TURNS = 20                     # the attacker's cell stays revealed while mark_age <= 20


NO_TARGET = 0xFFFFFF


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


def _scan_range(u, world=None):
    """The scan byte `+0xa5`: a human's recompute (high byte of `combatstats.human_sight_word`, needs `world` for the lazily built stats);
    else the template's scan range plus the effects' changes (Light, Darkness), wrapped to a byte (docs/engine/effects.md 2.1)."""
    if world is not None and u.human:
        st = cb.combat_stats(world, u)
        if st.attrs is not None:
            return combatstats.human_sight_word(u, st) >> 8
    base = int(u.stats.get("scan_range", 0) or 0) if u.stats is not None else 0
    return effects.scan_range(u, base) if (u.fx.scan or u.fx.scan_direct) else base


def _visible(world, observers):
    """`FUN_00571c4d` steps 1-2: the union of the observers' sight, plus the attacker cells their hit marks reveal (the mark ages)."""
    vis = set()
    for m in observers:
        vis |= sight(world, m.x, m.y, _scan_range(m, world))
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


def centroid_stats(world, g, mem=None, fine=False):
    """`FUN_0056fa63` / `FUN_0056f850`: mean cell, widest member distance, and reach (distance + scan range) of the members (`mem`, default the
    living-or-dying members of `g`); stored on `g`, `mem` returned (None when empty).  The centre is the integer mean of the cells, or with
    `fine` (`FUN_0056f850`, the squad set-up) the mean of the 16-bit positions `>> 8`."""
    if mem is None:
        mem = [world.units[i] for i in g.members if i in world.units]
    n = len(mem)
    if not n:
        return None
    if fine:
        cx, cy = (sum(pos16(u)[0] for u in mem) // n) >> 8 & 0xFF, (sum(pos16(u)[1] for u in mem) // n) >> 8 & 0xFF
    else:
        cx, cy = sum(u.x for u in mem) // n, sum(u.y for u in mem) // n
    g.centre = word(cx, cy)
    g.spread = max(chebyshev((u.x, u.y), (cx, cy)) for u in mem)
    g.reach = max(chebyshev((u.x, u.y), (cx, cy)) + _scan_range(u, world) for u in mem)
    return mem
