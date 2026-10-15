"""Synthetic tests, one per rule in docs/formats/sprites.md."""

import struct

import numpy as np
import pytest

from allods2 import graphics as gfx


def container(sprites, palette=None):
    """Build a sprite container: [palette] {w, h, size, data}* trailer."""
    body = b"".join(struct.pack("<III", w, h, len(d)) + d for w, h, d in sprites)
    trailer = len(sprites)
    if palette is not None:
        body = palette + body
        trailer |= gfx.PALETTE_FLAG
    return body + struct.pack("<I", trailer)


def words(*ws):
    return struct.pack("<%dH" % len(ws), *ws)


def px16a(index, alpha):
    return (alpha << 9) | (index << 1)


def drawn(decoded, fill=-1):
    """Index image with undrawn pixels replaced by `fill`, as nested lists."""
    return np.where(decoded.mask, decoded.index.astype(int), fill).tolist()


# --- container ------------------------------------------------------------

def test_palette_flag_and_bgr_order():
    pal = bytearray(1024)
    pal[4:8] = bytes((10, 20, 30, 0))              # entry 1 stored as B, G, R, 0
    sf = gfx.SpriteFile.parse(container([(1, 1, b"\x01\x05")], bytes(pal)))
    assert sf.palette[1].tolist() == [30, 20, 10]
    assert len(sf) == 1


def test_no_palette():
    sf = gfx.SpriteFile.parse(container([(2, 1, b"\x02\x07\x08"), (1, 1, b"\x01\x09")]))
    assert sf.palette is None
    assert [s.width for s in sf.sprites] == [2, 1]
    assert drawn(sf.decode(1)) == [[9]]


@pytest.mark.parametrize("data", [b"", container([(1, 1, b"\x01\x05")])[:6] + b"\x01\0\0\0"])
def test_truncated(data):
    with pytest.raises(ValueError):
        gfx.SpriteFile.parse(data)


@pytest.mark.parametrize("name,kind", [
    ("x/sprites.256", "256"), ("x/spritesb.256", "smooth"), ("x/houseb.256", "smooth"),
    ("x/sprites.16a", "16a"), ("x/font1.16", "16"),
])
def test_guess_kind(name, kind):
    assert gfx.guess_kind(name) == kind


# --- .256 -----------------------------------------------------------------

def test_256_literal_and_pixel_skip():
    data = bytes((0x81, 0x02, 5, 6, 0x83))          # skip 1, copy 2 | skip 3
    d = gfx.decode_256(data, 3, 2)
    assert drawn(d) == [[-1, 5, 6], [-1, -1, -1]]
    assert (d.consumed, d.rows_left) == (5, 0)


def test_256_0xc0_is_pixel_skip():
    assert drawn(gfx.decode_256(bytes((0xC1, 0x01, 7)), 2, 1)) == [[-1, 7]]


def test_256_row_skip_keeps_column():
    data = bytes((0x01, 4, 0x41, 0x01, 9))          # copy 1 | skip row | copy 1
    assert drawn(gfx.decode_256(data, 2, 2)) == [[4, -1], [-1, 9]]


def test_256_row_skip_past_end_terminates():
    data = bytes((0x02, 1, 2, 0x45, 0x01, 3))
    d = gfx.decode_256(data, 2, 3)
    assert drawn(d) == [[1, 2], [-1, -1], [-1, -1]]
    assert (d.consumed, d.rows_left) == (4, 2)


def test_256_overshoot_carries_into_next_row():
    data = bytes((0x03, 1, 2, 3, 0x02, 4, 5))       # width 2: 3 pixels, counter resets
    assert drawn(gfx.decode_256(data, 2, 3)) == [[1, 2], [3, 4], [5, -1]]


def test_256_literal_index_zero_is_drawn():
    assert drawn(gfx.decode_256(bytes((0x01, 0)), 1, 1)) == [[0]]


def test_smooth_overlay_is_half_transparent_colour():
    pal = bytearray(1024)
    pal[4 * 7:4 * 7 + 3] = bytes((3, 2, 1))
    sf = gfx.SpriteFile.parse(container([(2, 1, bytes((0x81, 0x01, 7)))], bytes(pal)), "smooth")
    assert sf.to_rgba(0)[0].tolist() == [[0, 0, 0, 0], [1, 2, 3, 128]]


# --- .16 ------------------------------------------------------------------

def test_16_nibbles_low_first():
    assert drawn(gfx.decode_16(bytes((0x01, 0x21)), 2, 1)) == [[1, 2]]


def test_16_zero_high_nibble_ends_run():
    data = bytes((0x01, 0x05, 0x81))                # 1 pixel, counter advances 2*1-1
    d = gfx.decode_16(data, 2, 1)
    assert drawn(d) == [[5, -1]]
    assert d.consumed == 3


def test_16_rest_of_run_is_reread_as_control():
    # run of 2 bytes, first has zero high nibble: 1 pixel, counter 2*2-1 = 3;
    # the second byte (0x81) is then a control byte: skip 1 -> counter 4 = w
    data = bytes((0x02, 0x03, 0x81))
    d = gfx.decode_16(data, 4, 1)
    assert drawn(d) == [[3, -1, -1, -1]]
    assert (d.consumed, d.rows_left) == (3, 0)


def test_16_short_run_counter_can_close_row():
    # same stream at width 2: counter 3 >= 2 closes the row before 0x81 is read
    d = gfx.decode_16(bytes((0x02, 0x03, 0x81)), 2, 1)
    assert (d.consumed, d.rows_left) == (2, 0)


# --- .16a -----------------------------------------------------------------

def test_16a_pixels_and_skips():
    d = gfx.decode_16a(words(0x8001, 0x0001, px16a(200, 15), 0x8002), 2, 2)
    assert drawn(d) == [[-1, 200], [-1, -1]]
    assert d.alpha[0, 1] == 15


def test_16a_row_skip_tested_before_pixel_skip():
    d = gfx.decode_16a(words(0xC001, 0x0002, px16a(1, 0), px16a(2, 7)), 2, 2)
    assert drawn(d) == [[-1, -1], [1, 2]]
    assert d.alpha[1].tolist() == [0, 7]


def test_16a_alpha_coverage():
    sf = gfx.SpriteFile.parse(container(
        [(2, 1, words(0x0002, px16a(0, 0), px16a(0, 15)))], bytes(1024)), "16a")
    assert sf.to_rgba(0)[0, :, 3].tolist() == [16, 255]


# --- compositing ----------------------------------------------------------

def test_canvas_darken():
    c = gfx.Canvas(1, 1, (160, 80, 16))
    c.draw_darken(gfx.Sprite(1, 1, bytes((0x01, 0))), 0, 0, level=8)
    assert c.pix[0, 0].tolist() == [80, 40, 8]


def test_canvas_16a_blend():
    c = gfx.Canvas(1, 1)
    c.draw_16a(gfx.Sprite(1, 1, words(0x0001, px16a(3, 7))), 0, 0, [(255, 255, 255)] * 256)
    assert c.pix[0, 0].tolist() == [127, 127, 127]     # 255 * 8/16


def test_canvas_translucent():
    c = gfx.Canvas(1, 1, (100, 100, 100))
    c.draw_256_translucent(gfx.Sprite(1, 1, bytes((0x01, 0))), 0, 0, [(200, 0, 51)] * 256)
    assert c.pix[0, 0].tolist() == [150, 50, 75]


def test_canvas_clipping():
    c = gfx.Canvas(1, 1)
    c.draw_256(gfx.Sprite(2, 1, bytes((0x02, 1, 2))), -1, 0, [(i, i, i) for i in range(256)])
    assert c.pix[0, 0].tolist() == [2, 2, 2]


def test_canvas_mirror_256():
    # Row [1, 2, ·] mirrored in place: the run starts at x + w - 1 going left.
    c = gfx.Canvas(3, 1)
    c.draw_256(gfx.Sprite(3, 1, bytes((0x02, 1, 2, 0x81))), 0, 0,
               [(i, i, i) for i in range(256)], mirror=True)
    assert c.pix[0, :, 0].tolist() == [0, 2, 1]


def test_canvas_mirror_16a_and_darken():
    c = gfx.Canvas(2, 1, (160, 160, 160))
    c.draw_16a(gfx.Sprite(2, 1, words(0x0001, px16a(0, 15), 0x8001)), 0, 0,
               [(0, 0, 0)] * 256, mirror=True)
    assert c.pix[0, :, 0].tolist() == [160, 0]
    c.draw_darken(gfx.Sprite(2, 1, bytes((0x81, 0x01, 0))), 0, 0, level=8, mirror=True)
    assert c.pix[0, :, 0].tolist() == [80, 0]
