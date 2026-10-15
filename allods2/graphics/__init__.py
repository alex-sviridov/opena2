"""Allods 2 graphics formats, decoded the way allods2.exe does.

Specs: docs/formats/.
"""

from .bmp import Bitmap, load_bmp
from .canvas import Canvas
from .lighting import (Daylight, daylight, daylight_tint, lit_terrain_corner,
                       object_light_row, object_light_row_lit, projectile_light,
                       shadow_angle, shadow_pixel, shadow_row_offsets, shadow_shear,
                       stamp_light, terrain_light)
from .palette import (Palette, code_palettes, code_ramps16,
                      grayscale_palette, load_human, load_human_palettes, load_pal,
                      load_pal_file, load_palettes, pack16, player_text_ramp,
                      read_palette,
                      shade_table, unpack16)
from .png import write_png
from .sprites import (PALETTE_FLAG, Decoded, Sprite, SpriteFile, alpha_coverage,
                      check_sprite, decode, decode_16, decode_16a, decode_256,
                      decode_smooth, guess_kind, to_rgba)

__all__ = [
    "Bitmap", "Canvas", "Daylight", "Decoded", "PALETTE_FLAG", "Palette", "Sprite", "SpriteFile",
    "alpha_coverage", "check_sprite", "code_palettes", "code_ramps16",
    "daylight", "daylight_tint", "decode", "decode_16", "decode_16a", "decode_256",
    "decode_smooth", "grayscale_palette", "guess_kind", "load_bmp",
    "load_human", "load_human_palettes", "load_pal", "load_pal_file",
    "lit_terrain_corner", "load_palettes", "object_light_row",
    "object_light_row_lit", "projectile_light", "shadow_angle", "shadow_pixel",
    "shadow_row_offsets", "shadow_shear", "stamp_light", "pack16", "player_text_ramp",
    "read_palette", "shade_table", "terrain_light", "to_rgba",
    "unpack16", "write_png",
]
