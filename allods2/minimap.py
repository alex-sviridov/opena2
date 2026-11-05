"""Minimap image of a map (spec: docs/superpowers/specs/2026-10-16-minimap-design.md).

The exe builds it at load (`FUN_004ab96c`): one colour per cell from the 52x14 table
`graphics/interface/MiniMapData.bmp`, border of 8 cells cut off, scaled by a shift `k` chosen
from the map's longer side.  Both the k = -1 2x2 average and the final light pass are built (5-6-5 words, docs/engine/rendering.md 12).
"""

import numpy as np

from .graphics.bmp import load_bmp
from .graphics.palette import pack16, unpack16

TABLE_PATH = "graphics/interface/MiniMapData.bmp"
BORDER = 8                      # cells cut off on every side (CONFIRMED 0x4abb53)


def scale_shift(w, h):
    """The scale shift k of a w x h map: 2**k image pixels per cell (CONFIRMED 0x4abc44)."""
    m = max(w, h)
    if m > 0x90:
        return -1
    if m > 0x50:
        return 0
    if m > 0x30:
        return 1
    return 2


def minimap_size(w, h):
    """(width, height) in pixels of the minimap image of a w x h cell map."""
    k = scale_shift(w, h)
    cw, ch = w - 2 * BORDER, h - 2 * BORDER
    return (cw << k, ch << k) if k >= 0 else (cw >> 1, ch >> 1)


DOT_PALETTE_INDEX = 164         # unit dot colour: u16 at +0x148 of the owner's colour table (0x465f3f)


def load_dot_colors(fs=None):
    """(16, 3) uint8: the minimap dot colour of each human.pal row (palette entry 164; the exe
    reads it from the 16-bit shade table row 8 = x1; modelled as a 5-6-5 round trip, INFERRED)."""
    from .common import as_fs
    from .graphics.palette import load_human_palettes
    from .units import HUMAN_PAL
    rows = load_human_palettes(HUMAN_PAL, as_fs(fs))
    return unpack16(pack16(np.array([np.asarray(r)[DOT_PALETTE_INDEX] for r in rows], np.uint8))).astype(np.uint8)


def load_structure_sizes(fs=None):
    """{structures.reg ID: (TileWidth, TileHeight)}: the size of a structure's minimap dot (vtable
    `+0x20/+0x24` = `0x4620fc`/`0x46211d`, the client footprint; bridges use the size of the map entry)."""
    from .common import as_fs
    from .anim.structures import load_structure_records
    return {i: (r["TileWidth"], r["TileHeight"]) for i, r in load_structure_records(as_fs(fs)).items()
            if not r.get("VariableSize")}


def load_color_table(fs=None):
    """The (14, 52, 3) uint8 colour table, top row first (the loader flips DIB rows)."""
    rgb = load_bmp(TABLE_PATH, fs).rgb
    if rgb.shape[:2] != (14, 52):
        raise ValueError("unexpected MiniMapData.bmp size %r" % (rgb.shape,))
    return rgb


def _words(rgb):
    """RGB888 -> 5-6-5 words (the exe's 16-bit surfaces; truncation INFERRED)."""
    return pack16(rgb)


def minimap_light(heights):
    """The (h, w) terrain light map the exe reads at `map + 0x18` (FUN_004a5dd2) at the default
    daylight (day/night option off): the same array the terrain view lights with."""
    from .graphics import lighting as lt
    day = lt.daylight(0, False)
    return lt.terrain_light(np.asarray(heights).astype(np.int8), day.angle, day.ambient, day.diffuse)


def light_pass(words, light, k):
    """The final channel pass `0x4ac030`-`0x4ac413` (CONFIRMED), on 5-6-5 `words`: per cell block
    (`1 << k` pixels, k = -1 one pixel per 2 x 2 cells) `L = 0x60 - (sum of the four light bytes at
    (x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)) // 4` and per channel `min(max, (c * L) >> 5)`."""
    light = np.asarray(light, np.int64)
    h, w = light.shape
    n = 1 << max(k, 0)
    step = 1 if k >= 0 else 2
    ys = np.arange(BORDER, h - BORDER, step)
    xs = np.arange(BORDER, w - BORDER, step)
    pad = np.zeros((h + 1, w + 1), np.int64)
    pad[:h, :w] = light
    s = pad[np.ix_(ys, xs)] + pad[np.ix_(ys, xs + 1)] + pad[np.ix_(ys + 1, xs)] + pad[np.ix_(ys + 1, xs + 1)]
    lum = 0x60 - s // 4
    if n > 1:
        lum = lum.repeat(n, 0).repeat(n, 1)
    lum = lum[:words.shape[0], :words.shape[1]]
    wd = words.astype(np.int64)
    r = np.minimum(31, ((wd >> 11) & 31) * lum >> 5)
    g = np.minimum(63, ((wd >> 5) & 63) * lum >> 5)
    b = np.minimum(31, (wd & 31) * lum >> 5)
    return ((r << 11) | (g << 5) | b).astype(np.uint16)


def minimap_rgb(cells, table, light=None):
    """(H, W, 3) uint8 minimap of `cells` ((h, w) uint16 tile values; dirt and fog bits are
    ignored) with the colour `table` from `load_color_table`.  Built like `FUN_004ab96c`: 5-6-5
    words, k = -1 as the average of 2 x 2 cells (`(px >> 2) & mask` summed), then the light pass
    with `light` (the (h, w) terrain light, `minimap_light`; None = unlit, for synthetic tests)."""
    cells = np.asarray(cells)
    h, w = cells.shape
    v = cells[BORDER:h - BORDER, BORDER:w - BORDER].astype(np.int64) & 0x1fff
    words = _words(table[13 - (v & 0xf), v >> 4])
    k = scale_shift(w, h)
    if k > 0:
        words = words.repeat(1 << k, 0).repeat(1 << k, 1)
    elif k < 0:
        ow, oh = (w - 2 * BORDER) >> 1, (h - 2 * BORDER) >> 1
        q = (words.astype(np.uint32) >> 2) & 0x39e7       # 7 << 11 | 15 << 5 | 7
        words = (q[0:2 * oh:2, 0:2 * ow:2] + q[0:2 * oh:2, 1:2 * ow:2]
                 + q[1:2 * oh:2, 0:2 * ow:2] + q[1:2 * oh:2, 1:2 * ow:2]).astype(np.uint16)
    if light is not None:
        words = light_pass(words, light, k)
    return np.ascontiguousarray(unpack16(words))
