"""Minimap geometry and image with the camera rectangle (no pygame).

Spec: docs/superpowers/specs/2026-10-16-minimap-design.md.  Image pixels per cell `s = 2**k`
(`allods2.minimap.scale_shift`); image pixel `(px, py)` is cell `(px / s + 8, py / s + 8)`.
"""

from allods2.graphics.terrain import TILE
from allods2.minimap import BORDER, minimap_rgb, minimap_size, scale_shift

RECT_COLOR = (255, 255, 255)        # CONFIRMED FUN_004569a3 call: all channels full


class MinimapGeometry:
    def __init__(self, map_w, map_h):
        """`map_w`, `map_h` in cells."""
        self.map_w, self.map_h = map_w, map_h
        self.k = scale_shift(map_w, map_h)
        self.s = 2.0 ** self.k
        self.width, self.height = minimap_size(map_w, map_h)

    def cell_to_pixel(self, col, row):
        """Image position (float) of the top-left corner of cell (col, row)."""
        return (col - BORDER) * self.s, (row - BORDER) * self.s

    def pixel_to_cell(self, px, py):
        """Cell position (floats) under image pixel (px, py); not clamped."""
        return px / self.s + BORDER, py / self.s + BORDER

    def camera_cell(self, camera):
        """The camera's top-left as a cell position (relief height ignored: DECISION)."""
        return camera.x / TILE, camera.y / TILE

    def camera_rect(self, camera):
        """(x0, y0, x1, y1) inclusive image pixels of the camera outline, clipped to the
        image; None when it lies outside."""
        cx, cy = self.camera_cell(camera)
        x0, y0 = self.cell_to_pixel(cx, cy)
        x1 = x0 + camera.view_w / TILE * self.s - 1
        y1 = y0 + camera.view_h / TILE * self.s - 1
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        if x1 < 0 or y1 < 0 or x0 >= self.width or y0 >= self.height:
            return None
        return max(x0, 0), max(y0, 0), min(x1, self.width - 1), min(y1, self.height - 1)


def draw_camera_rect(image, rect, color=RECT_COLOR):
    """Copy of `image` with the one-pixel outline `rect` drawn."""
    out = image.copy()
    if rect is not None:
        x0, y0, x1, y1 = rect
        out[y0, x0:x1 + 1] = color
        out[y1, x0:x1 + 1] = color
        out[y0:y1 + 1, x0] = color
        out[y0:y1 + 1, x1] = color
    return out


class Minimap:
    """The base image of a world, built once; `image(camera)` adds the camera rectangle."""

    def __init__(self, world, table):
        self.world, self.table = world, table
        self.geometry = MinimapGeometry(world.width, world.height)
        self._base = None
        self.builds = 0

    def invalidate(self):
        """Forget the base image (terrain edits; nothing else changes the picture)."""
        self._base = None

    @property
    def base(self):
        if self._base is None:
            self._base = minimap_rgb(self.world.cells, self.table)
            self._base.flags.writeable = False
            self.builds += 1
        return self._base

    def image(self, camera):
        return draw_camera_rect(self.base, self.geometry.camera_rect(camera))
