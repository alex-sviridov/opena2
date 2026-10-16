"""File-level tests: PNG/BMP I/O and checks against the game install in
samples/ (skipped when it is absent)."""

import os

import numpy as np
import pytest
from PIL import Image

from allods2 import graphics as gfx
from allods2.common import DATA

GRAPHICS = os.path.join(DATA, "graphics")

needs_samples = pytest.mark.skipif(not os.path.isdir(GRAPHICS),
                                   reason="game install not present in samples/")


def test_bmp24_top_row_first(tmp_path):
    img = np.array([[[255, 0, 0], [0, 255, 0]], [[0, 0, 255], [1, 2, 3]]], np.uint8)
    p = tmp_path / "t.bmp"
    Image.fromarray(img).save(p)          # Pillow writes bottom-up DIBs
    bmp = gfx.load_bmp(str(p))
    assert bmp.index is None
    assert np.array_equal(bmp.rgb, img)


def test_bmp8_keeps_indices_and_palette(tmp_path):
    im = Image.fromarray(np.array([[0, 1], [2, 1]], np.uint8), "P")
    im.putpalette([0, 0, 0, 10, 20, 30, 40, 50, 60] + [0] * 759)
    p = tmp_path / "t.bmp"
    im.save(p)
    bmp = gfx.load_bmp(str(p))
    assert bmp.index.tolist() == [[0, 1], [2, 1]]
    assert bmp.rgb[1, 0].tolist() == [40, 50, 60]


def test_png_roundtrip(tmp_path):
    img = np.arange(8, dtype=np.uint8).reshape(1, 2, 4)
    p = tmp_path / "t.png"
    gfx.write_png(str(p), img)
    assert np.array_equal(np.asarray(Image.open(p)), img)


def consistent(rel, kind, count=None):
    sf = gfx.SpriteFile.load(os.path.join(GRAPHICS, rel))
    assert sf.kind == kind
    if count is not None:
        assert len(sf) == count
    for s in sf.sprites:
        used, size, _ = gfx.check_sprite(s, kind)
        assert used == size
    return sf


@needs_samples
@pytest.mark.parametrize("rel,kind,count,has_palette", [
    ("units/heroes/archer/sprites.256", "256", 168, True),
    ("units/heroes/archer/spritesb.256", "smooth", 168, True),
    ("inventory/0705302.16a", "16a", 1, True),
    ("font1/font1.16", "16", 224, False),
])
def test_sample_sprites_consistent(rel, kind, count, has_palette):
    sf = consistent(rel, kind, count)
    if has_palette is not None:
        assert (sf.palette is not None) == has_palette


@needs_samples
def test_unit_pal_matches_embedded():
    d = os.path.join(GRAPHICS, "units", "monsters", "bat")
    assert np.array_equal(gfx.load_pal_file(os.path.join(d, "palette.pal")),
                          gfx.SpriteFile.load(os.path.join(d, "sprites.256")).palette)


@needs_samples
def test_human_pal():
    pals = gfx.load_human_palettes(os.path.join(GRAPHICS, "units", "heroes_l", "human.pal"))
    assert len(pals) == 16


@needs_samples
def test_terrain_bmp_is_tile_strip():
    bmp = gfx.load_bmp(os.path.join(GRAPHICS, "terrain", "tile1-00.bmp"))
    assert bmp.width == 32 and bmp.height % 32 == 0


def test_bmp64k_pack16_bgr_order(tmp_path):
    img = np.array([[[0xff, 0x80, 0x40]]], np.uint8)       # R, G, B
    p = tmp_path / "t.bmp"
    Image.fromarray(img).save(p)
    bmp = gfx.load_bmp(str(p))
    assert bmp.rgb16().tolist() == [[0xfc08]]
    assert bmp.rgb16((5, 5, 5)).tolist() == [[0x7e08]]


def test_bmp64k_colour_key_drops_near_black(tmp_path):
    img = np.array([[[7, 3, 7], [8, 0, 0], [0, 4, 0]]], np.uint8)
    p = tmp_path / "t.bmp"
    Image.fromarray(img).save(p)
    assert gfx.load_bmp(str(p)).key_mask().tolist() == [[False, True, True]]
