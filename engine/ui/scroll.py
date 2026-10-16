"""Scroll input: arrow keys and the mouse at the window edge move the camera.

Speed and edge zone are engine choices, not from the exe (architecture.md).
"""

SCROLL_SPEED = 600.0      # px per second
EDGE = 4                  # px from the window border


class ScrollInput:
    def __init__(self, speed=SCROLL_SPEED, edge=EDGE):
        self.speed, self.edge = speed, edge

    def direction(self, keys, mouse, view_w, view_h):
        """(dx, dy) in -1/0/1.  `keys`: set of 'left','right','up','down';
        `mouse`: (x, y) in the window or None when the pointer is outside."""
        dx = ("right" in keys) - ("left" in keys)
        dy = ("down" in keys) - ("up" in keys)
        if mouse is not None:
            mx, my = mouse
            dx += (mx >= view_w - self.edge) - (mx < self.edge)
            dy += (my >= view_h - self.edge) - (my < self.edge)
        return max(-1, min(1, dx)), max(-1, min(1, dy))

    def update(self, camera, dt_ms, keys, mouse=None):
        """Move `camera` for `dt_ms` of frame time."""
        dx, dy = self.direction(keys, mouse, camera.view_w, camera.view_h)
        if dx or dy:
            d = self.speed * dt_ms / 1000.0
            camera.move_by(dx * d, dy * d)
