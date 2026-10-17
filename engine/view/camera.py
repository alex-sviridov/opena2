"""Camera: world-pixel position of the viewport's top-left, clamped to the map (less `border`)."""

import math

from allods2.graphics.terrain import TILE


class Camera:
    def __init__(self, view_w, view_h, map_w, map_h, x=0.0, y=0.0, border=0):
        """`map_w`, `map_h` in cells; `x`, `y` world px (float); `border` px kept outside the view."""
        self.border = border
        self.view_w, self.view_h = view_w, view_h
        self.map_px_w, self.map_px_h = map_w * TILE, map_h * TILE
        self.x, self.y = float(x), float(y)
        self.clamp()

    def _range(self, map_px, view):
        lo, hi = self.border, map_px - self.border - view
        return (lo, hi) if lo <= hi else (0, max(0, map_px - view))

    @property
    def min_x(self):
        return self._range(self.map_px_w, self.view_w)[0]

    @property
    def min_y(self):
        return self._range(self.map_px_h, self.view_h)[0]

    @property
    def max_x(self):
        return self._range(self.map_px_w, self.view_w)[1]

    @property
    def max_y(self):
        return self._range(self.map_px_h, self.view_h)[1]

    def clamp(self):
        self.x = min(max(self.x, float(self.min_x)), float(self.max_x))
        self.y = min(max(self.y, float(self.min_y)), float(self.max_y))

    def move_to(self, x, y):
        self.x, self.y = float(x), float(y)
        self.clamp()

    def move_by(self, dx, dy):
        self.move_to(self.x + dx, self.y + dy)

    @property
    def ix(self):
        """Integer pixel position used for drawing."""
        return math.floor(self.x)

    @property
    def iy(self):
        return math.floor(self.y)
