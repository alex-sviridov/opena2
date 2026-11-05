"""Player-side fog of war: the client's sight mask and the tile-bit helpers (docs/engine/vision.md).

Pure, integer arithmetic after the tables; numpy only for the tile-word array.  Tile words keep the exe's bits: `SEEN` 0x4000 (seen at the last
refresh), `EXPLORED` 0x8000 (never cleared), both = in sight.
"""

import math

import numpy as np

SEEN, EXPLORED = 0x4000, 0x8000
IN_SIGHT = SEEN | EXPLORED
SCAN_SHIFT = 7                  # `view+0x3f50`; 1 << 7 = 128 per straight step
RINGS = 19                      # rings 1..19 of the 41 x 41 window
BORDER = 7                      # cells `7 <= x < w - 7` (the server flood uses 8)


def _tables():
    """`FUN_00403730`: step cost and parent step per offset (-20..20); the (+-1, 0) cells step along x only."""
    cost, par = {}, {}
    for i in range(-20, 21):
        for j in range(-20, 21):
            a, b = abs(i), abs(j)
            m = max(a, b)
            cost[i, j] = int(math.sqrt(a * a + b * b) * (1 << SCAN_SHIFT) / m) if m else 0
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


_COST, _PAR = _tables()


def sight_mask(heights, width, height, cx, cy, sight):
    """Cells seen from cell (cx, cy) by an observer with sight word `sight` (8.8 fixed point, `obj+0x10a`): `FUN_00403ca0`.

    `M(0,0) = (sight >> 1) + 64`, then rings 1..19: `M(c) = M(parent) - cost - (H(c) - H(observer))` (heights are signed bytes, `heights[row, col]`),
    cells outside `BORDER <= x < width - BORDER` (likewise y) keep 0; a ring in which no cell kept `M >= 1` ends the walk.  Returns a list of (x, y)
    with `M > 0`; empty for `sight <= 0`."""
    if sight <= 0:
        return []
    h0 = int(heights[cy, cx])
    lo_x, hi_x, lo_y, hi_y = BORDER, width - BORDER - 1, BORDER, height - BORDER - 1
    acc = {(0, 0): (sight >> (8 - SCAN_SHIFT)) + (1 << (SCAN_SHIFT - 1))}
    out = [(cx, cy)] if acc[0, 0] > 0 else []
    for k in range(1, RINGS + 1):
        dark = True
        for j in range(-k, k + 1):
            for i2, j2 in ((j, -k), (j, k), (-k, j), (k, -j)):
                wx, wy = cx + i2, cy + j2
                if lo_x <= wx <= hi_x and lo_y <= wy <= hi_y:
                    px, py = _PAR[i2, j2]
                    m = acc.get((i2 + px, j2 + py), 0) - (_COST[i2, j2] + int(heights[wy, wx]) - h0)
                    acc[i2, j2] = m
                    if m > 0:
                        out.append((wx, wy))
                        dark = False
        if dark:
            break
    return out


def new_fog(width, height):
    """All cells never seen."""
    return np.zeros((height, width), np.uint16)


def reveal(fog, cells):
    """`FUN_00460b76`: OR `IN_SIGHT` into the 2 x 2 tiles at each mask cell (clipped to the map)."""
    a = np.asarray(cells, np.intp).reshape(-1, 2)
    if not len(a):
        return
    h, w = fog.shape
    xs, ys = a[:, 0], a[:, 1]
    for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        x, y = xs + dx, ys + dy
        ok = (x < w) & (y < h)
        fog[y[ok], x[ok]] |= np.uint16(IN_SIGHT)


def begin_refresh(fog):
    """`FUN_0040c129`: clear the SEEN bit on every tile (EXPLORED stays)."""
    fog &= np.uint16(~SEEN & 0xFFFF)


def tiles_or(fog, x, y):
    """OR of the tile words (x, y) (x+1, y) (x, y+1) (x+1, y+1) (cells beyond the map count as 0)."""
    h, w = fog.shape
    return int(np.bitwise_or.reduce(fog[y:min(y + 2, h), x:min(x + 2, w)], axis=None))


def cell_in_sight(fog, x, y):
    """Unit / item / dot rule: some of the four tiles has both bits (`& 0xc000 == 0xc000` on the OR of the tiles for items and dots; units test
    each tile, which is the same condition because every reveal sets both bits together)."""
    return tiles_or(fog, x, y) & IN_SIGHT == IN_SIGHT


def structure_state(fog, cells):
    """`FUN_00461460` for a foreign structure: 0 when a footprint cell is in sight, 1 when one is exactly explored, else 2 (never seen)."""
    state = 2
    for x, y in cells:
        v = tiles_or(fog, x, y) & IN_SIGHT
        if v == IN_SIGHT:
            return 0
        if v == EXPLORED:
            state = 1
    return state
