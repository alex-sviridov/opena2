"""Compositing with the game's draw modes, on an RGB888 numpy surface.

The game draws to 16-bit surfaces; these modes reproduce its arithmetic per
channel at 8 bits (spec: docs/formats/sprites.md).
"""

import dataclasses

import numpy as np

from .sprites import decode_16, decode_16a, decode_256


def _mirror(d, mirror):
    """The mirrored blitters write each row from x + w - 1 leftward: a
    horizontal flip in the same rectangle."""
    if not mirror:
        return d
    flip = lambda a: None if a is None else a[:, ::-1]
    return dataclasses.replace(d, index=flip(d.index), mask=flip(d.mask), alpha=flip(d.alpha))


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

    def draw_256(self, sprite, x, y, palette, mirror=False):
        """Opaque palette sprite (0x459614; mirrored 0x45a64d)."""
        d = _mirror(decode_256(sprite.data, sprite.width, sprite.height), mirror)
        pal = np.asarray(palette, np.uint8)
        self._apply(x, y, d, lambda dst, s, m: pal[d.index[s][m]])

    def draw_256_translucent(self, sprite, x, y, palette, mirror=False):
        """50 % blend, (src >> 1) + (dst >> 1) per channel (0x459926; mirrored
        0x45a8e7).  Used for *b.256 smoothing overlays and for units with
        effect 0x20."""
        d = _mirror(decode_256(sprite.data, sprite.width, sprite.height), mirror)
        pal = np.asarray(palette, np.uint16)
        self._apply(x, y, d, lambda dst, s, m: (pal[d.index[s][m]] >> 1) + (dst >> 1))

    def draw_darken(self, sprite, x, y, level=8, mirror=False):
        """Darken the sprite's area (0x459d8c; mirrored 0x45ad81; sprite vtable
        +0x1c): the pixel values are skipped, dst = dst * (16 - level) / 16.
        The game uses it for UI drop shadows (lm.256 level 6, scrlbars.256
        and radiob.256 level 4, an inventory indicator level 8)."""
        d = _mirror(decode_256(sprite.data, sprite.width, sprite.height), mirror)
        self._apply(x, y, d, lambda dst, s, m: (dst * (16 - level)) >> 4)

    def draw_16a(self, sprite, x, y, palette, mirror=False):
        """Alpha sprite (0x45db6b; mirrored 0x45dee0):
        src * (a + 1) / 16 + dst * (15 - a) / 16."""
        d = _mirror(decode_16a(sprite.data, sprite.width, sprite.height), mirror)
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
