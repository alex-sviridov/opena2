"""Surface cache: per-cell RGBA arrays -> pygame surfaces, LRU."""

from collections import OrderedDict

import pygame


class SurfaceCache:
    """Maps a draw item to (surface, y0) via `terrain_view.composite`.  Static cells
    are built once, water cells once per animation phase.  `capacity` 0 disables
    caching (used to measure the uncached cost)."""

    def __init__(self, terrain_view, capacity=8192):
        self.tv, self.capacity = terrain_view, capacity
        self._d = OrderedDict()
        self._version = terrain_view.version
        self.hits = self.misses = 0

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
        comp = self.tv.composite(item.col, item.row, item.phase)
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
