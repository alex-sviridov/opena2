"""Bitmap fonts: fontN.16 / fontN.16a glyph sprites + fontN.dat metrics.

Spec: docs/formats/fonts.md.  Text is a byte string (cp1251, as the game
stores it); layout follows the measure routine FUN_00461e19, the .16 draw
0x4637f1 (with the a2mgr.dll hooks Ordinal_125/126) and the .16a draw
FUN_00463bbd.
"""

import os
import struct
from dataclasses import dataclass, field

import numpy as np

from .palette import pack16, unpack16
from .sprites import SpriteFile, to_rgba

FIRST_CHAR = 0x20
SPACING = 2                 # FUN_00464849 passes 2 to every font constructor
TILDE = 0x7E - FIRST_CHAR   # glyph 0x5e

ALIGN_RIGHT = 1             # x -= measure(text)
ALIGN_CENTER = 2            # x -= measure(text) >> 1
ALIGN_BOTTOM = 4            # y -= width of glyph 0 (sic)
ALIGN_MIDDLE = 8            # y -= width of glyph 0 >> 1

DEFAULT_COLOURS = 0x62AFB8  # FUN_00463a06: the constant (8, 8, 8) table


def read_metrics(data):
    """fontN.dat: one u32 per glyph, glyph g = character 0x20 + g."""
    if len(data) % 4:
        raise ValueError("metrics size %d is not a multiple of 4" % len(data))
    return list(struct.unpack("<%dI" % (len(data) // 4), data))


def map_char(c, cyrillic=False):
    """FUN_00461da1 + a2mgr Ordinal_26: byte -> font code.  Only active when
    DAT_0062c9c4 == 1 (`cyrillic`)."""
    if not cyrillic:
        return c
    special = {0xC1: 0x80, 0xF0: 0xE0, 0xF1: 0x89}      # a2mgr, checked first
    if c in special:
        return special[c]
    if 0x80 <= c <= 0xAF:
        return c + 0x30
    if 0xE0 <= c <= 0xEF:
        return c + 0x10
    return c


def escape_ramp(r, g, b):
    """The 16-entry RGB565 table a2mgr builds for %[...] (FUN_10005a20):
    entry k = (k·c / 15) scaled by 31/255 or 63/255, packed with OR."""
    out = []
    for k in range(16):
        r5 = (k * r // 15) * 31 // 255
        g6 = (k * g // 15) * 63 // 255
        b5 = (k * b // 15) * 31 // 255
        out.append((((r5 * 0x40) | g6) << 5 | b5) & 0xFFFF)
    return np.array(out, np.uint16)


def _hex(s):
    try:
        return int(s, 16)
    except ValueError:
        return -1


def _dec(s):
    try:
        return int(s, 10) if s else 0
    except ValueError:
        return -1


def parse_escape(text, i, original):
    """a2mgr FUN_10005a20 at text[i].  Returns (new_i, colour change) where
    the change is None (keep), "reset" (back to the caller's table) or an
    (r, g, b) triple.  Only parsed when the caller passed a colour table."""
    if original is None or text[i:i + 2] != b"%[":
        return i, None
    start = i + 2
    end = start
    while end < len(text) and text[end] not in (0, ord("]")):
        end += 1
    if end >= len(text) or text[end] != ord("]"):
        return i, None
    body = text[start:end].decode("latin-1")
    if body == "*":
        return end + 1, "reset"
    rgb = [-1, 0, 0]
    if "," in body:
        fields = body.split(",")
        if len(fields) > 3 or any(len(f) > 3 for f in fields):
            return i, None
        for k, f in enumerate(fields):
            rgb[k] = _dec(f)
    elif len(body) == 3:
        rgb = [_hex(ch) * 17 if _hex(ch) >= 0 else -1 for ch in body]
    elif len(body) == 6:
        rgb = [_hex(body[k:k + 2]) for k in (0, 2, 4)]
    if min(rgb) < 0:
        return i, None
    return end + 1, tuple(rgb)


@dataclass
class Glyph:
    x: int
    y: int
    index: int
    colours: object = None      # .16: (16,) uint16 RGB565 table


@dataclass
class Line:
    x0: int
    x1: int
    y: int
    colour: int                 # RGB565


@dataclass
class Layout:
    glyphs: list = field(default_factory=list)
    lines: list = field(default_factory=list)
    end_x: int = 0


class Font:
    """A font object as built by FUN_0046365e (.16) / FUN_00463a16 (.16a):
    glyph sprites, the .dat table, spacing."""

    def __init__(self, sprites, widths, spacing=SPACING, cyrillic=False):
        self.sprites = sprites
        self.widths = widths
        self.spacing = spacing
        self.cyrillic = cyrillic

    @classmethod
    def load(cls, stem, cyrillic=False):
        """stem: path without extension, e.g. .../font1/font1."""
        for ext in (".16", ".16a"):
            if os.path.exists(stem + ext):
                sprites = SpriteFile.load(stem + ext)
                break
        else:
            raise FileNotFoundError(stem + ".16/.16a")
        with open(stem + ".dat", "rb") as f:
            widths = read_metrics(f.read())
        return cls(sprites, widths, cyrillic=cyrillic)

    @property
    def is16a(self):
        return self.sprites.kind == "16a"

    def glyph(self, c):
        return (map_char(c, self.cyrillic) - FIRST_CHAR) & 0xFF

    def width(self, g):
        """.dat value; glyphs past the table read past it in the game (we use 0)."""
        return self.widths[g] if g < len(self.widths) else 0

    def cell_width(self):
        return self.sprites[0].width

    def cell_height(self):
        return self.sprites[0].height

    def measure(self, text):
        """FUN_00461e19.  Bytes < 0x20 and a lone '~' count 0; '~~' counts
        one '~'; a space adds half the glyph-0 height.  %[...] escapes are
        not recognised here (a2mgr does not hook it), so they count."""
        total, i = 0, 0
        while i < len(text):
            c = text[i]
            if c >= 0x20:
                if c == 0x7E:
                    if i + 1 < len(text) and text[i + 1] == 0x7E:
                        i += 1
                    else:
                        i += 1
                        continue
                g = self.glyph(c)
                total += self.width(g) + self.spacing
                if g == 0:
                    total += self.cell_height() >> 1
            i += 1
        return total

    def _align(self, text, x, y, flags):
        if flags & ALIGN_RIGHT:
            x -= self.measure(text)
        if flags & ALIGN_CENTER:
            x -= self.measure(text) >> 1
        if flags & ALIGN_BOTTOM:
            y -= self.cell_width()
        if flags & ALIGN_MIDDLE:
            y -= self.cell_width() >> 1
        return x, y

    def layout(self, text, x=0, y=0, flags=0, colours=None):
        """Glyph positions and underlines, as the game's draw places them.
        colours: the caller's .16 table, (16,) RGB565; None = no table."""
        return self._layout16a(text, x, y, flags) if self.is16a else \
            self._layout16(text, x, y, flags, colours)

    def _layout16a(self, text, x, y, flags):
        """FUN_00463bbd: no '~' or %[...] handling."""
        out = Layout()
        x, y = self._align(text, x, y, flags)
        for c in text:
            g = self.glyph(c)
            if g == 0:
                x += self.cell_height() >> 1
            else:
                out.glyphs.append(Glyph(x, y, g))
            x += self.width(g) + self.spacing
        out.end_x = x
        return out

    def _layout16(self, text, x, y, flags, colours):
        """0x4637f1 + a2mgr: per position, first one %[...] escape, then
        '~' + c underlines c (no advance), '~~' draws '~', space advances
        half the glyph-0 height."""
        out = Layout()
        x, y = self._align(text, x, y, flags)
        original = None if colours is None else np.asarray(colours, np.uint16)
        current = original
        i = 0
        while i < len(text):
            i, change = parse_escape(text, i, original)
            if change == "reset":
                current = original
            elif change is not None:
                current = escape_ramp(*change)
            if i >= len(text):
                break
            g = self.glyph(text[i])
            g2 = self.glyph(text[i + 1] if i + 1 < len(text) else 0)
            if g == TILDE and g2 != TILDE:
                ly = y + self.cell_height()
                out.lines.append(Line(x, x + self.width(g2), ly,
                                      int(current[15]) if current is not None else 0))
            else:
                if g == 0:
                    x += self.cell_height() >> 1
                else:
                    out.glyphs.append(Glyph(x, y, g, current))
                x += self.width(g) + self.spacing
                if g == TILDE and g2 == TILDE:
                    i += 1
            i += 1
        out.end_x = x
        return out

    def render(self, text, colours=None, palette=None, flags=0):
        """(h, w, 4) RGBA image of `text` drawn at (0, 0) (after alignment
        offsets, clipped).  .16: colours = (16,) RGB565 table (default:
        grey ramp 17i).  .16a: palette = 256 RGB (default: embedded)."""
        if not self.is16a and colours is None:
            colours = pack16(np.repeat(np.arange(16, dtype=np.uint16)[:, None] * 17, 3, 1))
        lay = self.layout(text, 0, 0, flags, colours)
        w = max([lay.end_x] + [gl.x + self.sprites[gl.index].width
                               for gl in lay.glyphs if gl.index < len(self.sprites)]
                + [ln.x1 + 1 for ln in lay.lines])
        h = self.cell_height() + 1
        img = np.zeros((h, max(w, 1), 4), np.uint8)
        for gl in lay.glyphs:
            if gl.index >= len(self.sprites):
                continue
            if self.is16a:
                pal = palette if palette is not None else self.sprites.palette
            else:
                pal = np.zeros((256, 3), np.uint8)
                pal[:16] = unpack16(gl.colours)
            rgba = to_rgba(self.sprites.decode(gl.index), self.sprites.kind, pal)
            _blend(img, rgba, gl.x, gl.y)
        for ln in lay.lines:
            x0, x1 = max(ln.x0, 0), min(ln.x1 + 1, img.shape[1])
            if 0 <= ln.y < h and x0 < x1:
                img[ln.y, x0:x1, :3] = unpack16(ln.colour)
                img[ln.y, x0:x1, 3] = 255
        return img


def _blend(dst, src, x, y):
    """Alpha-composite src over dst at (x, y), clipped."""
    h, w = src.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, dst.shape[1]), min(y + h, dst.shape[0])
    if x0 >= x1 or y0 >= y1:
        return
    s = src[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.uint16)
    d = dst[y0:y1, x0:x1].astype(np.uint16)
    a = s[..., 3:4]
    d[..., :3] = (s[..., :3] * a + d[..., :3] * (255 - a)) // 255
    d[..., 3:4] = np.maximum(d[..., 3:4], a)
    dst[y0:y1, x0:x1] = d.astype(np.uint8)


def last_ink_columns(sprites):
    """Per glyph: index of the rightmost drawn column, 0 if blank."""
    out = []
    for i in range(len(sprites)):
        cols = np.nonzero(sprites.decode(i).mask.any(0))[0]
        out.append(int(cols.max()) if len(cols) else 0)
    return out
