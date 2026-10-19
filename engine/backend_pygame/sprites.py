"""Sprite cache: draw items -> pygame surfaces or numpy blend masks, LRU.

Opaque sprites become RGBA surfaces (alpha 255 where the game writes a pixel) that
`Surface.blit` copies exactly.  The 50 % smoothing overlay and the shadows depend on
the destination, so their cache entries are masks for numpy arithmetic on the
framebuffer (the core's formulas: `Canvas.draw_256_translucent`, `Canvas.draw_darken`).
"""

from collections import OrderedDict

import numpy as np
import pygame

from allods2.graphics.palette import BRIGHT2, grayscale_palette, shade_table

LIGHT_LEVELS = 16


def _main(source):
    return source[:-2] if source.endswith("_b") else source


class SpriteCache:
    """`assets`: an `AssetCache`.  `capacity` 0 disables caching (timing runs)."""

    def __init__(self, assets, capacity=4096, tint=(0, 0, 0)):
        self.assets, self.capacity, self.tint = assets, capacity, tint
        self._d = OrderedDict()
        self._tables = {}
        self.hits = self.misses = 0

    def file(self, sprite):
        """The `SpriteFile` of a draw item's `sprite` tuple, or None."""
        kind, tid, source = sprite
        if kind == "backpack":
            from engine.view.drawlist import BACKPACK
            return self.assets.sprite(BACKPACK + ("b" if source.endswith("_b") else "") + ".256")
        aset = (self.assets.object_set(tid) if kind == "object" else
                self.assets.unit_set(tid) if kind == "unit" else
                self.assets.projectile_set(tid) if kind == "projectile" else self.assets.structure_set(tid, None))
        return None if aset is None else aset.sprites(source)

    def palette(self, sprite, light_row, remap=None):
        """(256, 3) colours of the main file's palette, through BRIGHT2 row `light_row`
        (None = the file's own colours).  Units: the set's palette for `remap` = (human.pal row,
        variant); the `b` overlay uses the main sprite's table."""
        kind, tid, source = sprite
        main = (kind, tid, _main(source))
        sf = self.file(main)
        if kind == "unit":
            aset = self.assets.unit_set(tid)
            pal = np.asarray(aset.palette(_main(source), *(remap or (0, 0))), np.uint8)
        elif kind == "projectile":          # a file palette (A16, Palette != 0), else projectiles.pal (animation.md 4.4)
            own = None if sf is None else sf.palette
            pal = np.asarray(own if own is not None else self.assets.projectile_set(tid).shade_palette, np.uint8)
        else:
            pal = grayscale_palette() if sf is None or sf.palette is None else np.asarray(sf.palette, np.uint8)
        if light_row is None:
            return pal
        tkey = main + (remap,)
        t = self._tables.get(tkey)
        if t is None:
            t = self._tables[tkey] = shade_table(pal, LIGHT_LEVELS, BRIGHT2, self.tint)
        return t[min(light_row, LIGHT_LEVELS - 1)]

    def get(self, item):
        """Cache entry of a "sprite" or "shadow" item: a Surface (opaque), (mask_t, src_t)
        for blend "half", or (mask_t, dx) for a shadow; None when the frame is missing.
        mask_t is (w, h) bool (x first, as `pixels3d`)."""
        shadow = item.kind == "shadow"
        key = (item.sprite, item.frame, item.mirrored, "shadow" if shadow else item.blend,
               None if shadow else item.light_row, item.shear if shadow else 0,
               None if shadow else item.remap)
        d = self._d
        if key in d:
            d.move_to_end(key)
            self.hits += 1
            return d[key]
        self.misses += 1
        val = self._build(item, shadow)
        if self.capacity:
            d[key] = val
            if len(d) > self.capacity:
                d.popitem(last=False)
        return val

    def _build(self, item, shadow):
        sf = self.file(item.sprite)
        if sf is None or not 0 <= item.frame < len(sf):
            return None
        dec = sf.decode(item.frame)
        mask, idx = dec.mask, dec.index
        if item.mirrored:
            mask, idx = mask[:, ::-1], idx[:, ::-1]
        if shadow:
            from engine.view.drawlist import shadow_offsets
            off, lo, hi = shadow_offsets(mask.shape[0], item.shear)
            h, w = mask.shape
            out = np.zeros((h, w + hi - lo), bool)
            for i, o in enumerate(off):
                out[i, o - lo:o - lo + w] = mask[i]
            return np.ascontiguousarray(out.T), lo
        pal = self.palette(item.sprite, item.light_row, item.remap)
        if item.blend == "half":
            src = (pal[idx].astype(np.uint16) >> 1)
            return np.ascontiguousarray(mask.T), np.ascontiguousarray(src.transpose(1, 0, 2))
        if item.blend == "alpha":           # `.16a`: src * (a + 1) / 16 + dst * (15 - a) / 16 (Canvas.draw_16a)
            alpha = dec.alpha[:, ::-1] if item.mirrored else dec.alpha
            return (np.ascontiguousarray(mask.T), np.ascontiguousarray(pal[idx].astype(np.uint16).transpose(1, 0, 2)),
                    np.ascontiguousarray(alpha.astype(np.uint16).T))
        h, w = mask.shape
        rgba = np.zeros((h, w, 4), np.uint8)
        rgba[..., :3][mask] = pal[idx[mask]]
        rgba[..., 3][mask] = 255
        surf = pygame.image.frombuffer(rgba.tobytes(), (w, h), "RGBA")
        if pygame.display.get_surface() is not None:
            surf = surf.convert_alpha()
        return surf


def blend_masked(surface, x, y, mask_t, fn):
    """dst = fn(dst) on the surface pixels covered by mask_t (w, h) placed at (x, y),
    clipped to the surface.  `fn(covered (n, 3) uint16, (x0, x1, y0, y1) window into mask_t,
    window mask)` returns the new values."""
    sw, sh = surface.get_size()
    w, h = mask_t.shape
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, sw), min(y + h, sh)
    if x0 >= x1 or y0 >= y1:
        return
    win = (x0 - x, x1 - x, y0 - y, y1 - y)
    m = mask_t[win[0]:win[1], win[2]:win[3]]
    pix = pygame.surfarray.pixels3d(surface)
    region = None
    try:
        region = pix[x0:x1, y0:y1]
        region[m] = fn(region[m].astype(np.uint16), win, m).astype(np.uint8)
    finally:
        region = pix = None


def blend_half(surface, x, y, entry):
    """50 % smoothing overlay: (src >> 1) + (dst >> 1) per channel."""
    mask_t, src_t = entry
    blend_masked(surface, x, y, mask_t,
                 lambda dst, win, m: src_t[win[0]:win[1], win[2]:win[3]][m] + (dst >> 1))


def alpha_mix(src, dst, a):
    """`.16a` blend of one channel (0x45889b): `min(src * (a + 1) / 16 + dst * (15 - a) / 16, 255)`, both terms truncated."""
    return np.minimum(((src * (a + 1)) >> 4) + ((dst * (15 - a)) >> 4), 255)


def blend_alpha(surface, x, y, entry):
    """Alpha sprite on the framebuffer: `entry` = (mask_t, src_t (w, h, 3), alpha_t (w, h)) of `SpriteCache.get`."""
    mask_t, src_t, alpha_t = entry

    def fn(dst, win, m):
        sl = (slice(win[0], win[1]), slice(win[2], win[3]))
        return alpha_mix(src_t[sl][m], dst, alpha_t[sl][m][:, None])
    blend_masked(surface, x, y, mask_t, fn)


def blend_shadow(surface, x, y, entry, level):
    """Shadow: dst * (16 - level) / 16 per channel on the covered pixels."""
    mask_t, lo = entry
    blend_masked(surface, x + lo, y, mask_t, lambda dst, win, m: (dst * (16 - level)) >> 4)
