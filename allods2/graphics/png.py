"""PNG input/output, the a2mgr.dll paper-doll PNG layer blend, the exe's
paper-doll layer order (FUN_0046dd6a) and a2mgr's menu PNG blit.

Spec: docs/formats/png.md.
"""

import numpy as np
from PIL import Image

PAPERDOLL_W, PAPERDOLL_H = 160, 240     # a2mgr draws a PNG layer only at this size


def write_png(path, image):
    """image: (h, w, 3) RGB or (h, w, 4) RGBA uint8 array."""
    Image.fromarray(np.ascontiguousarray(image, np.uint8)).save(path)


def load_png(path):
    """(h, w, 4) uint8 straight (non-premultiplied) RGBA, as GDI+ hands
    a2mgr 32bpp ARGB pixels."""
    with Image.open(path) as im:
        return np.asarray(im.convert("RGBA")).copy()


def blend_png_layer(dst, rgba):
    """a2mgr FUN_10010d70: composite one 160x240 RGBA layer into the
    paper-doll's 16-bit RGB565 buffer `dst` ((240, 160) uint16), in place.

    Per pixel, with source channels r5 = R >> 3, g6 = G >> 2, b5 = B >> 3:
      alpha 0     unchanged
      alpha 255   (max(r5, 1), max(g6, 1), max(b5, 1))
      otherwise   t = float(A / 255.0); c = int(float(dst_c·(1.0 − t) +
                  float(src_c·t))), then c < 2 -> 1, else min(c, 31 / 63)
    (SSE: the dst term in double, the src term in single, sum rounded to
    single, then truncated.)
    A layer of any other size is not drawn.  Returns dst.
    """
    rgba = np.asarray(rgba, np.uint8)
    if rgba.shape[:2] != (PAPERDOLL_H, PAPERDOLL_W):
        return dst
    a = rgba[..., 3]
    src = (rgba[..., 0] >> 3, rgba[..., 1] >> 2, rgba[..., 2] >> 3)
    d = dst.astype(np.uint32)
    old = ((d >> 11) & 0x1F, (d >> 5) & 0x3F, d & 0x1F)
    t = (a / 255.0).astype(np.float32)
    u = 1.0 - t.astype(np.float64)
    out = []
    for s, o, top in zip(src, old, (31, 63, 31)):
        src_term = (s.astype(np.float32) * t).astype(np.float64)
        blended = (o.astype(np.float64) * u + src_term).astype(np.float32).astype(np.int32)
        blended = np.where(blended < 2, 1, np.minimum(blended, top))
        opaque = np.maximum(s, 1).astype(np.int32)
        out.append(np.where(a == 255, opaque, blended))
    packed = ((out[0] << 11) | (out[1] << 5) | out[2]).astype(np.uint16)
    np.copyto(dst, packed, where=a != 0)
    return dst


def png_hit_mask(mask, rgba, layer_id):
    """a2mgr FUN_10010d00: write `layer_id` into the (240, 160) byte mask
    where the layer's alpha is >= 127 (INFERRED: the item under the mouse)."""
    rgba = np.asarray(rgba, np.uint8)
    if rgba.shape[:2] == (PAPERDOLL_H, PAPERDOLL_W):
        mask[rgba[..., 3] > 0x7E] = layer_id
    return mask


# --- compositing order (FUN_0046dd6a) ------------------------------------------

TWO_HANDED_CLASSES = ("bowman", "archer", "xbowman", "axeman2h", "swordsman2h", "mage_st")


def doll_layer_order(mage, two_handed):
    """Draw order after the horse / hero-back layers: ("B",) body, ("P", n)
    primary and ("S", n) secondary layer of slot n.  two_handed = slot 0's
    item class is in TWO_HANDED_CLASSES (fighters only)."""
    if mage:
        return [("P", 7), ("B",), ("P", 11), ("P", 9), ("S", 9), ("P", 3), ("S", 3),
                ("P", 6), ("P", 4), ("P", 0), ("P", 5), ("S", 7)]
    out = [("B",), ("P", 11), ("P", 10), ("P", 6), ("P", 3), ("P", 4), ("P", 8), ("P", 9)]
    if not two_handed:
        out.append(("P", 0))
    out += [("P", 7), ("S", 3), ("P", 5), ("S", 8), ("S", 9)]
    out.append(("P", 0) if two_handed else ("P", 1))
    return out


def doll_mask_order(mage, two_handed):
    """Hit-mask order: (layer, id) with id = slot + 1, body 0.  Mages add
    slot 8 (never drawn); fighters leave out the body."""
    order = doll_layer_order(mage, two_handed)
    if mage:
        order.insert(order.index(("P", 0)), ("P", 8))
    else:
        order.remove(("B",))
    return [(layer, 0 if layer == ("B",) else layer[1] + 1) for layer in order]


# --- a2mgr menu art (FUN_1000f790) ---------------------------------------------

def blend_menu_png(dst, rgba, x, y, hard=False, clip=None):
    """Draw a whole RGBA image at (x, y) into an RGB565 surface (H × W
    uint16, in place) like a2mgr FUN_1000f760.  Negative x / y skip that
    many source columns / rows; the draw is dropped when it misses `clip`
    (left, top, right, bottom; default the surface) or would cross the
    surface's right edge.  hard: alpha > 127 is opaque, the rest skipped."""
    rgba = np.asarray(rgba, np.uint8)
    ih, iw = rgba.shape[:2]
    H, W = dst.shape
    sx, x = (-x, 0) if x < 0 else (0, x)
    sy, y = (-y, 0) if y < 0 else (0, y)
    w, h = iw - sx, ih - sy
    left, top, right, bottom = clip or (0, 0, W, H)
    if x > right or y > bottom or x + w < left or y + h < top or W - w - x < 0:
        return dst
    if w <= 0 or h <= 0:
        return dst
    src = rgba[sy:sy + h, sx:sx + w]
    h = min(h, H - y)                        # the game does not check the bottom
    src = src[:h]
    a = src[..., 3]
    if hard:
        draw = a > 0x7F
        a = np.where(draw, 255, 0).astype(np.uint8)
    else:
        draw = a != 0
    d = dst[y:y + h, x:x + w].astype(np.uint32)
    old = ((d >> 11) & 0x1F, (d >> 5) & 0x3F, d & 0x1F)
    srcc = (src[..., 0] >> 3, src[..., 1] >> 2, src[..., 2] >> 3)
    t = (a / 255.0).astype(np.float32)
    u = 1.0 - t.astype(np.float64)
    out = []
    for s, o, top_ in zip(srcc, old, (31, 63, 31)):
        v = (o.astype(np.float64) * u + (s.astype(np.float32) * t).astype(np.float64))
        v = np.minimum(v.astype(np.float32), np.float32(top_)).astype(np.int32)
        out.append(np.where(a == 255, s.astype(np.int32), v))
    packed = ((out[0] << 11) | (out[1] << 5) | out[2]).astype(np.uint16)
    np.copyto(dst[y:y + h, x:x + w], packed, where=draw)
    return dst
