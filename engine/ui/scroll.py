"""Scroll input: arrow keys and the mouse on the screen border move the camera one cell per tick.

CONFIRMED (docs/engine/ui-layout.md section 5, FUN_00488aa1 / FUN_00403f4f): x == 0 or y == 0 scrolls
back, x >= W-2 or y >= H-2 forward, on the screen border only (panels do not matter).
"""

from allods2.graphics.terrain import TILE

PERIOD_MS = 62      # one tick at the default speed (16 ticks/s)


class ScrollInput:
    def __init__(self, period_ms=PERIOD_MS):
        self.period_ms = period_ms
        self.acc = 0

    def direction(self, keys, mouse, screen_w, screen_h):
        """(dx, dy) in -1/0/1.  `keys`: set of 'left','right','up','down';
        `mouse`: (x, y) in the window or None when the pointer is outside."""
        dx = ("right" in keys) - ("left" in keys)
        dy = ("down" in keys) - ("up" in keys)
        if mouse is not None:
            mx, my = mouse
            dx += (mx >= screen_w - 2) - (mx == 0)
            dy += (my >= screen_h - 2) - (my == 0)
        return max(-1, min(1, dx)), max(-1, min(1, dy))

    def update(self, camera, dt_ms, keys, mouse, screen_size):
        """Move `camera` one cell per active axis for every full period in `dt_ms`; the remainder carries over."""
        self.acc += dt_ms
        dx, dy = self.direction(keys, mouse, *screen_size)
        while self.acc >= self.period_ms:
            self.acc -= self.period_ms
            if dx or dy:
                camera.move_by(dx * TILE, dy * TILE)
