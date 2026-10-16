"""Synthetic tests, one per rule in docs/formats/fonts.md, plus the game fonts."""

import struct

import numpy as np
import pytest

from allods2 import graphics as gfx
from allods2.graphics.sprites import Sprite, SpriteFile

from helpers import GFS

FONTS = GFS.glob("graphics/font*/font*.dat") if GFS else []

DOT = b"\x01\x0f"            # .16 stream: one pixel, colour slot 15


def font16(widths, w=4, h=6):
    """A .16 font whose glyph g is a w x h cell with one pixel at (0, 0)."""
    sprites = [Sprite(w, h, DOT + bytes([0x40 | (h - 1)])) for _ in widths]
    return gfx.Font(SpriteFile(sprites, kind="16"), list(widths))


def placed(layout):
    return [(g.x, g.y, g.index) for g in layout.glyphs]


GREY = np.arange(16, dtype=np.uint16)


# --- .dat ----------------------------------------------------------------

def test_metrics_one_u32_per_glyph():
    assert gfx.read_metrics(struct.pack("<3I", 0, 5, 7)) == [0, 5, 7]
    with pytest.raises(ValueError):
        gfx.read_metrics(b"\0\0\0")


# --- character map ---------------------------------------------------------

def test_char_map_off_is_identity():
    assert [gfx.map_char(c) for c in (0x41, 0x80, 0xC1, 0xF1)] == [0x41, 0x80, 0xC1, 0xF1]


def test_char_map_cyrillic_cp866():
    m = lambda c: gfx.map_char(c, cyrillic=True)
    assert (m(0x80), m(0xAF), m(0xE0), m(0xEF)) == (0xB0, 0xDF, 0xF0, 0xFF)
    assert (m(0xC1), m(0xF0), m(0xF1)) == (0xC1, 0xF0, 0xF1)     # outside both ranges
    assert (m(0x41), m(0xB0), m(0xFF)) == (0x41, 0xB0, 0xFF)


def test_locale_text_cp1251_to_cp866():
    # CharToOemA in FUN_00474585 / FUN_004741ad (Russian system locale)
    src = "Атака ёЁ я ~Ok’".encode("cp1251")
    assert gfx.ansi_to_oem(src) == b"\x80\xe2\xa0\xaa\xa0 \xf1\xf0 \xef ~Ok'"
    # the font map then reaches the Cyrillic glyphs (А -> glyph 0xB0)
    assert gfx.map_char(gfx.ansi_to_oem("А".encode("cp1251"))[0], cyrillic=True) == 0xB0


def test_font_remap_off_by_default():
    f = font16([0] * 224)
    assert (f.glyph(0x80), f.glyph(0x41)) == (0x60, 0x21)
    assert gfx.Font(f.sprites, f.widths, cyrillic=True).glyph(0x80) == 0x90


@pytest.mark.skipif(GFS is None, reason="game files not available")
def test_gog_locale_flag_is_off():
    assert GFS.read_bytes("main/id") == b"english 0"
    assert gfx.locale_flag(GFS) == 0
    assert gfx.Font.load("graphics/font1/font1", GFS).cyrillic is False


# --- advance, space, spacing -------------------------------------------------

def test_advance_is_dat_plus_spacing():
    f = font16([0, 3, 5])                     # ' ', '!', '"'
    lay = f.layout(b'!"!')
    assert placed(lay) == [(0, 0, 1), (5, 0, 2), (12, 0, 1)]
    assert lay.end_x == 17 and f.measure(b'!"!') == 17


def test_space_adds_half_glyph0_height():
    f = font16([1, 3], w=4, h=7)              # height 7 -> +3
    lay = f.layout(b" !")
    assert placed(lay) == [(6, 0, 1)]         # 3 + (1 + 2)
    assert f.measure(b" ") == 6


def test_alignment_flags():
    f = font16([0, 3], w=10, h=6)
    assert placed(f.layout(b"!", 20, 30, gfx.ALIGN_RIGHT)) == [(15, 30, 1)]
    assert placed(f.layout(b"!", 20, 30, gfx.ALIGN_CENTER)) == [(18, 30, 1)]
    # bottom / middle subtract the WIDTH of glyph 0 (game quirk)
    assert placed(f.layout(b"!", 20, 30, gfx.ALIGN_BOTTOM)) == [(20, 20, 1)]
    assert placed(f.layout(b"!", 20, 30, gfx.ALIGN_MIDDLE)) == [(20, 25, 1)]


# --- measure -------------------------------------------------------------

def test_measure_skips_controls_and_lone_tilde():
    widths = [0] * 0x60
    widths[1] = 3
    widths[0x5E] = 4
    f = font16(widths)
    assert f.measure(b"\x01!\x1f") == 5
    assert f.measure(b"~!") == 5              # lone '~' counts nothing
    assert f.measure(b"~~") == 6              # '~~' counts one '~'


# --- .16 draw: '~' -------------------------------------------------------------

def tilde_font():
    widths = [0] * 0x60
    widths[0x21] = 6                          # 'A'
    widths[0x5E] = 4                          # '~'
    return font16(widths, w=8, h=6)


def test_tilde_underlines_next_char_without_advance():
    lay = tilde_font().layout(b"~A", 10, 0, colours=GREY)
    assert placed(lay) == [(10, 0, 0x21)]
    ln = lay.lines[0]
    assert (ln.x0, ln.x1, ln.y, ln.colour) == (10, 16, 6, 15)   # colour = table[15]


def test_double_tilde_draws_one_tilde():
    lay = tilde_font().layout(b"~~A", colours=GREY)
    assert placed(lay) == [(0, 0, 0x5E), (6, 0, 0x21)] and not lay.lines


# --- .16a draw -------------------------------------------------------------

def test_16a_draw_has_no_tilde_handling():
    widths = [0] * 0x60
    sprites = [Sprite(4, 4, b"") for _ in widths]
    f = gfx.Font(SpriteFile(sprites, kind="16a"), widths)
    lay = f.layout(b"~A")
    assert [g.index for g in lay.glyphs] == [0x5E, 0x21] and not lay.lines


# --- rendering -----------------------------------------------------------

def test_render_uses_caller_colours():
    widths = [0, 0]
    f = font16(widths, w=1, h=1)
    f.sprites.sprites[1] = Sprite(1, 1, DOT)
    table = np.zeros(16, np.uint16)
    table[15] = gfx.pack16(np.array([255, 0, 0], np.uint8))
    img = f.render(b"!", colours=table)
    assert img[0, 0].tolist() == [255, 0, 0, 255]


# --- game files ------------------------------------------------------------

@pytest.mark.skipif(not FONTS, reason="game files not available")
@pytest.mark.parametrize("dat", FONTS, ids=lambda p: p.rpartition("/")[2])
def test_game_font_byte_accounting(dat):
    font = gfx.Font.load(dat[:-4], GFS)
    assert len(GFS.read(dat)) == 4 * len(font.sprites)
    for s in font.sprites.sprites:
        assert gfx.check_sprite(s, font.sprites.kind)[0] == len(s.data)
    ink = gfx.last_ink_columns(font.sprites)
    assert sum(a != b for a, b in zip(font.widths, ink)) <= 2
