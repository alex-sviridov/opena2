"""Surface cache: per-cell RGBA arrays -> pygame surfaces, LRU."""

import time
from collections import OrderedDict

import pygame

from engine.view import TerrainItem
from allods2.graphics.terrain import TILE


class SurfaceCache:
    """Maps a draw item to (surface, y0) via `terrain_view.composite`.  Static cells
    are built once, water cells once per animation phase.  `capacity` 0 disables
    caching (used to measure the uncached cost)."""

    def __init__(self, terrain_view, capacity=8192):
        self.tv, self.capacity = terrain_view, capacity
        self._d = OrderedDict()
        self._version = terrain_view.version
        self.hits = self.misses = 0

    def prewarm(self, camera, tick, budget_ms=4.0, margin=2):
        """Build the cells in a ring of `margin` cells around the visible ones that are not cached yet, nearest rows first, for at most
        `budget_ms` (call it after a frame is drawn: a scroll then finds the next row / column ready instead of building it in one frame).
        Returns the number built."""
        tv = self.tv
        x0, x1, y0, y1 = tv.proj.visible_cells(camera)
        cols, rows = tv.proj.cols, tv.proj.rows
        xa, xb, ya, yb = max(0, x0 - margin), min(cols, x1 + margin), max(0, y0 - margin), min(rows, y1 + margin)
        ring = [(c, r) for r in range(y0 - 1, ya - 1, -1) for c in range(xa, xb)]
        ring += [(c, r) for r in range(y1, yb) for c in range(xa, xb)]
        for r in range(max(y0, ya), min(y1, yb)):
            ring += [(c, r) for c in list(range(x0 - 1, xa - 1, -1)) + list(range(x1, xb))]
        cx = camera.ix
        deadline = time.perf_counter() + budget_ms / 1000
        built = 0
        for c, r in ring:
            if r < 0 or r >= rows:
                continue
            ph = tv.phase(c, r, tick)
            if (c, r, ph, None) in self._d:
                continue
            self.get(TerrainItem(c, r, ph, c * TILE - cx))
            built += 1
            if time.perf_counter() > deadline:
                break
        return built

    def get(self, item):
        if self.tv.version != self._version:        # the light changed (day/night step)
            self._d.clear()
            self._version = self.tv.version
        key = item.key
        d = self._d
        if key in d:
            d.move_to_end(key)
            self.hits += 1
            return d[key]
        self.misses += 1
        comp = self.tv.composite(item.col, item.row, item.phase, item.lit)
        val = None
        if comp is not None:
            arr, y0 = comp
            surf = pygame.image.frombuffer(arr.tobytes(), (arr.shape[1], arr.shape[0]), "RGBA")
            val = (surf, y0)
        if self.capacity:
            d[key] = val
            if len(d) > self.capacity:
                d.popitem(last=False)
        return val
