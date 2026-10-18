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
    searched: list = field(default_factory=list)
    limit: int = 0
    levels: int = 0
    reason: str = ""


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
        body.append("n = c + %d\nnew = cur + %s\nold = fld[n]\nif new < old:\n"
                    "    if old == 65535:\n        sappend(n)\n    fld[n] = new\n    nappend(n)\n" % (d, step))
    slow = []
    for dx, dy in order:
        d = dy * GRID + dx
        straight = dx == 0 or dy == 0
        step = ("cost[n]" if straight else "diag[n]") if use_cost else ("2" if straight else "3")
        slow.append("n = (c + %d) & 0xFFFF\nnew = (cur + %s) & 0xFFFF\nold = fld[n]\nif new < old:\n"
                    "    if old == 65535:\n        sappend(n)\n    fld[n] = new\n    nappend(n)\n" % (d, step))
    ind = lambda blocks, n: "".join(" " * n + line + "\n" for b in blocks for line in b.rstrip("\n").split("\n"))
    src = ("def expand(frontier, fld, cost, diag, sappend):\n"
           " nxt = []\n nappend = nxt.append\n"
           " for c in frontier:\n  cur = fld[c]\n"
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
    frontier, it = [sidx], 0
    while frontier and it < limit and (tdead or fld[tidx] == UNSEEN):
        frontier = expand(frontier, fld, cost, diag, sappend)      # half step A -> B
        frontier = expand(frontier, fld, cost, diag, sappend)      # then B -> A
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


def _plan(grid, start, target, size, walker, human, static, cfg, radius):
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
    res.searched = list(map(_xy_table().__getitem__, searched))
    res.limit, res.levels = limit, levels
    end = target
    tidx, sidx = target[1] * GRID + target[0], start[1] * GRID + start[0]
    if fld[tidx] == UNSEEN or (dead is not None and dead[tidx] and tidx != sidx):
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


def plan_static(grid, start, target, *, size=1, walker=True, human=False, cfg=DEFAULT_CONFIG):
    """The long plan (`FUN_0054d76e` with mode != 0): ignores units.  `human`: the unit's owner is the human
    player (owner `+0x2c` == 0), whose search is unbounded when the target cell is free.  Returns a PathResult
    whose `cells` start at the first step."""
    return _plan(grid, tuple(start), tuple(target), size, walker, human, True, cfg, None)


def plan_dynamic(grid, start, target, *, size=1, walker=True, cfg=DEFAULT_CONFIG, radius=None):
    """The short hop plan (`FUN_0054d76e` with mode 0) over the live layer `grid` (units stamped as blocked,
    the planner's own footprint not)."""
    return _plan(grid, tuple(start), tuple(target), size, walker, False, False, cfg, radius)
