"""Sprite cache: draw items -> pygame surfaces or numpy blend masks, LRU.

Opaque sprites become RGBA surfaces (alpha 255 where the game writes a pixel) that
`Surface.blit` copies exactly.  The 50 % smoothing overlay and the shadows depend on
the destination, so their cache entries are masks for numpy arithmetic on the
framebuffer (the core's formulas: `Canvas.draw_256_translucent`, `Canvas.draw_darken`).
"""

from collections import OrderedDict

import numpy as np
import pygame

from allods2.graphics.palette import BRIGHT2, GRAY, grayscale_palette, shade_table

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

    def palette(self, sprite, light_row, remap=None, gray=False):
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
        if gray:                            # Stone Curse (`FUN_004632a1`): the GRAY table (16 levels, no tint) in place of BRIGHT2; unlit = row 8 (x1)
            tkey = main + (remap, "gray")
            t = self._tables.get(tkey)
            if t is None:
                t = self._tables[tkey] = shade_table(pal, LIGHT_LEVELS, GRAY, (0, 0, 0))
            return t[min(8 if light_row is None else light_row, LIGHT_LEVELS - 1)]
        if light_row is None:
            return pal
        tkey = main + (remap,)
        t = self._tables.get(tkey)
        if t is None:
            t = self._tables[tkey] = shade_table(pal, LIGHT_LEVELS, BRIGHT2, self.tint)
        return t[min(light_row, LIGHT_LEVELS - 1)]

    def get(self, item):
        """Cache entry of a "sprite" or "shadow" item: a Surface (opaque), a `SparseMask` for blend "half" and for
        a shadow (the sheared box starts `dx` left of the sprite), (mask_t, src_t, alpha_t) for "alpha" (arrays (w, h),
        x first, as `pixels3d`); None when the frame is missing."""
        shadow = item.kind == "shadow"
        key = (item.sprite, item.frame, item.mirrored, "shadow" if shadow else item.blend,
               None if shadow else item.light_row, item.shear if shadow else 0,
               None if shadow else item.remap, False if shadow else item.gray)
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
            return SparseMask(out, lo)
        pal = self.palette(item.sprite, item.light_row, item.remap, item.gray)
        if item.blend == "half":
            return SparseMask(mask, 0, pack_rgb(pal[idx] >> 1))
        if item.blend == "alpha":           # `.16a`: src * (a + 1) / 16 + dst * (15 - a) / 16 (Canvas.draw_16a)
            alpha = dec.alpha[:, ::-1] if item.mirrored else dec.alpha
            return (np.ascontiguousarray(mask.T), np.ascontiguousarray(pal[idx].astype(np.uint16).transpose(1, 0, 2)),
                    np.ascontiguousarray(alpha.astype(np.uint16).T))
        h, w = mask.shape
        rgba = np.zeros((h, w, 4), np.uint8)
        rgba[..., :3][mask] = pal[idx[mask]]
        rgba[..., 3][mask] = 255
        surf = pygame.image.frombuffer(rgba.tobytes(), (w, h), "RGBA")
        return surf


class Frame:
    """A software framebuffer the numpy blends write without locking: `arr` (h, w) uint32 words whose bytes are R, G, B, X
    (pygame "RGBX") and `surf`, a surface sharing that memory, so `Surface.blit` and the blends compose in list order."""

    _all = {}

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.arr = np.zeros((h, w), np.uint32)
        self.flat = self.arr.reshape(-1)
        self.bytes = self.arr.view(np.uint8).reshape(h, w, 4)       # [..., :3] = R, G, B
        self.surf = pygame.image.frombuffer(self.arr, (w, h), "RGBX")
        self.flat8 = self.arr.view(np.uint8).reshape(-1)            # every byte: R, G, B, X of word 0, then word 1, ...

    @classmethod
    def get(cls, w, h):
        f = cls._all.get((w, h))
        if f is None:
            if len(cls._all) > 4:
                cls._all.clear()
            f = cls._all[(w, h)] = cls(w, h)
        return f


def _word(*b):
    return int(np.array(b, np.uint8).view(np.uint32)[0])


RB, GG, LOW7 = (np.uint32(_word(*b)) for b in ((255, 0, 255, 0), (0, 255, 0, 0), (127, 127, 127, 0)))   # channel fields of a word


def pack_rgb(rgb):
    """(..., 3) uint8 colours -> uint32 words as the Frame stores them."""
    out = np.zeros(rgb.shape[:-1] + (4,), np.uint8)
    out[..., :3] = rgb
    return out.view(np.uint32)[..., 0]


class SparseMask:
    """The covered pixels of a shadow or half-overlay entry: rows `ys`, columns `xs` inside a w x h box that starts `dx`
    left of the sprite, with their packed source words `vals` (half) or None (shadow).  Most of the box is empty, so the
    blends gather / scatter only these; the flat framebuffer indices are cached per frame width."""

    __slots__ = ("ys", "xs", "vals", "dx", "w", "h", "fw", "base", "memo", "memo3")

    def __init__(self, mask, dx=0, vals=None):
        self.ys, self.xs = np.nonzero(mask)
        self.vals = None if vals is None else vals[self.ys, self.xs]
        self.dx, (self.h, self.w), self.fw, self.base = dx, mask.shape, -1, None
        self.memo = {}
        self.memo3 = {}

    def clipped(self, frame, x, y, clip):
        """`indices` limited to the box `clip` = (x0, y0, x1, y1) (inside the frame); None when nothing is left."""
        x0 = x + self.dx
        if x0 >= clip[0] and y >= clip[1] and x0 + self.w <= clip[2] and y + self.h <= clip[3]:
            return self.indices(frame, x, y)             # the whole box is inside: the memoised path
        X, Y = self.xs + (x + self.dx), self.ys + y
        keep = (X >= clip[0]) & (X < clip[2]) & (Y >= clip[1]) & (Y < clip[3])
        return (Y[keep] * frame.w + X[keep], keep) if keep.any() else None

    def indices(self, frame, x, y):
        """(flat indices, keep or None) of the covered pixels inside the frame for the sprite at (x, y), or None."""
        x += self.dx
        fw, fh, w, h = frame.w, frame.h, self.w, self.h
        if x >= fw or y >= fh or x + w <= 0 or y + h <= 0:
            return None
        if self.fw != fw:
            self.fw, self.base = fw, self.ys * fw + self.xs
            self.memo.clear()
            self.memo3.clear()
        key = (x, y, fh)
        r = self.memo.get(key)                  # a still camera draws the same sprite at the same place every frame
        if r is not None:
            return r
        if x >= 0 and y >= 0 and x + w <= fw and y + h <= fh:
            r = self.base + (y * fw + x), None
        else:
            X, Y = self.xs + x, self.ys + y
            keep = (X >= 0) & (X < fw) & (Y >= 0) & (Y < fh)
            r = Y[keep] * fw + X[keep], keep
        if len(self.memo) >= 24:
            self.memo.clear()
        self.memo[key] = r
        return r

    def indices3(self, frame, x, y):
        """Byte indices of the R, G, B bytes of the covered pixels (`indices` x 4 + 0..2), memoised like `indices`; None when nothing is covered."""
        r = self.indices(frame, x, y)
        if r is None:
            return None
        key = (x + self.dx, y, frame.h)
        i3 = self.memo3.get(key)
        if i3 is None:
            if len(self.memo3) >= 24:
                self.memo3.clear()
            i3 = self.memo3[key] = _rgb_bytes(r[0])
        return i3


def frame_half(frame, x, y, entry, clip=None):
    """50 % smoothing overlay: (src >> 1) + (dst >> 1) per channel; src is already halved (<= 0x7F), so the fields add
    without carries.  `clip` = (x0, y0, x1, y1): write only inside it."""
    r = entry.indices(frame, x, y) if clip is None else entry.clipped(frame, x, y, clip)
    if r is None:
        return
    idx, keep = r
    flat = frame.flat
    flat[idx] = (entry.vals if keep is None else entry.vals[keep]) + ((flat.take(idx) >> 1) & LOW7)


_SHADOW_LUT = np.array([[(v * (16 - k)) >> 4 for v in range(256)] for k in range(17)], np.uint8)


_RGB = np.arange(3, dtype=np.intp)


def _rgb_bytes(idx):
    """Flat word indices -> the byte indices of their R, G, B bytes."""
    return (idx[:, None] * 4 + _RGB).ravel()


def frame_shadow(frame, x, y, entry, level, clip=None):
    """Shadow: dst * (16 - level) / 16 per channel on the covered pixels, one byte table over the R, G, B bytes (the X byte is left alone, it is 0)."""
    if clip is None:
        i3 = entry.indices3(frame, x, y)
    else:
        r = entry.clipped(frame, x, y, clip)
        i3 = None if r is None else _rgb_bytes(r[0])
    if i3 is None:
        return
    b = frame.flat8
    b[i3] = _SHADOW_LUT[level].take(b.take(i3))


def alpha_mix(src, dst, a):
    """`.16a` blend of one channel (0x45889b): `min(src * (a + 1) / 16 + dst * (15 - a) / 16, 255)`, both terms truncated."""
    return np.minimum(((src * (a + 1)) >> 4) + ((dst * (15 - a)) >> 4), 255)


def frame_alpha(frame, x, y, entry, clip=None):
    """Alpha sprite: `entry` = (mask_t, src_t (w, h, 3), alpha_t (w, h)) of `SpriteCache.get` (x first)."""
    mask_t, src_t, alpha_t = entry
    w, h = mask_t.shape
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, frame.w), min(y + h, frame.h)
    if clip is not None:
        x0, y0, x1, y1 = max(x0, clip[0]), max(y0, clip[1]), min(x1, clip[2]), min(y1, clip[3])
    if x0 >= x1 or y0 >= y1:
        return
    sl = (slice(x0 - x, x1 - x), slice(y0 - y, y1 - y))
    region = frame.bytes[y0:y1, x0:x1, :3]
    new = alpha_mix(src_t[sl].transpose(1, 0, 2), region.astype(np.uint16), alpha_t[sl].T[..., None])
    np.copyto(region, new, where=mask_t[sl].T[..., None], casting="unsafe")


def _on_surface(fn):
    """The same blend on any surface: copy it into a Frame, blend, copy back (tests, one-off use)."""
    def blend(surface, *args):
        f = Frame.get(*surface.get_size())
        f.surf.blit(surface, (0, 0))
        fn(f, *args)
        surface.blit(f.surf, (0, 0))
    blend.__doc__ = fn.__doc__
    return blend


blend_half, blend_shadow, blend_alpha = _on_surface(frame_half), _on_surface(frame_shadow), _on_surface(frame_alpha)
