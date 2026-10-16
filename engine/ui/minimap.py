"""Minimap panel: click or drag centres the camera on that cell.  View state only, never a
command (architecture rule 4)."""

from allods2.graphics.terrain import TILE

PANEL_ORIGIN = (8, 8)       # px from the window's top-right corner: INFERRED until the G3b frame
CENTER = (0x48, 0x52)       # the image's centre inside the exe's panel (CONFIRMED FUN_004ac414)


class MinimapPanel:
    def __init__(self, geometry, left, top):
        """`left`, `top`: window position of the image's top-left pixel."""
        self.geometry, self.left, self.top = geometry, left, top
        self.dragging = False

    @classmethod
    def at_top_right(cls, geometry, window_w, origin=PANEL_ORIGIN):
        return cls(geometry, window_w - origin[0] - geometry.width, origin[1])

    def contains(self, x, y):
        g = self.geometry
        return self.left <= x < self.left + g.width and self.top <= y < self.top + g.height

    def cell_at(self, x, y):
        """Cell position (floats) under window pixel (x, y)."""
        return self.geometry.pixel_to_cell(x - self.left, y - self.top)

    def center_camera(self, camera, x, y):
        """Centre `camera` on the cell under (x, y); the camera clamps to the map."""
        col, row = self.cell_at(x, y)
        camera.move_to(col * TILE - camera.view_w / 2, row * TILE - camera.view_h / 2)

    def press(self, camera, x, y):
        """Mouse button down; True when the panel took it."""
        if not self.contains(x, y):
            return False
        self.dragging = True
        self.center_camera(camera, x, y)
        return True

    def drag(self, camera, x, y):
        """Mouse moved with the button held; the pointer may leave the image."""
        if self.dragging:
            self.center_camera(camera, x, y)

    def release(self):
        self.dragging = False
