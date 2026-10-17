"""Minimap image of a map (spec: docs/superpowers/specs/2026-10-16-minimap-design.md).

The exe builds it at load (`FUN_004ab96c`): one colour per cell from the 52x14 table
`graphics/interface/MiniMapData.bmp`, border of 8 cells cut off, scaled by a shift `k` chosen
from the map's longer side.  Cheap variant: no 2x2 average for k = -1, no final channel pass.
"""

import numpy as np

from .graphics.bmp import load_bmp

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
    reads it from the 16-bit shade table row 8 = x1, so 5-6-5 rounding is not reproduced)."""
    from .common import as_fs
    from .graphics.palette import load_human_palettes
    from .units import HUMAN_PAL
    rows = load_human_palettes(HUMAN_PAL, as_fs(fs))
    return np.array([np.asarray(r)[DOT_PALETTE_INDEX] for r in rows], np.uint8)


def load_color_table(fs=None):
    """The (14, 52, 3) uint8 colour table, top row first (the loader flips DIB rows)."""
    rgb = load_bmp(TABLE_PATH, fs).rgb
    if rgb.shape[:2] != (14, 52):
        raise ValueError("unexpected MiniMapData.bmp size %r" % (rgb.shape,))
    return rgb


def minimap_rgb(cells, table):
    """(H, W, 3) uint8 minimap of `cells` ((h, w) uint16 tile values; dirt and fog bits are
    ignored) with the colour `table` from `load_color_table`."""
    cells = np.asarray(cells)
    h, w = cells.shape
    v = cells[BORDER:h - BORDER, BORDER:w - BORDER].astype(np.int64) & 0x1fff
    rgb = table[13 - (v & 0xf), v >> 4]
    k = scale_shift(w, h)
    if k > 0:
        rgb = rgb.repeat(1 << k, 0).repeat(1 << k, 1)
    elif k < 0:
        rgb = rgb[::2, ::2][:(h - 2 * BORDER) >> 1, :(w - 2 * BORDER) >> 1]
    return np.ascontiguousarray(rgb)
