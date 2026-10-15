"""Compositing with the game's draw modes, on an RGB888 numpy surface.

The game draws to 16-bit surfaces; these modes reproduce its arithmetic per
channel at 8 bits (spec: docs/formats/sprites.md).
"""

import numpy as np

from .sprites import decode_16, decode_16a, decode_256


class Canvas:
    def __init__(self, width, height, fill=(0, 0, 0)):
        self.pix = np.empty((height, width, 3), np.uint8)
        self.pix[...] = fill

    @property
    def width(self):
        return self.pix.shape[1]

    @property
    def height(self):
        return self.pix.shape[0]

    def _region(self, x, y, decoded):
        """Clip a sprite placed at (x, y): returns (dst view, sprite slices)."""
        h, w = decoded.mask.shape
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + w, self.width), min(y + h, self.height)
        if x0 >= x1 or y0 >= y1:
            return None, None
        src = (slice(y0 - y, y1 - y), slice(x0 - x, x1 - x))
        return self.pix[y0:y1, x0:x1], src

    def _apply(self, x, y, decoded, fn):
        dst, src = self._region(x, y, decoded)
        if dst is None:
            return
        m = decoded.mask[src]
        dst[m] = fn(dst[m].astype(np.uint16), src, m).astype(np.uint8)

    def draw_256(self, sprite, x, y, palette):
        """Opaque palette sprite (0x459614)."""
        d = decode_256(sprite.data, sprite.width, sprite.height)
        pal = np.asarray(palette, np.uint8)
        self._apply(x, y, d, lambda dst, s, m: pal[d.index[s][m]])

    def draw_256_translucent(self, sprite, x, y, palette):
        """50 % blend, (src >> 1) + (dst >> 1) per channel (0x459926).  Used
        for *b.256 smoothing overlays and for units with state flag 0x20."""
        d = decode_256(sprite.data, sprite.width, sprite.height)
        pal = np.asarray(palette, np.uint16)
        self._apply(x, y, d, lambda dst, s, m: (pal[d.index[s][m]] >> 1) + (dst >> 1))

    def draw_darken(self, sprite, x, y, level=8):
        """Darken the sprite's area (0x459d8c, sprite vtable +0x1c): the pixel
        values are skipped, dst = dst * (16 - level) / 16.  Which objects the
        game draws this way is not yet known."""
        d = decode_256(sprite.data, sprite.width, sprite.height)
        self._apply(x, y, d, lambda dst, s, m: (dst * (16 - level)) >> 4)

    def draw_16a(self, sprite, x, y, palette):
        """Alpha sprite (0x45db6b): src * (a + 1) / 16 + dst * (15 - a) / 16."""
        d = decode_16a(sprite.data, sprite.width, sprite.height)
        pal = np.asarray(palette, np.uint16)

        def blend(dst, s, m):
            a = d.alpha[s][m].astype(np.uint16)[:, None]
            src = pal[d.index[s][m]]
            return np.minimum(((src * (a + 1)) >> 4) + ((dst * (15 - a)) >> 4), 255)
        self._apply(x, y, d, blend)

    def draw_16(self, sprite, x, y, colors):
        """4-bit glyph (0x4593a1); colors: 16 RGB entries (the text colour table)."""
        d = decode_16(sprite.data, sprite.width, sprite.height)
        cols = np.asarray(colors, np.uint8)
        self._apply(x, y, d, lambda dst, s, m: cols[d.index[s][m]])
