"""PNG input/output, and the a2mgr.dll paper-doll PNG layer blend.

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
      otherwise   t = A / 255 (float); c = int(dst_c·(1 − t) + src_c·t),
                  then c < 2 -> 1, else min(c, 31 / 63)
    A layer of any other size is not drawn.  Returns dst.
    """
    rgba = np.asarray(rgba, np.uint8)
    if rgba.shape[:2] != (PAPERDOLL_H, PAPERDOLL_W):
        return dst
    a = rgba[..., 3]
    src = (rgba[..., 0] >> 3, rgba[..., 1] >> 2, rgba[..., 2] >> 3)
    d = dst.astype(np.uint32)
    old = ((d >> 11) & 0x1F, (d >> 5) & 0x3F, d & 0x1F)
    t = a.astype(np.float32) / np.float32(255.0)
    u = np.float32(1.0) - t
    out = []
    for s, o, top in zip(src, old, (31, 63, 31)):
        blended = (o.astype(np.float32) * u + s.astype(np.float32) * t).astype(np.int32)
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
