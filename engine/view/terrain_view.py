"""Per-map terrain rendering data and per-cell compositing (numpy, no pygame).

Every pixel comes from the core's terrain functions (`tile_columns`,
`shade_table`, `cell_tile`), so the result equals `render_3d` for the same area.
"""

import numpy as np

from allods2.graphics import lighting as lt
from allods2.graphics.palette import BRIGHT32, shade_table
from allods2.graphics.terrain import LIGHT_ROWS, TILE, WATER, decode_cell, edge_offsets, tile_columns

from .coords import Projection


class TerrainView:
    def __init__(self, world, terrain, animate=True, minutes=0, time_flow=False):
        """`terrain`: a `TerrainSet`.  Light = terrain light at the fixed default
        daylight (the game's "ShowTimeFlow" option off, its default), like
        `map render --relief`.  `time_flow` turns the day/night cycle on
        ([lighting §1](../../docs/mechanics/lighting.md#1-time-of-day-fun_00474d98-confirmed),
        client-only: nothing here enters the world hash)."""
        self.world, self.terrain, self.animate = world, terrain, animate
        self.proj = Projection(world.heights)
        self.time_flow = time_flow
        self._light_version = 0         # bumped when the light changes: cell caches must drop
        self._minutes = None
        self._apply(minutes)

    def _apply(self, minutes):
        """FUN_0041d3b9 body: FUN_00474d98 (daylight), FUN_004a5dd2 (terrain light),
        FUN_0047e345 (tinted tables)."""
        day = lt.daylight(minutes, self.time_flow)
        light = lt.terrain_light(self.world.heights, day.angle, day.ambient, day.diffuse)
        self.base_light = np.pad(np.asarray(light), ((0, 1), (0, 1)), mode="edge")
        getattr(self.world, "light_vertices", {}).clear()       # FUN_004a5dd2 over the whole map overwrites every Light / Darkness vertex write
        self._lv = None
        self.table = shade_table(self.terrain.palette, LIGHT_ROWS, BRIGHT32, day.tint)
        self.day, self._minutes = day, minutes
        self.world.daylight = day       # client-side only; read by the draw list
        self._light_version += 1

    @property
    def light(self):
        self._sync_light()
        return self._light

    def _sync_light(self):
        lv = getattr(self.world, "light_version", 0)
        if lv != self._lv:                  # Light / Darkness cell flags (`World.light_write`): the vertex values they wrote replace the computed ones
            self._lv = lv
            over = getattr(self.world, "light_vertices", None)
            if over:
                L = self.base_light.copy()
                h, w = L.shape
                for (x, y), val in over.items():
                    if 0 <= x < w and 0 <= y < h:
                        L[y, x] = val
                self._light = L
            else:
                self._light = self.base_light
            self._light_version += 1

    @property
    def version(self):
        """Changes whenever a cached cell composite is stale: the light stepped, or a tile bit changed at run time (`World.scorch`)."""
        self._sync_light()
        return self._light_version + getattr(self.world, "cells_version", 0)

    def set_clock(self, tick, force=False):
        """FUN_0041d3b9: with the option on, recompute when `tick & 15 == 0` and
        `m = (tick >> 4) + 360` is a multiple of 20 (every 320 ticks); `force` is
        its param 1 (load, option change).  Returns True when the light changed."""
        minutes = (tick >> 4) + 360
        if not (force or (self.time_flow and tick & 15 == 0 and minutes % 20 == 0)):
            return False
        if minutes == self._minutes and not force:
            return False
        self._apply(minutes)
        return True

    def set_time_flow(self, on, tick=0):
        """The option toggle (key 'N' in debug mode, options): recomputes at once."""
        self.time_flow = bool(on)
        self.set_clock(tick, force=True)

    def phase(self, col, row, tick):
        """Water animation phase (tick >> 2) & 3; 0 for other cells or when frozen."""
        if not self.animate or decode_cell(self.world.cells[row, col]).set not in WATER:
            return 0
        return (tick >> 2) & 3

    def composite_reference(self, col, row, phase=0):
        """(rgba, y0): the cell as an (n, 32, 4) uint8 array, alpha 255 where the
        game's blit writes a pixel, and y0 = world y of its first row; None when
        nothing is drawn (tile past its strip, or every column back-facing).
        The column-by-column form of `composite`, kept as its parity reference."""
        t = self.terrain.cell_tile(self.world.cells[row, col], col, row,
                                   phase << 2, self.animate)
        if t is None:
            return None
        L = self.light
        lights = (L[row, col], L[row, col + 1], L[row + 1, col], L[row + 1, col + 1])
        cols = list(tile_columns(*self.proj.corners(col, row), lights))
        if not cols:
            return None
        y0 = min(c[1] for c in cols)
        y1 = max(c[1] + len(c[2]) for c in cols)
        out = np.zeros((y1 - y0, TILE, 4), np.uint8)
        for c, top, rows, lrows in cols:
            px = self.table[np.clip(lrows, 0, LIGHT_ROWS - 1), t[rows, c]]
            out[top - y0:top - y0 + len(rows), c, :3] = px
            out[top - y0:top - y0 + len(rows), c, 3] = 255
        return out, y0

    def composite(self, col, row, phase=0, lit=None):
        """`composite_reference`, all 32 columns at once (the column spans, texel rows and light rows as 2-D arrays); the same pixels."""
        t = self.terrain.cell_tile(self.world.cells[row, col], col, row,
                                   phase << 2, self.animate)
        if t is None:
            return None
        L = self.light
        ltl, ltr, lbl, lbr = lit if lit is not None else (int(v) for v in (L[row, col], L[row, col + 1], L[row + 1, col], L[row + 1, col + 1]))
        ytl, ytr, ybl, ybr = self.proj.corners(col, row)
        top = ytl + _edges(ytl, ytr, False)
        bot = ybl + _edges(ybl, ybr, True)
        span = bot - top
        ok = span > 0
        if not ok.any():
            return None
        n = int(span.max())
        sp = np.where(ok, span, 1)
        c = np.arange(TILE)
        i = np.arange(n)
        lt = (ltl << 9) + c * ((ltr - ltl) * 16)
        lb = (lbl << 9) + c * ((lbr - lbl) * 16)
        diff = lb - lt
        lstep = np.where(diff >= 0, diff // sp, -((-diff) // sp))      # C division
        rows = (i[None, :] * (0x200000 // sp)[:, None]) >> 16
        lrows = (lt[:, None] + 0x100 + i[None, :] * lstep[:, None]) >> 9
        sel = (i[None, :] < span[:, None]) & ok[:, None]
        y0 = int(top[ok].min())
        y1 = int((top + span)[ok].max())
        px = self.table[np.clip(lrows, 0, LIGHT_ROWS - 1), t[np.minimum(rows, TILE - 1), c[:, None]]]      # (32, n, 3)
        yy = (top - y0)[:, None] + i[None, :]
        out = np.zeros((y1 - y0, TILE, 4), np.uint8)
        cc = np.broadcast_to(c[:, None], sel.shape)
        out[yy[sel], cc[sel], :3] = px[sel]
        out[yy[sel], cc[sel], 3] = 255
        return out, y0


_EDGES = {}


def _edges(y0, y1, bottom):
    """`edge_offsets` memoised (the heights repeat all over a map)."""
    key = (y1 - y0, bottom)
    got = _EDGES.get(key)
    if got is None:
        got = _EDGES[key] = edge_offsets(0, y1 - y0, bottom)
    return got
