"""Incremental scene composite: reuse the previous frame instead of redrawing terrain and every sprite (docs/engine/architecture.md, Renderer speed).

The pre-fog image of a frame (terrain cells, then the draw list in order, onto black) is a pure function of the terrain items and the draw items.
Every item is identified by its content with its screen position taken back to world pixels (`ix + sx`), so two frames are comparable when
the camera moved.  `SceneMemo.compose` keeps a copy of the last composite and, for the next frame, shifts it by the camera step and redraws only
the **dirty rectangles**: the strips that scrolled in, and the bounding boxes (at the old and at the new place) of every terrain cell and draw
item that is not in both frames.  Inside a dirty rectangle the pixels are rebuilt from black: every terrain cell and every draw item whose box
touches it is drawn in list order with the output clipped to the rectangle (blits through the surface clip, the shadow / half / alpha blends with
a clip mask), so the result is the full redraw's pixel for pixel; outside every dirty rectangle all items that cover a pixel are the same, in the
same order (the draw list is sorted by `depth`, which is part of the identity), over the same terrain, so the old pixel is still right.  Anything
the analysis cannot cover (debug overlays, a changed terrain version, another size, a huge dirty area) takes the full redraw."""

from collections import Counter
from operator import attrgetter

import numpy as np
import pygame

from allods2.anim.lens import apply_lens
from engine.view import TerrainItem
from engine.view.drawlist import shadow_offsets

from .sprites import frame_alpha, frame_half, frame_shadow

_REST = attrgetter("kind", "entity", "sprite", "frame", "w", "h", "mirrored", "blend", "light_row", "shadow_level", "remap", "gray", "depth",
                   "shear", "text", "bar")
MAX_RECTS = 48
MAX_AREA = 0.45             # of the frame: past this a full redraw is cheaper than the passes
_FAR = -(1 << 30)


def draw_items(frame, caches, items, only=None, clip=None):
    """Draw `items` (or those at the indices `only`) in order onto the frame; `clip` = (x0, y0, x1, y1) limits every write to that box."""
    surface = frame.surf
    blit, sprites = surface.blit, caches.sprites
    from .render import draw_bar, _overlay          # late: render imports this module
    seq = items if only is None else [items[i] for i in only]
    for it in seq:
        kind = it.kind
        if kind == "sprite" or kind == "shadow":
            val = sprites.get(it)
            if val is None:
                continue
            if kind == "shadow":
                frame_shadow(frame, it.sx, it.sy, val, it.shadow_level, clip)
            elif it.blend == "half":
                frame_half(frame, it.sx, it.sy, val, clip)
            elif it.blend == "alpha":
                frame_alpha(frame, it.sx, it.sy, val, clip)
            else:
                blit(val, (it.sx, it.sy))
        elif kind == "bar":
            draw_bar(surface, it, caches.ball)
        elif kind == "lens":
            apply_lens(frame.arr, it.sx, it.sy)
        else:
            _overlay(surface, caches, it)


def full_scene(frame, caches, terrain_items, items, cy):
    """The whole pre-fog image: black, the terrain items in order (as one cached layer when the cache has it), the draw items in order."""
    surface = frame.surf
    surface.fill((0, 0, 0))
    terrain = caches.terrain
    layer = getattr(terrain, "layer", None)
    if layer is not None:
        surface.blit(layer(terrain_items, cy, surface), (0, 0))
    else:
        for item in terrain_items:
            val = terrain.get(item)
            if val is not None:
                surface.blit(val[0], (item.sx, val[1] - cy))
    draw_items(frame, caches, items)


def _bbox(it, ball):
    """(x0, y0, x1, y1) of everything the item writes, in its frame's screen coordinates, or None for kinds the analysis does not cover."""
    kind, x, y = it.kind, it.sx, it.sy
    if kind == "sprite":
        return x, y, x + it.w, y + it.h
    if kind == "shadow":
        _, lo, hi = shadow_offsets(it.h, it.shear)
        return x + lo, y, x + it.w + hi, y + it.h
    if kind == "bar":
        bw, bh = ball.get_size() if ball is not None else (0, 0)
        return x, y, max(x + it.w, x + it.w - 4 + bw), y + max(4, bh)
    return None


def _area(r):
    return (r[2] - r[0]) * (r[3] - r[1])


def _merge(rects):
    """Rectangles that overlap and fit their bounding box well (box area <= 1.25 x the sum) merged into it, until none does; a dirty area may
    be drawn twice (a pass rebuilds its pixels from black), so overlapping rectangles that stay apart are fine."""
    rects = sorted(set(rects), key=_area, reverse=True)
    out = []
    for r in rects:
        for o in out:                                   # inside a bigger one
            if o[0] <= r[0] and o[1] <= r[1] and o[2] >= r[2] and o[3] >= r[3]:
                break
        else:
            out.append(r)
    again = True
    while again and len(out) > 1:
        again = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                a, b = out[i], out[j]
                if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                    u = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
                    if _area(u) <= 1.25 * (_area(a) + _area(b)):
                        out[i] = u
                        del out[j]
                        again = True
                        break
            if again:
                break
    return out


class SceneMemo:
    """The last composite and what it was made of (see the module docstring).  One per `Caches`."""

    def __init__(self):
        self.snap = None
        self.state = None               # (size, terrain version, sprites, ball, cx, cy, tset, tcount, icount, items by key)
        self.geo = {}                   # terrain cell key -> (world x, world y0, w, h) or None
        self.final = self.final_key = None      # the last fogged output (a `Frame`), kept while the camera stands still
        self.final_cam = None
        self.full = self.incremental = self.reused = 0      # counters (tests, tuning)

    def _geom(self, terrain, key):
        g = self.geo.get(key, False)
        if g is False:
            val = terrain.get(TerrainItem(key[0], key[1], key[2], 0, key[3]))
            g = None if val is None else (key[0] * 32, val[1], val[0].get_width(), val[0].get_height())
            if len(self.geo) > 30000:
                self.geo.clear()
            self.geo[key] = g
        return g

    def compose(self, frame, caches, terrain_items, items, camera):
        """Draw the pre-fog image of the frame into `frame` (its surface and words), the full way or incrementally; remember it.
        Returns True when nothing changed against the last frame (same camera pixel, no dirty rectangle): then `frame` is **not** written, the
        caller either reuses its own copy of that frame's output or calls `restore`."""
        terrain = caches.terrain
        tv = getattr(terrain, "tv", None)
        W, H = frame.w, frame.h
        cx, cy = camera.ix, camera.iy
        ball = caches.ball
        keys = None
        ok = tv is not None and caches.sprites is not None
        if ok:
            keys = []
            ap = keys.append
            for it in items:
                if it.kind not in ("sprite", "shadow", "bar"):
                    ok = False
                    break
                ap((it.sx + cx, it.sy + cy, _REST(it)))
        if not ok:
            self.state = None
            full_scene(frame, caches, terrain_items, items, cy)
            return
        tkeys = [(t.col, t.row, t.phase, t.lit) for t in terrain_items]
        tset = set(tkeys)
        version = tv.version
        st = self.state
        sig = ((W, H), version, caches.sprites, ball)
        rects = None
        if st is not None and st[:4] == sig and self.snap is not None and abs(cx - st[4]) < W and abs(cy - st[5]) < H:
            rects = self._dirty(terrain, st, cx, cy, W, H, ball, tkeys, tset, keys, items)
        if rects is None:
            self.full += 1
            full_scene(frame, caches, terrain_items, items, cy)
        else:
            self.incremental += 1
            if not rects and cx == st[4] and cy == st[5]:
                self.reused += 1
                return True
            self._patch(frame, caches, terrain_items, items, tkeys, keys, rects, st, cx, cy, ball)
        if self.snap is None or self.snap.shape != frame.arr.shape:
            self.snap = np.empty_like(frame.arr)
        np.copyto(self.snap, frame.arr)
        by_key = {}
        for k, it in zip(keys, items):
            by_key[k] = it
        self.state = (sig[0], version, caches.sprites, ball, cx, cy, tset, Counter(keys), by_key)

    def keep_final(self, frame, key, camera):
        """Remember the fogged output when the camera did not move since the last frame (the frames that can repeat); drop it otherwise."""
        cam = (camera.ix, camera.iy)
        if cam != self.final_cam or self.state is None:
            self.final_key = self.final = None
        else:
            from .sprites import Frame
            if self.final is None or (self.final.w, self.final.h) != (frame.w, frame.h):
                self.final = Frame(frame.w, frame.h)
            np.copyto(self.final.arr, frame.arr)
            self.final_key = key
        self.final_cam = cam

    def restore(self, frame):
        """Put the remembered pre-fog image into `frame`."""
        np.copyto(frame.arr, self.snap)

    def _dirty(self, terrain, st, cx, cy, W, H, ball, tkeys, tset, keys, items):
        """The dirty rectangles (new screen coordinates) of this frame against the remembered one, or None when a full redraw is better."""
        ocx, ocy, otset, ocount, oitems = st[4:9]
        dx, dy = cx - ocx, cy - ocy                  # new[y, x] = old[y + dy, x + dx]
        rects = []
        if dx or dy:
            ox0, ox1, oy0, oy1 = max(0, -dx), min(W, W - dx), max(0, -dy), min(H, H - dy)
            if oy0 > 0:
                rects.append((0, 0, W, oy0))
            if oy1 < H:
                rects.append((0, oy1, W, H))
            if ox0 > 0:
                rects.append((0, oy0, ox0, oy1))
            if ox1 < W:
                rects.append((ox1, oy0, W, oy1))
        sx, sy = ocx - cx, ocy - cy                  # old screen -> new screen
        if tset != otset:
            for k in tset - otset:
                g = self._geom(terrain, k)
                if g is not None:
                    rects.append((g[0] - cx, g[1] - cy, g[0] - cx + g[2], g[1] - cy + g[3]))
            for k in otset - tset:
                g = self._geom(terrain, k)
                if g is not None:
                    rects.append((g[0] - cx, g[1] - cy, g[0] - cx + g[2], g[1] - cy + g[3]))
        left = dict(ocount)
        for i, k in enumerate(keys):
            c = left.get(k, 0)
            if c:
                left[k] = c - 1
            else:
                b = _bbox(items[i], ball)
                rects.append(b)
        for k, c in left.items():
            if c > 0:
                b = _bbox(oitems[k], ball)
                rects.append((b[0] + sx, b[1] + sy, b[2] + sx, b[3] + sy))
        clipped = []
        for x0, y0, x1, y1 in rects:
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
            if x0 < x1 and y0 < y1:
                clipped.append((x0, y0, x1, y1))
        rects = _merge(clipped)
        if len(rects) > MAX_RECTS or sum((r[2] - r[0]) * (r[3] - r[1]) for r in rects) > MAX_AREA * W * H:
            return None
        return rects

    def _patch(self, frame, caches, terrain_items, items, tkeys, keys, rects, st, cx, cy, ball):
        W, H = frame.w, frame.h
        ocx, ocy = st[4], st[5]
        dx, dy = cx - ocx, cy - ocy
        arr = frame.arr
        x0, x1, y0, y1 = max(0, -dx), min(W, W - dx), max(0, -dy), min(H, H - dy)       # the fog pass has overwritten the frame: copy back even if still
        arr[y0:y1, x0:x1] = self.snap[y0 + dy:y1 + dy, x0 + dx:x1 + dx]
        if not rects:
            return
        terrain = caches.terrain
        surface = frame.surf
        tg = np.array([self._geom(terrain, k) or (_FAR, _FAR, 0, 0) for k in tkeys], np.int64).reshape(-1, 4)
        tx0, ty0 = tg[:, 0] - cx, tg[:, 1] - cy
        tx1, ty1 = tx0 + tg[:, 2], ty0 + tg[:, 3]
        bx = np.array([_bbox(it, ball) for it in items], np.int64).reshape(-1, 4)
        try:
            for r in rects:
                x0, y0, x1, y1 = r
                surface.set_clip(pygame.Rect(x0, y0, x1 - x0, y1 - y0))
                surface.fill((0, 0, 0), (x0, y0, x1 - x0, y1 - y0))
                for i in np.flatnonzero((tx0 < x1) & (tx1 > x0) & (ty0 < y1) & (ty1 > y0)):
                    item = terrain_items[i]
                    val = terrain.get(item)
                    if val is not None:
                        surface.blit(val[0], (item.sx, val[1] - cy))
                hit = np.flatnonzero((bx[:, 0] < x1) & (bx[:, 2] > x0) & (bx[:, 1] < y1) & (bx[:, 3] > y0))
                if len(hit):
                    draw_items(frame, caches, items, hit.tolist(), r)
        finally:
            surface.set_clip(None)
