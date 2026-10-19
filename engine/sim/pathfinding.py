"""Path planners of the original game: pure functions over a passability grid.

Spec: docs/engine/simulation.md section 7 (exe routines, tie-breaking, limits, quirks).  Layer 4, no
pygame, no world mutation: a `PathGrid` goes in, a `PathResult` comes out.

The search is the exe's, not A*: a label-correcting wave fill over a distance field (`FUN_0054d76e`
with the expanders `FUN_0055d010` / `FUN_0055c6f0` / `FUN_0055e050` / `FUN_0055cb30`), then a
backward walk from the end cell (`FUN_0054e58c` / `FUN_0054e886`).  Cells are indexed `y * 256 + x`
as in the exe's 256 x 256 grids; the 8-cell map border is blocked, so a plan never leaves the map.
"""

from array import array
from dataclasses import dataclass, field
from typing import NamedTuple

import numpy as np

GRID = 256
UNSEEN = 0xFFFF
MAX_STEPS = 1000                # backward walk limit (FUN_0054e58c: more than 1000 steps drops the plan)
UNLIMITED = 1000                # search limit of a human unit going to a free target (FUN_0054d76e)

# Neighbour orders (dx, dy).  Size-1 expanders list the diagonals first (FUN_0055d010 order of the
# index deltas -0x101, -0xff, +0xff, +0x101, -0x100, -1, +1, +0x100); sized expanders loop x outer,
# y inner (FUN_0055c6f0).
ORDER_SIZE1 = ((-1, -1), (1, -1), (-1, 1), (1, 1), (0, -1), (-1, 0), (1, 0), (0, 1))
ORDER_SIZED = tuple((dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
# Backward-walk scan: dx outer, dy inner, self included (FUN_0054e58c).
ORDER_WALK = ORDER_SIZED


@dataclass(frozen=True)
class PathConfig:
    """map.reg `[Path Finding]` (constructor 0x5543d9..0x5545d6; the defaults are the shipped values)."""
    static_scan_ahead: int = 5          # +0x58584
    dynamic_scan_ahead: int = 3         # +0x58588
    static_refresh_rate: int = 16       # +0x5858c  waypoints consumed before a static re-plan
    dynamic_refresh_rate: int = 32      # +0x58590  ticks between hop re-plans
    dynamic_by_static_lookup: int = 3   # +0x58594
    static_isnt_needed: int = 5         # +0x58598


DEFAULT_CONFIG = PathConfig()


class PathGrid:
    """Flat 256 x 256 views of the layers a plan reads.

    `blocked`: bytearray, non-zero = the mover may not enter (the layer already masked with the mover
    byte).  `cost`: bytearray of terrain costs for walkers, or None (costs 2 / 3 apply).  Cells outside
    the map are blocked.  Build with `PathGrid.from_arrays`."""

    __slots__ = ("blocked", "cost", "width", "height")

    def __init__(self, blocked, cost, width, height):
        self.blocked, self.cost, self.width, self.height = blocked, cost, width, height

    @classmethod
    def from_arrays(cls, blocked, cost=None):
        """`blocked`: (h, w) bool/uint8 array (True/non-zero = blocked); `cost`: (h, w) uint8 or None."""
        blocked = np.asarray(blocked)
        h, w = blocked.shape
        if h > GRID or w > GRID:
            raise ValueError("map larger than the 256 x 256 path-finder grid")
        flat = np.ones((GRID, GRID), np.uint8)
        flat[:h, :w] = (blocked != 0)
        cflat = None
        if cost is not None:
            c = np.zeros((GRID, GRID), np.uint8)
            c[:h, :w] = np.asarray(cost)
            cflat = bytearray(c.tobytes())
        return cls(bytearray(flat.tobytes()), cflat, w, h)

    def with_blocked(self, cells):
        """A grid with `cells` ((x, y) pairs) also blocked (the live layer: units stamped over the static one)."""
        b = bytearray(self.blocked)
        for x, y in cells:
            if 0 <= x < GRID and 0 <= y < GRID:
                b[y * GRID + x] = 1
        return PathGrid(b, self.cost, self.width, self.height)

    def is_blocked(self, x, y):
        return not (0 <= x < GRID and 0 <= y < GRID) or bool(self.blocked[y * GRID + x])


@dataclass
class PathResult:
    """`cells`: the route, first step ... end cell (start excluded; empty when nothing to walk).
    `found`: the target itself was labelled.  `end`: the cell the route ends at (the target, or the
    fallback cell; None when there is none).  `searched`: cells that received a label, in the order
    they were first labelled (debug overlay).  `limit`: the level limit the search ran with."""
    cells: list = field(default_factory=list)
    found: bool = False
    end: tuple = None
    limit: int = 0
    levels: int = 0
    reason: str = ""
    _searched: list = field(default_factory=list, repr=False, compare=False)
    _raw: list = field(default=None, repr=False, compare=False)       # cell indices, mapped to (x, y) on first use

    @property
    def searched(self):
        if self._raw is not None:                           # debug overlay only: not paid for by the planner
            self._searched = list(map(_xy_table().__getitem__, self._raw))
            self._raw = None
        return self._searched

    @searched.setter
    def searched(self, v):
        self._searched, self._raw = v, None


def chebyshev(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _footprint_free(blocked, x, y, size):
    """FUN_0055c440: every cell of the size x size footprint with top-left (x, y) is free."""
    if not (0 <= x and 0 <= y and x + size <= GRID and y + size <= GRID):
        return False
    for j in range(size):
        row = (y + j) * GRID + x
        for i in range(size):
            if blocked[row + i]:
                return False
    return True


_TEMPLATES = []                 # last few (blocked bytes, size, dead bytes, field template): grids repeat across plans
_DIAG = []                      # last (cost bytes, k + (k >> 1) list)


def _dead_cells(blocked, size):
    """Cells a label can never land on: blocked (size 1) or whose size x size footprint is not free
    (FUN_0055c440, out of the 256 x 256 grid counts as blocked)."""
    key = bytes(blocked)
    for k, sz, dead, tmpl in _TEMPLATES:
        if sz == size and k == key:
            return dead, tmpl
    free = (np.frombuffer(key, np.uint8) == 0).reshape(GRID, GRID)
    if size > 1:
        ok = np.zeros_like(free)
        m = GRID - size + 1
        acc = free[:m, :m].copy()
        for j in range(size):
            for i in range(size):
                if i or j:
                    acc &= free[j:j + m, i:i + m]
        ok[:m, :m] = acc
        free = ok
    dead = (~free).astype(np.uint8).tobytes()
    tmpl = np.where(free, UNSEEN, 0).astype(np.uint16).ravel().tolist()
    _TEMPLATES.insert(0, (key, size, dead, tmpl))
    del _TEMPLATES[4:]
    return dead, tmpl


def _diag_costs(cost):
    for k, d in _DIAG:
        if k == cost:
            return d
    c = np.frombuffer(bytes(cost), np.uint8).astype(np.uint16)
    d = (c + (c >> 1)).tolist()
    _DIAG[:] = [(bytes(cost), d)]
    return d


_EXPANDERS = {}


def _expander(order, use_cost):
    """Source-generated half-step for one neighbour order: the 8 neighbours unrolled with literal deltas
    (no tuple unpacking or table lookups per neighbour).  Semantics of the loops in `_wave` exactly."""
    key = (order, use_cost)
    fn = _EXPANDERS.get(key)
    if fn is not None:
        return fn
    body = []
    for dx, dy in order:
        d = dy * GRID + dx
        straight = dx == 0 or dy == 0
        step = ("cost[n]" if straight else "diag[n]") if use_cost else ("2" if straight else "3")
        body.append("n = c + %d\nif cur + %s < fld[n]:\n"
                    "    if fld[n] == 65535:\n        sappend(n)\n    fld[n] = cur + %s\n    nappend(n)\n" % (d, step, step))
    slow = []
    for dx, dy in order:
        d = dy * GRID + dx
        straight = dx == 0 or dy == 0
        step = ("cost[n]" if straight else "diag[n]") if use_cost else ("2" if straight else "3")
        slow.append("n = (c + %d) & 0xFFFF\nnew = (cur + %s) & 0xFFFF\nold = fld[n]\nif new < old:\n"
                    "    if old == 65535:\n        sappend(n)\n    fld[n] = new\n    nappend(n)\n" % (d, step))
    ind = lambda blocks, n: "".join(" " * n + line + "\n" for b in blocks for line in b.rstrip("\n").split("\n"))
    src = ("def expand(frontier, fld, cost, diag, sappend, last):\n"
           " nxt = []\n nappend = nxt.append\n"
           " for c in frontier:\n  cur = fld[c]\n"
           "  if last[c] == cur:\n   continue\n  last[c] = cur\n"
           "  if cur > 0xF000 or c < 257 or c > 65278:\n" + ind(slow, 3) +
           "  else:\n" + ind(body, 3) + " return nxt\n")
    ns = {}
    exec(src, ns)
    fn = _EXPANDERS[key] = ns["expand"]
    return fn


def _wave_ref(grid, start, target, size, walker, limit, order, cost):
    """The plain sequential wave fill (kept for starts on the last rows/columns with sized movers)."""
    fld = array("H", b"\xff\xff" * (GRID * GRID))
    blocked = grid.blocked
    sidx, tidx = start[1] * GRID + start[0], target[1] * GRID + target[0]
    fld[sidx] = 0
    searched = [sidx]
    use_cost = cost is not None
    offs = [(dx, dy, dy * GRID + dx, dx == 0 or dy == 0) for dx, dy in order]
    sized = size > 1
    frontier, it = [sidx], 0
    while fld[tidx] == UNSEEN and frontier and it < limit:
        for _ in range(2):                                  # half step A -> B, then B -> A
            nxt = []
            for c in frontier:
                cur, cx, cy = fld[c], c & 255, c >> 8
                for dx, dy, delta, straight in offs:
                    n = (c + delta) & 0xFFFF
                    if sized:
                        if not _footprint_free(blocked, cx + dx, cy + dy, size):
                            continue
                    elif blocked[n]:
                        continue
                    if use_cost:
                        k = cost[n]
                        step = k if straight else k + (k >> 1)
                    else:
                        step = 2 if straight else 3
                    new = (cur + step) & 0xFFFF
                    if new < fld[n]:
                        if fld[n] == UNSEEN:
                            searched.append(n)
                        fld[n] = new
                        nxt.append(n)
            frontier = nxt
        it += 2
    return fld, searched, it, None


def _wave(grid, start, target, size, walker, limit, order, cost):
    """The wave fill.  Returns (field, searched cells in labelling order, levels run, dead).

    Same label-correcting order as the exe: cells are expanded one by one in frontier order and read their
    label at expansion time.  Cells that can never be labelled (blocked, or footprint not free) hold 0 in
    the working field, so the strict `<` rejects them without a test; `dead` (bytes, 1 = such a cell) lets
    the callers read them as unlabelled."""
    sidx, tidx = start[1] * GRID + start[0], target[1] * GRID + target[0]
    if size > 1 and (start[0] + size > GRID or start[1] + size > GRID):
        return _wave_ref(grid, start, target, size, walker, limit, order, cost)
    dead, tmpl = _dead_cells(grid.blocked, size)
    fld = tmpl[:]
    fld[sidx] = 0
    tdead = bool(dead[tidx]) and tidx != sidx
    searched = [sidx]
    sappend = searched.append
    diag = None if cost is None else _diag_costs(cost)
    expand = _expander(tuple(order), cost is not None)
    last = [-1] * (GRID * GRID)         # label a cell was last expanded with: expanding it again is a no-op
    frontier, it = [sidx], 0
    while frontier and it < limit and (tdead or fld[tidx] == UNSEEN):
        frontier = expand(frontier, fld, cost, diag, sappend, last)      # half step A -> B
        frontier = expand(frontier, fld, cost, diag, sappend, last)      # then B -> A
        it += 2
    return fld, searched, it, dead


def _walk_back(fld, cost, start, end, walker_cost, dead=None):
    """FUN_0054e58c / FUN_0054e886: from `end` back to `start` along the smallest label; returns the cells
    from the first step to `end`, or None when the walk exceeds MAX_STEPS."""
    sidx = start[1] * GRID + start[0]
    cx, cy = end
    out = [end]
    steps = 0
    while (cx, cy) != start:
        steps += 1
        if steps > MAX_STEPS:
            return None
        best, pick = UNSEEN, (0, 0)
        c = cy * GRID + cx
        for dx, dy in ORDER_WALK:
            nx, ny = cx + dx, cy + dy
            if not (8 <= nx <= GRID - 8 and 8 <= ny <= GRID - 8):
                continue
            i = ny * GRID + nx
            v = fld[i]
            if v == UNSEEN or (dead is not None and dead[i] and i != sidx):
                continue
            if dx == 0 or dy == 0:
                cand = (v + (cost[c] if walker_cost else 2)) & 0xFFFF
                if cand <= best:
                    best, pick = cand, (dx, dy)
            else:
                k = cost[c] if walker_cost else 0
                cand = (v + (k + (k >> 1) if walker_cost else 3)) & 0xFFFF
                if cand < best:
                    best, pick = cand, (dx, dy)
        cx, cy = cx + pick[0], cy + pick[1]
        out.append((cx, cy))
    out.reverse()
    return out[1:]                                          # the start cell is pushed last and popped


def _nearest_reached(fld, target, radius, dead=None, sidx=-1):
    """FUN_005585f4: scan rings r = 1 .. radius - 1 around `target` for the labelled cell with the
    smallest label (first in scan order on ties); the first ring that has one decides.  Packed 16-bit
    index arithmetic as in the exe.  None when no ring cell is labelled."""
    t = (target[1] << 8) + target[0]
    best, found = UNSEEN, None
    for r in range(1, radius):
        for o in range(-r, r + 1):
            for idx in ((r << 8) + t + o, (-r << 8) + t + o, (o << 8) + t + r, (o << 8) + t - r):
                idx &= 0xFFFF
                if fld[idx] < best and not (dead is not None and dead[idx] and idx != sidx):
                    best, found = fld[idx], idx
        if best < UNSEEN:
            break
    return None if found is None else (found & 255, found >> 8)


_XY = []


def _xy_table():
    """(x, y) tuple of every cell index, built once (the searched list is mapped through it)."""
    if not _XY:
        _XY.extend(zip(list(range(GRID)) * GRID, [y for y in range(GRID) for _ in range(GRID)]))
    return _XY


# ---------------------------------------------------------------------------------------------
# Follow-target fallback (FUN_00557f08): spec docs/engine/simulation.md section 7.4 / 9.

class Foot(NamedTuple):
    """What the follow routines read of a unit: `FUN_0054ffb0/c0` cell (x, y), the token size (vtable
    `+0x1c`), and the mover's sub-cell offsets (`mover+4/+5`, 0x80 = cell centre)."""
    x: int
    y: int
    size: int = 1
    sx: int = 128
    sy: int = 128


# Direction table at pathfinder +0x54156 (constructor 0x5543e7): (dx, dy) = E, S, W, N repeated 3 times.
FOLLOW_DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1)) * 3
FOLLOW_ATTEMPTS = 8             # box growths tried (0x557f1d.. `cmp [ebp-0x44], 8`)
FOLLOW_RING_CAP = 100           # walk iterations stop after step 0x64 (0x5584ee)


def unit_size(u):
    """Footprint side in cells of an engine `Unit`: token size (+0x49, vtable +0x1c `0x542360`, CONFIRMED)."""
    return max(1, int(getattr(u.stats, "token_size", 1) or 1)) if u.stats is not None else 1


def foot(u):
    """The `Foot` of an engine `Unit` (cell, token size, sub-cell offsets)."""
    return Foot(u.x, u.y, unit_size(u), u.sub_x, u.sub_y)


def centre_x(u):
    """FUN_0050d884: footprint centre x in 1/256 cells, 16-bit: cell * 256 + sub + (size - 1) * 128."""
    return (((u.x << 8) + u.sx) + ((u.size - 1) << 7)) & 0xFFFF


def centre_y(u):
    """FUN_0050d8c0: the same for y."""
    return (((u.y << 8) + u.sy) + ((u.size - 1) << 7)) & 0xFFFF


def follow_distance(a, b):
    """FUN_00556dcd(a, b): gap between the footprint centres less the half sizes, Chebyshev, in whole
    cells, plus 1 (touching = 1).  Each axis: |dpos| - (size_a + size_b) * 128, floored at 0; the larger
    axis is divided by 256 truncating toward zero and incremented.  Returns a byte."""
    half = (a.size + b.size) << 7
    dx = max(abs(centre_x(a) - centre_x(b)) - half, 0)
    dy = max(abs(centre_y(a) - centre_y(b)) - half, 0)
    v = max(dx, dy)
    return ((v >> 8) + 1) & 0xFF


def follow_compass(target, follower):
    """FUN_00557cf1(target, follower): 16-way compass code of the follower as seen from the target, from
    `d = centre(follower) - centre(target)`: 0 north (just east of north), 3/4 east, 7/8 south, 11/12
    west, 15 north (just west).  Within a half-plane the axis ratio splits at 2:1 and 1:1.

    Quadrants (a = |dx|, b = |dy|, as 16-bit values): dx > 0, dy > 0: a > b ? (a > 2b ? 4 : 5) :
    (b > 2a ? 7 : 6); dx > 0, dy <= 0: a > b ? (a > 2b ? 3 : 2) : (b > 2a ? 0 : 1); dx <= 0, dy > 0:
    a > b ? (a > 2b ? 11 : 10) : (b > 2a ? 8 : 9); dx <= 0, dy <= 0: a > b ? (a > 2b ? 12 : 13) :
    (b > 2a ? 15 : 14)."""
    dx = centre_x(follower) - centre_x(target)
    dy = centre_y(follower) - centre_y(target)
    a = (dx if dx > 0 else -dx) & 0xFFFF
    b = (dy if dy > 0 else -dy) & 0xFFFF
    if dx > 0:
        if dy > 0:
            return (4 if a > 2 * b else 5) if a > b else (7 if b > 2 * a else 6)
        return (3 if a > 2 * b else 2) if a > b else (0 if b > 2 * a else 1)
    if dy > 0:
        return (11 if a > 2 * b else 10) if a > b else (8 if b > 2 * a else 9)
    return (12 if a > 2 * b else 13) if a > b else (15 if b > 2 * a else 14)


def _ftol(v):
    """FUN_00582c0c: FISTP with truncation, low dword; NaN / inf give the 'integer indefinite' (low dword 0)."""
    if v != v or v in (float("inf"), float("-inf")):
        return 0
    return int(v)


def _f32(v):
    return float(np.float32(v))


def follow_fallback(fld, follower, target, dead=None, sidx=-1):
    """FUN_00557f08(follower, target): the cell to walk to when the dynamic wave did not label the goal and
    the plan has a unit target.  Returns `(x, y)` or None (the exe returns 0).

    `fld`: label field (flat 65536 list, UNSEEN = unlabelled); `dead`/`sidx` as in `_nearest_reached` (cells
    the working field holds as 0 but the exe leaves unlabelled).  Algorithm (all CONFIRMED, 0x557f08):

    1. side = ((compass(target, follower) + 2) & 12) >> 2) + 4 : 4 north, 5 east, 6 south, 7 west.
    2. line through the two centres, fx/fy = centre(target) - centre(follower) as float32:
       side 5/7: fx += 1.0 if fx == 0; s = f32(fy / fx); b = trunc(Ty - Tx * s)  (line y = s x + b);
       side 4/6: s = f32(fx / fy) (no zero guard); b = trunc(Tx - Ty * s)       (line x = s y + b).
       T* = centre of the target.
    3. box (cells, top-left of the follower's footprint): x0 = Tx - follower.size, y0 = Ty - follower.size,
       x1 = Tx + target.size, y1 = Ty + target.size (cell coordinates).  Up to 8 attempts, growing the box
       by one cell on every side after each attempt, until a labelled cell was seen.
    4. entry point on the box edge of `side` (4: row y0, 5: column x1, 6: row y1, 7: column x0): the line is
       evaluated at the edge's cell centre ((edge << 8) + 0x80), truncated, then arithmetic >> 8.
    5. two walkers start there and walk `n = (x1 - x0) + (y1 - y0) + 1` steps; walker 1 forward with direction
       index p (E, S, W, N pattern, p starts at side), walker 2 backwards (q starts at side, steps by
       -dir[q]).  Each step: read the label of both walkers (walker 1 first); a label strictly below the best so
       far replaces it (first wins ties).  Then the corner test, then the move:
       walker 1: idx p%4 0: x == x1, 1: y == y1, 2: x == x0, 3: y == y0 -> p += 1; move by dir[p].
       walker 2: idx q%4 0: x == x0, 1: y == y0, 2: x == x1, 3: y == y1 -> q -= 1; move by -dir[q].
       (the walk stops after step 100.)  Coordinates are 16-bit; label lookups use the low bytes.
    6. result `(y << 8) + x` of the best cell, 0 when nothing was labelled after 8 attempts.
    """
    code = follow_compass(target, follower)
    side = (((code + 2) & 0xC) >> 2) + 4
    tx, ty = centre_x(target), centre_y(target)
    fx = _f32(tx - centre_x(follower))
    fy = _f32(ty - centre_y(follower))
    with np.errstate(all="ignore"):
        if side in (5, 7):
            if fx == 0.0:
                fx = _f32(fx + 1.0)
            s = float(np.float32(fy) / np.float32(fx))
            b = _ftol(float(_f32(ty)) - tx * s)
        else:
            s = float(np.float32(fx) / np.float32(fy))
            b = _ftol(float(_f32(tx)) - ty * s)
    x0, y0 = target.x - follower.size, target.y - follower.size
    x1, y1 = target.x + target.size, target.y + target.size

    def label(x, y):
        idx = ((y & 255) << 8) + (x & 255)
        if dead is not None and dead[idx] and idx != sidx:
            return UNSEEN
        return fld[idx]

    best, bx, by = UNSEEN, 0, 0
    attempt = 0
    while best == UNSEEN and attempt < FOLLOW_ATTEMPTS:
        attempt += 1
        with np.errstate(all="ignore"):
            if side == 4:
                py = y0; px = _ftol(((y0 << 8) + 0x80) * s + b) >> 8
            elif side == 5:
                px = x1; py = _ftol(((x1 << 8) + 0x80) * s + b) >> 8
            elif side == 6:
                py = y1; px = _ftol(((y1 << 8) + 0x80) * s + b) >> 8
            else:
                px = x0; py = _ftol(((x0 << 8) + 0x80) * s + b) >> 8
        p = q = side
        ax, ay = px & 0xFFFF, py & 0xFFFF
        bx2, by2 = ax, ay
        n = (x1 - x0) + (y1 - y0) + 1
        for i in range(n):
            v = label(ax, ay)
            if v < best:
                best, bx, by = v, ax, ay
            v = label(bx2, by2)
            if v < best:
                best, bx, by = v, bx2, by2
            if p <= 0xB:
                m = p & 3
                if (m == 0 and ax == x1) or (m == 1 and ay == y1) or (m == 2 and ax == x0) or (m == 3 and ay == y0):
                    p += 1
            ax = (ax + FOLLOW_DIRS[p][0]) & 0xFFFF
            ay = (ay + FOLLOW_DIRS[p][1]) & 0xFFFF
            if 0 <= q <= 0xB:
                m = q & 3
                if (m == 0 and bx2 == x0) or (m == 1 and by2 == y0) or (m == 2 and bx2 == x1) or (m == 3 and by2 == y1):
                    q -= 1
            bx2 = (bx2 - FOLLOW_DIRS[q][0]) & 0xFFFF
            by2 = (by2 - FOLLOW_DIRS[q][1]) & 0xFFFF
            if i > FOLLOW_RING_CAP:
                break
        x0 -= 1; y0 -= 1; x1 += 1; y1 += 1
    if best == UNSEEN:
        return None
    res = ((by << 8) + bx) & 0xFFFF
    return None if res == 0 else (res & 255, res >> 8)


def _plan(grid, start, target, size, walker, human, static, cfg, radius, follow=None):
    res = PathResult()
    if start == target:
        res.reason = "at target"
        return res
    dist = chebyshev(start, target)
    quarter = dist >> 2
    if size == 1:
        slack = cfg.static_scan_ahead if static else cfg.dynamic_scan_ahead
        limit = dist + min(slack, quarter)
        if static and human and _footprint_free(grid.blocked, target[0], target[1], 1):
            limit = UNLIMITED
        order = ORDER_SIZE1
    else:
        limit = dist + (cfg.static_scan_ahead if static else cfg.dynamic_scan_ahead)
        order = ORDER_SIZED
    cost = grid.cost if (walker and grid.cost is not None) else None
    fld, searched, levels, dead = _wave(grid, start, target, size, walker, limit, order, cost)
    res._raw = searched
    res.limit, res.levels = limit, levels
    end = target
    tidx, sidx = target[1] * GRID + target[0], start[1] * GRID + start[0]
    if fld[tidx] == UNSEEN or (dead is not None and dead[tidx] and tidx != sidx):
        if follow is not None:                              # 0x54e30f: a unit target, FUN_00557f08
            end = follow_fallback(fld, follow[0], follow[1], dead, sidx)
        else:
            end = _nearest_reached(fld, target, radius if radius is not None else (quarter + 4 if static else 8),
                                   dead, sidx)
        if end is None:
            res.reason = "unreachable"
            return res
        res.reason = "fallback"
    else:
        res.found, res.reason = True, "found"
    route = _walk_back(fld, grid.cost, start, end, cost is not None, dead)
    if route is None:
        res.found, res.reason = False, "too long"
        return res
    res.cells, res.end = route, end
    return res


# --- Range clause of the static fallback (FUN_0054d76e 0x54e245..0x54e2c1), spec simulation.md 7.1 ------------
GROUP_ORDER_GUARD = 0x12        # group record +0x20 set by FUN_00570aba (computer players' groups after load)
BRAIN_MODE_ATTACK = 5           # brain +8 = 5: order 3 attack, approach/swing (FUN_0056eab5)


def footprint_gap(here, target, size):
    """`FUN_00556f56` (CONFIRMED): cells between a `size` x `size` footprint anchored at `here` and the cell
    `target`: per axis, `max(0, t - h - size + 1)` when the target is after the anchor, else `h - t`; the larger
    axis (a Chebyshev gap, asymmetric: only the far side counts the footprint)."""
    def axis(h, t):
        return max(0, t - h - size + 1) if h < t else h - t
    return max(axis(here[0], target[0]), axis(here[1], target[1]))


def default_range(creature_range, spell_range=None, mana=0, spell_cost=0):
    """`FUN_0056ac5b` (CONFIRMED): the selected special's range (spell record +9) when the brain's special slot
    (+0x78) names a spell that is in the spellbook and `mana >= cost` (signed words, `JL`), else the creature's
    byte +0x12c.  `spell_range=None`: no special selected / not found.  Structures are not special-cased here."""
    if spell_range is not None and mana >= spell_cost:
        return spell_range & 0xFF
    return creature_range & 0xFF


def fallback_stamp(group_order, brain_mode, here, target, size, range_, tick):
    """The class-0x12 / order-5 clause: after an unreachable static plan took a fallback cell `here` (packed 0 =
    cell (0, 0) when none), a unit whose group order is 0x12 and whose brain mode is 5 stamps `brain+0x16 :=
    tick & 0xFFFF` when the footprint gap exceeds its default range; otherwise None (nothing written).  Reads
    only; it changes no route.  Not wired: the engine has no group orders or attack modes (phase I)."""
    if group_order == GROUP_ORDER_GUARD and brain_mode == BRAIN_MODE_ATTACK \
            and footprint_gap(here, target, size) > range_ & 0xFF:
        return tick & 0xFFFF
    return None


def plan_static(grid, start, target, *, size=1, walker=True, human=False, cfg=DEFAULT_CONFIG):
    """The long plan (`FUN_0054d76e` with mode != 0): ignores units.  `human`: the unit's owner is the human
    player (owner `+0x2c` == 0), whose search is unbounded when the target cell is free.  Returns a PathResult
    whose `cells` start at the first step."""
    return _plan(grid, tuple(start), tuple(target), size, walker, human, True, cfg, None)


def plan_dynamic(grid, start, target, *, size=1, walker=True, cfg=DEFAULT_CONFIG, radius=None, follow=None):
    """The short hop plan (`FUN_0054d76e` with mode 0) over the live layer `grid` (units stamped as blocked,
    the planner's own footprint not).  `follow=(follower Foot, target Foot)`: the hop plan of a follow driver
    (`FUN_00555dc2(unit, target unit)`, 7.4): when the hop goal stays unlabelled the end cell is
    `follow_fallback` around the target unit (not around `target`), instead of the ring scan."""
    return _plan(grid, tuple(start), tuple(target), size, walker, False, False, cfg, radius, follow)
