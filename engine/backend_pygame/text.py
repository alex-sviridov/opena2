"""Text drawing with the game's own fonts (docs/formats/fonts.md): the single entry point.

`draw_text` keeps its G3b signature; `font` picks font1..4, `colour` is an RGB
tuple (a 16-step ramp, black to the colour, like the exe's code tables) or the
name of one of the game's tables (`TABLES`), text is a str (see allods2.text)
or font bytes.  Text gets the exe's 1 px drop shadow.  Without an install
(synthetic tests) pygame's bundled font stands in.
"""

from collections import OrderedDict

import numpy as np
import pygame

from allods2 import graphics as gfx
from allods2.common import game_fs, have_install
from allods2.text import font_bytes

DEFAULT_FONT = 2        # small UI font; font1 = dialogs, font3 = digits/capitals, font4 = titles
SHADOW_OFFSET = 1       # FUN_0045d536 callers: off = 1
SHADOW_COLOUR = (8, 8, 8)
CACHE_SIZE = 512

# Colour tables of palettes.md section 6 by role -> code-table address (code_ramps16).
TABLES = {"normal": 0x620928, "highlight": 0x61fa80, "label": 0x620d90, "value": 0x620d70,
          "header": 0x620d50, "tooltip": 0x6200e0, "red": 0x620ea0, "yellow": 0x620e10,
          "green": 0x620508, "gold": 0x620ec0}

_fonts = {}
_surfaces = OrderedDict()
_fallback = None


def game_font(n):
    """Font n (1..4) from the install, or None without one."""
    if n not in _fonts:
        _fonts[n] = gfx.Font.load("graphics/font%d/font%d" % (n, n), game_fs()) if have_install() else None
    return _fonts[n]


def ramp(colour):
    """(16,) RGB565 table: a TABLES name, a 16-entry table of RGB triples, or the 16-step ramp black -> colour."""
    if isinstance(colour, str):
        return gfx.pack16(gfx.code_ramps16()[TABLES[colour]])
    if len(colour) == 16:                                   # a ready 16-entry table of RGB triples (player ramps)
        return gfx.pack16(np.array(colour, np.uint8))
    i = np.arange(16, dtype=np.int32)[:, None]
    return gfx.pack16((i * np.array(colour[:3], np.int32)[None] // 15).astype(np.uint8))


def _compose(font, lines, colour, shadow, align, width):
    """RGBA block: `lines` (font bytes) aligned inside `width` (None = the widest)."""
    cols = None if font.is16a else ramp(colour)
    widths = [font.measure(ln) for ln in lines]
    block = max([width or 0] + widths)
    lh = font.line_height()
    h = (len(lines) - 1) * lh + font.cell_height() + 1
    out = np.zeros((h + SHADOW_OFFSET, block + 2 + SHADOW_OFFSET, 4), np.uint8)
    shade = gfx.pack16(np.tile(np.array(SHADOW_COLOUR, np.uint8), (16, 1)))
    dark = np.zeros((256, 3), np.uint8)
    for i, (ln, w) in enumerate(zip(lines, widths)):
        x = {"left": 0, "center": (block - w) // 2, "right": block - w}[align]
        y = i * lh
        if shadow:
            img = font.render(ln, colours=None if font.is16a else shade, palette=dark if font.is16a else None)
            gfx.blend(out, img, x + SHADOW_OFFSET, y + SHADOW_OFFSET)
        gfx.blend(out, font.render(ln, colours=cols), x, y)
    return out


def _fallback_font():
    global _fallback
    if not pygame.font.get_init():                        # pygame.quit() invalidates the font
        pygame.font.init()
        _fallback = None
    if _fallback is None:
        _fallback = pygame.font.Font(None, 14)
    return _fallback


def render_text(text, colour=(255, 255, 255), font=DEFAULT_FONT, shadow=True, align="left",
                width=None, wrap=False, background=None):
    """Surface with `text`; `wrap` breaks it to `width` (Font.wrap), `align` places each line
    inside the block (`width` or the widest line).  Cached per argument set."""
    if not isinstance(text, (str, bytes)):
        text = str(text)
    key = (font, text, colour, shadow, align, width, wrap, background)
    surf = _surfaces.get(key)
    if surf is not None:
        _surfaces.move_to_end(key)
        return surf
    f = game_font(font)
    if f is None:
        shown = text if isinstance(text, str) else text.decode("cp866", "replace")
        surf = _fallback_font().render(shown, False, colour[:3] if isinstance(colour, tuple) else (255, 255, 255))
    else:
        codes = font_bytes(text) if isinstance(text, str) else text
        lines = f.wrap(codes, width) if wrap and width else [codes]
        arr = _compose(f, lines, colour, shadow, align, width if wrap else None)
        surf = pygame.image.frombuffer(arr.tobytes(), (arr.shape[1], arr.shape[0]), "RGBA")
        if pygame.display.get_surface():
            surf = surf.convert_alpha()
    if background is not None:
        bg = pygame.Surface(surf.get_size())
        bg.fill(background)
        bg.blit(surf, (0, 0))
        surf = bg
    _surfaces[key] = surf
    if len(_surfaces) > CACHE_SIZE:
        _surfaces.popitem(last=False)
    return surf


def draw_text(surface, text, x, y, colour=(255, 255, 255), align="left", font=DEFAULT_FONT,
              shadow=True, width=None, wrap=False):
    """Draw `text` with its top at `y`; `align` 'left' (x = left), 'center' (x = middle) or
    'right' (x = right edge).  `width` + `wrap`: a paragraph broken to `width`, `x` is then the
    left edge of the block.  Returns the drawn width."""
    img = render_text(text, colour, font, shadow, align if wrap else "left", width, wrap)
    if not wrap:
        if align == "center":
            x -= img.get_width() // 2
        elif align == "right":
            x -= img.get_width()
    surface.blit(img, (x, y))
    return img.get_width()


# --- exact placement of the exe's `FUN_0045d536(x, y, text, flags, colours, off)` (docs/engine/ui-layout.md 11.8) ---------------------

LEFT, RIGHT, CENTRE, BOTTOM, MIDDLE = 0, 1, 2, 4, 8       # draw flags (`FUN_0045e531`; fonts.md)
SHADOW_TABLE = tuple(SHADOW_COLOUR for _ in range(16))        # slot 6 of the font vtable: a constant (8, 8, 8) table


def measure(text, font=DEFAULT_FONT):
    """The exe's `measure` of `text` in font `font` (`FUN_0045cb59`, spacing included, a lone `~` counts 0); an estimate from pygame's font without an install."""
    f = game_font(font)
    if f is None:
        return _fallback_font().size(text if isinstance(text, str) else text.decode("cp866", "replace"))[0]
    return f.measure(font_bytes(text) if isinstance(text, str) else text)


def draw_text_exact(surface, text, x, y, colour="normal", flags=LEFT, font=DEFAULT_FONT, off=SHADOW_OFFSET):
    """`FUN_0045d536` placement: flags 0 left, 1 right (`x -= measure`), 2 centre (`x -= measure // 2`), 4 bottom, 8 middle (`y -= glyph0 width`, `>> 1`), `y` = the top of the glyph cell, the shadow
    `off` pixels right and down in the constant (8, 8, 8) table.  Unlike `draw_text(align=)` the origin is the exact measure, not the rendered
    surface width (`measure + 3`).  Returns the measure."""
    w = measure(text, font)
    if flags & RIGHT:
        x -= w
    if flags & CENTRE:
        x -= w >> 1
    if flags & (BOTTOM | MIDDLE):                   # the vertical flags use the width of glyph 0 (sic, `FUN_0045e531`: fonts.md)
        f = game_font(font)
        glyph0 = f.cell_width() if f is not None else 16
        if flags & BOTTOM:
            y -= glyph0
        if flags & MIDDLE:
            y -= glyph0 >> 1
    if off:
        surface.blit(render_text(text, SHADOW_TABLE, font, shadow=False), (x + off, y + off))
    surface.blit(render_text(text, colour, font, shadow=False), (x, y))
    return w
