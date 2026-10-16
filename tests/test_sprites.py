"""Synthetic tests, one per rule in docs/formats/sprites.md."""

import struct

import numpy as np
import pytest

from allods2 import graphics as gfx

from helpers import container


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


# --- RLE walks: (decoder, stream, w, h) -> drawn indices [, (consumed, rows_left)]

D256, D16 = gfx.decode_256, gfx.decode_16


@pytest.mark.parametrize("decode,data,w,h,image,walk", [
    pytest.param(D256, (0x81, 0x02, 5, 6, 0x83), 3, 2, [[-1, 5, 6], [-1, -1, -1]], (5, 0),
                 id="256-literal-and-pixel-skip"),
    pytest.param(D256, (0xC1, 0x01, 7), 2, 1, [[-1, 7]], None, id="256-0xc0-is-pixel-skip"),
    pytest.param(D256, (0x01, 4, 0x41, 0x01, 9), 2, 2, [[4, -1], [-1, 9]], None,
                 id="256-row-skip-keeps-column"),
    pytest.param(D256, (0x02, 1, 2, 0x45, 0x01, 3), 2, 3, [[1, 2], [-1, -1], [-1, -1]], (4, 2),
                 id="256-row-skip-past-end-terminates"),
    pytest.param(D256, (0x03, 1, 2, 3, 0x02, 4, 5), 2, 3, [[1, 2], [3, 4], [5, -1]], None,
                 id="256-overshoot-carries-into-next-row"),
    pytest.param(D256, (0x01, 0), 1, 1, [[0]], None, id="256-literal-index-0-is-drawn"),
    pytest.param(D16, (0x01, 0x21), 2, 1, [[1, 2]], None, id="16-nibbles-low-first"),
    # 1 pixel, the counter advances 2*1-1
    pytest.param(D16, (0x01, 0x05, 0x81), 2, 1, [[5, -1]], (3, 0), id="16-zero-high-nibble-ends-run"),
    # run of 2 bytes, the first has a zero high nibble: 1 pixel, counter 2*2-1 = 3;
    # the second byte (0x81) is then a control byte: skip 1 -> counter 4 = w
    pytest.param(D16, (0x02, 0x03, 0x81), 4, 1, [[3, -1, -1, -1]], (3, 0),
                 id="16-rest-of-run-reread-as-control"),
    # the same stream at width 2: counter 3 >= 2 closes the row before 0x81 is read
    pytest.param(D16, (0x02, 0x03, 0x81), 2, 1, None, (2, 0), id="16-short-run-closes-row"),
])
def test_rle_walk(decode, data, w, h, image, walk):
    d = decode(bytes(data), w, h)
    if image is not None:
        assert drawn(d) == image
    if walk is not None:
        assert (d.consumed, d.rows_left) == walk


def test_smooth_overlay_is_half_transparent_colour():
    pal = bytearray(1024)
    pal[4 * 7:4 * 7 + 3] = bytes((3, 2, 1))
    sf = gfx.SpriteFile.parse(container([(2, 1, bytes((0x81, 0x01, 7)))], bytes(pal)), "smooth")
    assert sf.to_rgba(0)[0].tolist() == [[0, 0, 0, 0], [1, 2, 3, 128]]


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

GREY = [(i, i, i) for i in range(256)]


@pytest.mark.parametrize("fill,draw,expect", [
    pytest.param((160, 80, 16), lambda c: c.draw_darken(gfx.Sprite(1, 1, bytes((0x01, 0))), 0, 0, level=8),
                 [80, 40, 8], id="darken"),
    pytest.param((0, 0, 0), lambda c: c.draw_16a(gfx.Sprite(1, 1, words(0x0001, px16a(3, 7))), 0, 0,
                                                 [(255, 255, 255)] * 256),
                 [127, 127, 127], id="16a-blend-255x8/16"),
    pytest.param((100, 100, 100), lambda c: c.draw_256_translucent(
        gfx.Sprite(1, 1, bytes((0x01, 0))), 0, 0, [(200, 0, 51)] * 256), [150, 50, 75], id="translucent"),
    pytest.param((0, 0, 0), lambda c: c.draw_256(gfx.Sprite(2, 1, bytes((0x02, 1, 2))), -1, 0, GREY),
                 [2, 2, 2], id="clipping"),
])
def test_canvas_mode(fill, draw, expect):
    c = gfx.Canvas(1, 1, fill)
    draw(c)
    assert c.pix[0, 0].tolist() == expect


def test_canvas_mirror_256():
    # Row [1, 2, ·] mirrored in place: the run starts at x + w - 1 going left.
    c = gfx.Canvas(3, 1)
    c.draw_256(gfx.Sprite(3, 1, bytes((0x02, 1, 2, 0x81))), 0, 0, GREY, mirror=True)
    assert c.pix[0, :, 0].tolist() == [0, 2, 1]


def test_canvas_mirror_16a_and_darken():
    c = gfx.Canvas(2, 1, (160, 160, 160))
    c.draw_16a(gfx.Sprite(2, 1, words(0x0001, px16a(0, 15), 0x8001)), 0, 0,
               [(0, 0, 0)] * 256, mirror=True)
    assert c.pix[0, :, 0].tolist() == [160, 0]
    c.draw_darken(gfx.Sprite(2, 1, bytes((0x81, 0x01, 0))), 0, 0, level=8, mirror=True)
    assert c.pix[0, :, 0].tolist() == [80, 0]
