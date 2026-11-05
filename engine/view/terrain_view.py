"""Per-map terrain rendering data and per-cell compositing (numpy, no pygame).

Every pixel comes from the core's terrain functions (`tile_columns`,
`shade_table`, `cell_tile`), so the result equals `render_3d` for the same area.
"""

import numpy as np

from allods2.graphics import lighting as lt
from allods2.graphics.palette import BRIGHT32, shade_table
from allods2.graphics.terrain import LIGHT_ROWS, TILE, WATER, decode_cell, tile_columns

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
        self.version = 0                # bumped when the light changes: cell caches must drop
        self._minutes = None
        self._apply(minutes)

    def _apply(self, minutes):
        """FUN_0041d3b9 body: FUN_00474d98 (daylight), FUN_004a5dd2 (terrain light),
        FUN_0047e345 (tinted tables)."""
        day = lt.daylight(minutes, self.time_flow)
        light = lt.terrain_light(self.world.heights, day.angle, day.ambient, day.diffuse)
        self.light = np.pad(np.asarray(light), ((0, 1), (0, 1)), mode="edge")
        self.table = shade_table(self.terrain.palette, LIGHT_ROWS, BRIGHT32, day.tint)
        self.day, self._minutes = day, minutes
        self.world.daylight = day       # client-side only; read by the draw list
        self.version += 1

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

    def composite(self, col, row, phase=0):
        """(rgba, y0): the cell as an (n, 32, 4) uint8 array, alpha 255 where the
        game's blit writes a pixel, and y0 = world y of its first row; None when
        nothing is drawn (tile past its strip, or every column back-facing)."""
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
