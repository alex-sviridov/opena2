"""Palette tests: synthetic ones per rule in docs/formats/palettes.md, then
checks against every palette in the install (skipped when it is absent)."""

import os
import struct
import sys
from dataclasses import astuple

import numpy as np
import pytest
from PIL import Image

from allods2 import graphics as gfx
from allods2.common import DATA, ROOT
from allods2.graphics.palette import (BRIGHT2, BRIGHT32, FADE16, GRAY, MASK, PLAIN,
                                      TEAM_COLOR_INDEX)

GRAPHICS = os.path.join(DATA, "graphics")
needs_samples = pytest.mark.skipif(not os.path.isdir(GRAPHICS),
                                   reason="game install not present in samples/")


def quads(entries):
    """1024 bytes from {index: (r, g, b, reserved)}."""
    buf = bytearray(1024)
    for i, (r, g, b, x) in entries.items():
        buf[4 * i:4 * i + 4] = bytes((b, g, r, x))
    return bytes(buf)


def test_entry_order_is_bgr0():
    buf = bytes(4) + bytes((0x0A, 0x14, 0x1E, 0x00)) + bytes(1016)
    assert gfx.read_palette(buf)[1].tolist() == [30, 20, 10]


def test_reserved_byte_kept_for_round_trip():
    buf = quads({0: (1, 2, 3, 7), 255: (255, 254, 253, 9)})
    p = gfx.Palette.from_bytes(buf)
    assert p.reserved[0] == 7 and p.rgb[255].tolist() == [255, 254, 253]
    assert p.to_bytes() == buf


def test_to_rgb_and_swatch_layout():
    rgb = np.zeros((256, 3), np.uint8)
    rgb[17] = (9, 8, 7)
    p = gfx.Palette(rgb)
    assert len(p.to_rgb()) == 256 and p.to_rgb()[17] == (9, 8, 7)
    sw = p.swatch(cell=2)
    assert sw.shape == (32, 32, 3)
    assert sw[2, 2].tolist() == [9, 8, 7] and sw[0, 0].tolist() == [0, 0, 0]


def test_png_swatch(tmp_path):
    p = gfx.Palette(gfx.grayscale_palette())
    path = tmp_path / "s.png"
    p.to_png_swatch(str(path), cell=1)
    assert np.asarray(Image.open(path))[15, 15].tolist() == [255, 255, 255]


@pytest.mark.parametrize("kind", ["raw", "pal"])
def test_save_load_round_trip(tmp_path, kind):
    rgb = np.random.default_rng(1).integers(0, 256, (256, 3), dtype=np.uint8)
    path = tmp_path / ("x.pal" if kind == "pal" else "human.pal")
    gfx.Palette(rgb).save(str(path), kind)
    [back] = gfx.load_palettes(str(path))
    assert np.array_equal(back.rgb, rgb)


def test_saved_pal_is_bmp_with_table_at_0x36(tmp_path):
    rgb = np.random.default_rng(2).integers(0, 256, (256, 3), dtype=np.uint8)
    path = tmp_path / "palette.pal"
    gfx.Palette(rgb).save(str(path), "pal")
    assert np.array_equal(gfx.load_pal_file(str(path)), rgb)
    with Image.open(path) as im:
        assert im.format == "BMP" and im.mode == "P"
        assert np.array_equal(np.asarray(im.getpalette()[:768], np.uint8).reshape(256, 3), rgb)


def test_human_pal_is_concatenated_raw_palettes(tmp_path):
    path = tmp_path / "human.pal"
    path.write_bytes(quads({1: (1, 0, 0, 0)}) + quads({1: (2, 0, 0, 0)}))
    pals = gfx.load_palettes(str(path))
    assert [p.rgb[1, 0] for p in pals] == [1, 2]


def test_sprite_palette_only_with_trailer_flag(tmp_path):
    pal = quads({3: (5, 6, 7, 0)})
    a, b = tmp_path / "a.256", tmp_path / "b.256"
    a.write_bytes(pal + struct.pack("<I", 0x80000000))
    b.write_bytes(struct.pack("<I", 0))
    [p] = gfx.load_palettes(str(a))
    assert p.rgb[3].tolist() == [5, 6, 7]
    assert gfx.load_palettes(str(b)) == []


def test_bmp_colour_table_uses_clr_used(tmp_path):
    im = Image.fromarray(np.zeros((2, 2), np.uint8), "P")
    im.putpalette([10, 20, 30, 40, 50, 60])
    path = tmp_path / "t.bmp"
    im.save(path)
    [p] = gfx.load_palettes(str(path))
    assert p.rgb[0].tolist() == [10, 20, 30] and p.rgb[1].tolist() == [40, 50, 60]


# --- shade tables ---------------------------------------------------------

def one(r, g, b):
    rgb = np.zeros((256, 3), np.uint8)
    rgb[1] = (r, g, b)
    return rgb


def test_shade_mask():
    t = gfx.shade_table(one(1, 2, 3), 16, MASK)
    assert t.shape == (1, 256, 3)
    assert t[0, 0].tolist() == [0, 0, 0] and t[0, 1].tolist() == [255, 255, 255]


def test_shade_plain_adds_tint_and_clamps():
    t = gfx.shade_table(one(250, 10, 20), 16, PLAIN, tint=(24, 12, 0))
    assert t[0, 1].tolist() == [255, 22, 20]


def test_shade_bright2_rows_descend_from_double():
    t = gfx.shade_table(one(100, 200, 3), 16, BRIGHT2)
    assert t.shape == (16, 256, 3)
    assert t[0, 1].tolist() == [200, 255, 6]       # k = 16: x2, clamped
    assert t[8, 1].tolist() == [100, 200, 3]       # k = 8: unchanged
    assert t[15, 1].tolist() == [12, 25, 0]        # k = 1: x1/8, truncated


def test_shade_bright2_tint_before_scaling():
    t = gfx.shade_table(one(10, 10, 10), 16, BRIGHT2, tint=(0, 12, 48))
    assert t[8, 1].tolist() == [10, 22, 58]


def test_shade_bright32():
    t = gfx.shade_table(one(64, 255, 31), 0x60, BRIGHT32)
    assert t.shape == (96, 256, 3)
    assert t[0, 1].tolist() == [192, 255, 93]      # k = 96: x3
    assert t[64, 1].tolist() == [64, 255, 31]      # k = 32: unchanged
    assert t[95, 1].tolist() == [2, 7, 0]          # k = 1: >> 5


def test_shade_fade16_rows_ascend():
    t = gfx.shade_table(one(160, 16, 255), 16, FADE16)
    assert t[0, 1].tolist() == [10, 1, 15]
    assert t[15, 1].tolist() == [160, 16, 255]


def test_fade16_row_is_16a_alpha_premultiply():
    # .16a word (alpha << 9 | index << 1) is a byte offset into the table:
    # row a, column index -> colour * (a + 1) / 16
    t = gfx.shade_table(one(160, 16, 255), 16, FADE16)
    word = (7 << 9) | (1 << 1)
    assert t.reshape(-1, 3)[word // 2].tolist() == [160 * 8 // 16, 16 * 8 // 16, 255 * 8 // 16]


def test_shade_gray_ignores_tint():
    t = gfx.shade_table(one(30, 60, 90), 16, GRAY, tint=(50, 50, 50))
    assert t[8, 1].tolist() == [60, 60, 60]        # mean at k = N / 2
    assert t[0, 1].tolist() == [120, 120, 120]


def test_pack16():
    assert gfx.pack16(np.array([255, 255, 255])) == 0xFFFF
    assert gfx.pack16(np.array([255, 0, 0])) == 0xF800
    assert gfx.pack16(np.array([0, 255, 0]), (5, 5, 5)) == 0x03E0
    assert gfx.pack16(np.array([8, 4, 8])) == (1 << 11) | (1 << 5) | 1


def test_unpack16_extremes():
    assert gfx.unpack16(0xFFFF).tolist() == [255, 255, 255]
    assert gfx.unpack16(0).tolist() == [0, 0, 0]


# --- code palettes and day/night --------------------------------------------

def test_code_ramp_palettes():
    pals = {p.name: p.rgb for p in gfx.code_palettes()}
    assert pals["ramp_0x62a6f0"][255].tolist() == [0xb9, 0x9f, 0x49]
    assert pals["ramp_0x62a6f0"][128].tolist() == [128 * 0xb9 // 255, 128 * 0x9f // 255,
                                                   128 * 0x49 // 255]
    assert not pals["ramp_0x62ab10"].any()


def test_code_ramps16():
    r = gfx.code_ramps16()
    assert len(r) == 14 and all(t.shape == (16, 3) for t in r.values())
    assert r[0x629c48][15].tolist() == [255, 255, 255]
    assert r[0x629c68][0].tolist() == [192, 180, 120] and r[0x629c68][15].tolist() == [32, 32, 32]


@pytest.mark.parametrize("hour,tint", [(12, (0, 0, 0)), (0, (0, 12, 48)), (23, (0, 12, 48)),
                                       (2, (0, 12, 48)), (4, (24, 12, 0)), (6, (0, 0, 0)),
                                       (18, (0, 0, 0)), (20, (24, 0, 8))])
def test_daylight_tint_at_hour_start(hour, tint):
    assert gfx.daylight_tint(hour * 60) == tint


def test_daylight_tint_is_continuous_and_disableable():
    for h in (2, 4, 18, 20):
        before = gfx.daylight_tint(h * 60 - 1)
        after = gfx.daylight_tint(h * 60)
        assert max(abs(a - b) for a, b in zip(before, after)) <= 1
    assert gfx.daylight_tint(0, enabled=False) == (0, 0, 0)


def test_player_text_ramp_pairs_levels():
    rgb = np.zeros((256, 3), np.uint8)
    rgb[TEAM_COLOR_INDEX] = (80, 160, 240)
    ramp = gfx.player_text_ramp(rgb)
    assert ramp.shape == (16, 3)
    assert ramp[0].tolist() == ramp[1].tolist() == [10, 20, 30]      # x 1/8
    assert ramp[15].tolist() == [80, 160, 240]                       # x 8/8


# --- lighting ---------------------------------------------------------------

def test_daylight_params_continuous():
    prev = gfx.daylight(0)
    for t in range(1, 24 * 60):
        cur = gfx.daylight(t)
        assert abs(cur.ambient - prev.ambient) <= 1 and abs(cur.diffuse - prev.diffuse) <= 1, t
        prev = cur


def test_daylight_fixed_points():
    assert astuple(gfx.daylight(12 * 60))[1:5] == (14, 32, 4, 2)
    assert astuple(gfx.daylight(0))[1:5] == (32, 8, 8, 4)
    assert astuple(gfx.daylight(3 * 60))[1:5] == (30, 14, 6, 3)
    assert astuple(gfx.daylight(0, enabled=False))[1:5] == (14, 32, 4, 2)
    assert gfx.daylight(6 * 60).angle == pytest.approx(-0.78539815)
    assert gfx.daylight(18 * 60 - 1).angle == pytest.approx(0.78539815, abs=0.003)


def test_terrain_light_flat_ground():
    day, night = gfx.daylight(12 * 60), gfx.daylight(0)
    flat = np.zeros((4, 4), np.int8)
    assert gfx.terrain_light(flat, day.angle, day.ambient, day.diffuse)[1, 1] == 46
    assert gfx.terrain_light(flat, night.angle, night.ambient, night.diffuse)[1, 1] == 64
    assert gfx.terrain_light(flat, 0.0, 14, 32)[0, 0] == 0          # border untouched


def test_terrain_light_slope_and_clamp():
    # ground rising toward +y (down the screen) is darker (higher row) than
    # flat ground, and ground falling toward +y is brighter
    rise = np.repeat(np.arange(0, 40, 10)[:, None], 4, 1).astype(np.int8)
    assert gfx.terrain_light(rise, 0.0, 14, 32)[1, 1] > 46
    assert gfx.terrain_light(rise[::-1], 0.0, 14, 32)[1, 1] < 46
    cliff = np.zeros((3, 3), np.int8)
    cliff[0, :] = 127
    assert gfx.terrain_light(cliff, 0.0, 255, 255)[1, 1] == 94      # clamped to 94


def test_object_light_row():
    assert gfx.object_light_row(gfx.daylight(12 * 60).ambient) == 3
    assert gfx.object_light_row(gfx.daylight(0).ambient) == 8


# --- game files ---------------------------------------------------------------

@needs_samples
def test_every_palette_in_install_parses():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import validate_palettes
    seen = 0
    for rel, kind, pals in gfx.find_palettes(DATA):
        assert validate_palettes.check_file(os.path.join(DATA, rel), kind, pals) == [], rel
        for p in pals:
            assert p.rgb.shape == (256, 3) and p.rgb.dtype == np.uint8
            assert 0 <= p.rgb.min() and p.rgb.max() <= 255
        seen += len(pals)
    assert seen == 2973


@needs_samples
def test_channels_are_8_bit_not_vga_6_bit():
    p = gfx.load_pal(os.path.join(GRAPHICS, "units", "monsters", "bat", "palette.pal"))
    assert p.rgb.max() > 63 and (p.rgb & 3).any()


@needs_samples
def test_human_pal_player_colours_differ_at_index_164():
    pals = gfx.load_human(os.path.join(GRAPHICS, "units", "humans", "human.pal"))
    assert len(pals) == 16
    assert len({tuple(p.rgb[TEAM_COLOR_INDEX]) for p in pals}) == 16


@needs_samples
def test_terrain_tiles_share_one_palette():
    tiles = sorted(f for f in os.listdir(os.path.join(GRAPHICS, "terrain")) if f.startswith("tile"))
    first = gfx.load_palettes(os.path.join(GRAPHICS, "terrain", tiles[0]))[0]
    for f in tiles[1:]:
        assert gfx.load_palettes(os.path.join(GRAPHICS, "terrain", f))[0] == first
