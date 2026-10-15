"""Terrain: .alm Tiles values -> 32x32 tiles from tile<g>-<nn>.bmp strips.

Spec: docs/formats/terrain.md.  Loader FUN_0047b899, cell decode and
water/dirt rules FUN_00404eb5, flat lit blit FUN_0045c757, height-displaced
blit FUN_0045c8ce with the edge step table from FUN_0045752b, vertex table
FUN_00406658.
"""

import os
from dataclasses import dataclass

import numpy as np

from .bmp import load_bmp
from .palette import BRIGHT32, shade_table

TILE = 32
SETS = 13                  # sets 0..12 exist in this install (slots go to 32)
STRIPS = 4                 # bitmaps per set
WATER = range(8, 12)       # sets drawn as 4 animation frames
DIRT_FLAG = 0x2000
LIGHT_ROWS = 0x60          # BRIGHT32 table, 96 rows; row 64 = x1


@dataclass
class Cell:
    set: int               # (v & 0x1fff) >> 6
    strip: int             # (v >> 4) & 3
    row: int               # v & 0xf, tile index inside the strip
    dirt: bool             # v & 0x2000 (ignored on water sets)


def cell_value(set_, strip, row, dirt=False):
    """Inverse of decode_cell: the u16 a map stores for this tile."""
    return (set_ << 6) | (strip << 4) | row | (DIRT_FLAG if dirt else 0)


def decode_cell(v):
    v = int(v)
    return Cell((v & 0x1FFF) >> 6, (v >> 4) & 3, v & 0xF, bool(v & DIRT_FLAG))


def strip_name(set_, strip):
    """FUN_0047b899: slot t, bitmap j -> tile{(t>>2)+1}-{(t&3)*4+j:02d}.bmp."""
    return "tile%d-%02d.bmp" % ((set_ >> 2) + 1, (set_ & 3) * 4 + strip)


def water_set(set_, x, y, anim, animate=True):
    """FUN_00404eb5: water sets cycle through 8..11.  `anim` is the
    counter at view+0xa88; the option DAT_005fb974 == 0 freezes frame 0."""
    if not animate:
        return 8
    return 8 + ((set_ + (x + 1) * y + (anim >> 2)) & 3)


def dirt_variant(x, y):
    return (x + 5 * y) & 3


class TerrainSet:
    """The strips the game keeps in DAT_00630b90[set][strip] plus dirt.bmp."""

    def __init__(self, strips, dirt, palette):
        self.strips = strips        # {(set, strip): (rows*32, 32) uint8}
        self.dirt = dirt            # (128, 32) uint8
        self.palette = palette      # (256, 3) of the tile strips

    @classmethod
    def load(cls, terrain_dir):
        strips, palette = {}, None
        for s in range(SETS):
            for j in range(STRIPS):
                path = os.path.join(terrain_dir, strip_name(s, j))
                if os.path.exists(path):
                    bmp = load_bmp(path)
                    strips[(s, j)] = bmp.index
                    if palette is None:
                        palette = bmp.palette
        dirt = load_bmp(os.path.join(terrain_dir, "dirt.bmp")).index
        return cls(strips, dirt, palette)

    def rows(self, set_, strip):
        a = self.strips.get((set_, strip))
        return 0 if a is None else a.shape[0] // TILE

    def tile(self, set_, strip, row):
        """(32, 32) indices, or None where the game would read past the
        strip (row >= tiles in the strip, or a missing file)."""
        a = self.strips.get((set_, strip))
        if a is None or row >= a.shape[0] // TILE:
            return None
        return a[row * TILE:(row + 1) * TILE]

    def tile_rgba(self, set_, strip, row, light=None, tint=(0, 0, 0)):
        """(32, 32, 4) uint8 RGBA of one tile, or None (see tile()).

        light: a row of the set's 96-row BRIGHT32 table, applied to the whole
        tile (64 = x1, 46 = flat ground in daylight); None = plain palette."""
        t = self.tile(set_, strip, row)
        if t is None:
            return None
        if light is None:
            rgb = self.palette[t]
        else:
            rgb = shade_table(self.palette, LIGHT_ROWS, BRIGHT32, tint)[light][t]
        out = np.empty((TILE, TILE, 4), np.uint8)
        out[..., :3] = rgb
        out[..., 3] = 255
        return out

    def cell_tile(self, v, x, y, anim=0, animate=True):
        """Indices the game blits for map value v at cell (x, y)."""
        c = decode_cell(v)
        s = water_set(c.set, x, y, anim, animate) if c.set in WATER else c.set
        t = self.tile(s, c.strip, c.row)
        if c.dirt and c.set not in WATER:
            base = np.zeros((TILE, TILE), np.uint8) if t is None else t.copy()
            d = self.dirt[dirt_variant(x, y) * TILE:(dirt_variant(x, y) + 1) * TILE]
            np.copyto(base, d, where=d != 0)       # FUN_00457e8d: index 0 is clear
            return base
        return t


def light_rows(corners):
    """FUN_0045c757: (32, 32) table rows for corner lights
    (top-left, top-right, bottom-left, bottom-right), column by column."""
    tl, tr, bl, br = (int(c) for c in corners)
    out = np.empty((TILE, TILE), np.int64)
    top, bot = tl << 9, bl << 9
    for c in range(TILE):
        diff = bot - top
        step = (diff + (31 if diff < 0 else 0)) >> 5      # C division by 32
        v = top + 0x100 + step * np.arange(TILE)
        out[:, c] = v >> 9
        top += (tr - tl) * 16
        bot += (br - bl) * 16
    return out


def _cdiv(a, b):
    """C integer division (truncates toward zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def _step_row(n):
    """FUN_0045752b: T[n][k], k = 0..n, the column where an edge that moves
    n pixels over the tile takes its (k+1)-th 1-pixel step."""
    step = 0x200000 // (n + 1)
    return [((k + 1) * step + 0x8000) >> 16 for k in range(n + 1)]


STEP_ROWS = 128            # the game builds rows 1..127 (row 0 stays zero)
STEP_TABLE = [[0]] + [_step_row(n) for n in range(1, STEP_ROWS)]


def _step_row_any(n):
    # |dy| > 127 makes the game read past its table (into DAT_00629780);
    # that is undefined, so the formula is extended instead.
    return STEP_TABLE[n] if n < STEP_ROWS else _step_row(n)


def edge_offsets(y0, y1, bottom=False):
    """Per tile column c = 0..31, the y of an edge from y0 (left) to y1
    (right) relative to y0, as FUN_0045c8ce steps it before drawing column c.

    The top edge counts T[n][k] <= c when it goes down (y0 < y1) and
    32 - T[n][k] <= c when it goes up; the bottom edge does the opposite,
    so the two edges round differently."""
    n = abs(y1 - y0)
    if n == 0:
        return np.zeros(TILE, np.int64)
    t = np.asarray(_step_row_any(n)[:n])
    c = np.arange(TILE)[:, None]
    fwd = (t[None, :] <= c).sum(1)
    mir = ((TILE - t)[None, :] <= c).sum(1)
    down = y0 < y1
    if bottom:
        return mir if down else -fwd
    return fwd if down else -mir


def tile_columns(ytl, ytr, ybl, ybr, lights):
    """FUN_0045c8ce for one tile: yields (c, y_top, rows, light_rows) for
    each column that has pixels.  rows[i] is the tile texel row drawn at
    y_top + i, light_rows[i] the row of the 96-row shade table.  lights =
    (tl, tr, bl, br) corner light values."""
    ltl, ltr, lbl, lbr = (int(v) for v in lights)
    top = ytl + edge_offsets(ytl, ytr)
    bot = ybl + edge_offsets(ybl, ybr, bottom=True)
    lt, lb = ltl << 9, lbl << 9
    for c in range(TILE):
        span = int(bot[c] - top[c])
        if span > 0:
            vstep = 0x200000 // span
            lstep = _cdiv(lb - lt, span)
            i = np.arange(span, dtype=np.int64)
            yield c, int(top[c]), (i * vstep) >> 16, (lt + 0x100 + i * lstep) >> 9
        lt += (ltr - ltl) * 16
        lb += (lbr - lbl) * 16


def vertex_y(heights):
    """FUN_00406658: screen y of vertex (x, y) = 32·y − H[y][x], with H the
    .alm Altitudes block read as signed bytes (runtime map +0x10).  Returns
    an (h + 1, w + 1) array; the extra row and column repeat the last ones
    (INFERRED: the game never draws the map edge)."""
    H = np.asarray(heights).astype(np.int8).astype(np.int64)
    H = np.pad(H, ((0, 1), (0, 1)), mode="edge")
    return np.arange(H.shape[0])[:, None] * TILE - H


def render_3d(tiles, heights, terrain, light, anim=0, animate=True, tint=(0, 0, 0)):
    """(h·32 + top + bottom, w·32, 3) RGB of a Tiles block drawn like
    FUN_00404eb5 with heights: rows top to bottom, each tile through
    FUN_0045c8ce (on undistorted tiles this equals the flat blit).  Returns
    (image, top) where `top` is the margin above map row 0 in pixels."""
    h, w = tiles.shape
    vy = vertex_y(heights)
    top = max(0, -int(vy.min()))
    height = max(int(vy.max()), h * TILE) + top
    out = np.zeros((height, w * TILE, 3), np.uint8)
    table = shade_table(terrain.palette, LIGHT_ROWS, BRIGHT32, tint)
    L = np.pad(np.asarray(light), ((0, 1), (0, 1)), mode="edge")
    for y in range(h):
        for x in range(w):
            t = terrain.cell_tile(tiles[y, x], x, y, anim, animate)
            if t is None:
                continue
            corners = (vy[y, x], vy[y, x + 1], vy[y + 1, x], vy[y + 1, x + 1])
            lights = (L[y, x], L[y, x + 1], L[y + 1, x], L[y + 1, x + 1])
            for c, y0, rows, lrows in tile_columns(*(int(v) for v in corners), lights):
                px = table[np.clip(lrows, 0, LIGHT_ROWS - 1), t[rows, c]]
                yy = y0 + top + np.arange(len(rows))
                ok = (yy >= 0) & (yy < height)
                out[yy[ok], x * TILE + c] = px[ok]
    return out, top


def render(tiles, terrain, light=None, anim=0, animate=True, tint=(0, 0, 0)):
    """(h·32, w·32, 3) RGB of a Tiles block drawn flat (no height offsets).

    light: optional (h, w) per-vertex light map (rows of the 96-row BRIGHT32
    table, lighting.md §2); corners at the map edge reuse the last column /
    row.  Without it, tiles use the plain strip palette.  Cells whose tile is
    past the end of a strip are left black."""
    h, w = tiles.shape
    out = np.zeros((h * TILE, w * TILE, 3), np.uint8)
    table = shade_table(terrain.palette, LIGHT_ROWS, BRIGHT32, tint) if light is not None else None
    for y in range(h):
        for x in range(w):
            t = terrain.cell_tile(tiles[y, x], x, y, anim, animate)
            if t is None:
                continue
            if table is None:
                px = terrain.palette[t]
            else:
                x1, y1 = min(x + 1, w - 1), min(y + 1, h - 1)
                rows = light_rows((light[y, x], light[y, x1], light[y1, x], light[y1, x1]))
                px = table[np.clip(rows, 0, LIGHT_ROWS - 1), t]
            out[y * TILE:(y + 1) * TILE, x * TILE:(x + 1) * TILE] = px
    return out
