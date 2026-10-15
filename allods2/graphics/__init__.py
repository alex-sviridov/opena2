"""Allods 2 graphics formats, decoded the way allods2.exe does.

Specs: docs/formats/.
"""

from .bmp import Bitmap, load_bmp
from .canvas import Canvas
from .palette import (Palette, code_palettes, code_ramps16, daylight_tint,
                      grayscale_palette, load_human, load_human_palettes, load_pal,
                      load_pal_file, load_palettes, pack16, read_palette,
                      shade_table, unpack16)
from .png import write_png
from .sprites import (PALETTE_FLAG, Decoded, Sprite, SpriteFile, alpha_coverage,
                      check_sprite, decode, decode_16, decode_16a, decode_256,
                      decode_smooth, guess_kind, to_rgba)

__all__ = [
    "Bitmap", "Canvas", "Decoded", "PALETTE_FLAG", "Palette", "Sprite", "SpriteFile",
    "alpha_coverage", "check_sprite", "code_palettes", "code_ramps16",
    "daylight_tint", "decode", "decode_16", "decode_16a", "decode_256",
    "decode_smooth", "grayscale_palette", "guess_kind", "load_bmp",
    "load_human", "load_human_palettes", "load_pal", "load_pal_file",
    "load_palettes", "pack16", "read_palette", "shade_table", "to_rgba",
    "unpack16", "write_png",
]
