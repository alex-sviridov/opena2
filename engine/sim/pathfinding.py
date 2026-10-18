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


def _wave(grid, start, target, size, walker, limit, order, cost):
    """The wave fill.  Returns (field array('H'), searched cells in labelling order, levels run)."""
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
    return fld, searched, it


def _walk_back(fld, cost, start, end, walker_cost):
    """FUN_0054e58c / FUN_0054e886: from `end` back to `start` along the smallest label; returns the cells
    from the first step to `end`, or None when the walk exceeds MAX_STEPS."""
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
            v = fld[ny * GRID + nx]
            if v == UNSEEN:
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


def _nearest_reached(fld, target, radius):
    """FUN_005585f4: scan rings r = 1 .. radius - 1 around `target` for the labelled cell with the
    smallest label (first in scan order on ties); the first ring that has one decides.  Packed 16-bit
    index arithmetic as in the exe.  None when no ring cell is labelled."""
    t = (target[1] << 8) + target[0]
    best, found = UNSEEN, None
    for r in range(1, radius):
        for o in range(-r, r + 1):
            for idx in ((r << 8) + t + o, (-r << 8) + t + o, (o << 8) + t + r, (o << 8) + t - r):
                idx &= 0xFFFF
                if fld[idx] < best:
                    best, found = fld[idx], idx
        if best < UNSEEN:
            break
    return None if found is None else (found & 255, found >> 8)


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
    fld, searched, levels = _wave(grid, start, target, size, walker, limit, order, cost)
    res.searched = [(i & 255, i >> 8) for i in searched]
    res.limit, res.levels = limit, levels
    end = target
    if fld[target[1] * GRID + target[0]] == UNSEEN:
        end = _nearest_reached(fld, target, radius if radius is not None else (quarter + 4 if static else 8))
        if end is None:
            res.reason = "unreachable"
            return res
        res.reason = "fallback"
    else:
        res.found, res.reason = True, "found"
    route = _walk_back(fld, grid.cost, start, end, cost is not None)
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
