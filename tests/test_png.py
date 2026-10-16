"""Synthetic tests for docs/formats/png.md (a2mgr paper-doll PNG layers)."""

import glob
import os

import numpy as np

from allods2 import graphics as gfx
from allods2.common import DATA

H, W = gfx.PAPERDOLL_H, gfx.PAPERDOLL_W


def layer(r, g, b, a):
    out = np.zeros((H, W, 4), np.uint8)
    out[0, 0] = (r, g, b, a)
    return out


def rgb565(r5, g6, b5):
    return (r5 << 11) | (g6 << 5) | b5


def test_alpha_zero_leaves_destination():
    dst = np.full((H, W), 0x1234, np.uint16)
    gfx.blend_png_layer(dst, layer(255, 255, 255, 0))
    assert (dst == 0x1234).all()


def test_opaque_copies_with_channels_at_least_one():
    dst = np.zeros((H, W), np.uint16)
    gfx.blend_png_layer(dst, layer(0, 0, 0, 255))
    assert dst[0, 0] == rgb565(1, 1, 1)
    gfx.blend_png_layer(dst, layer(255, 128, 64, 255))
    assert dst[0, 0] == rgb565(31, 32, 8)


def test_partial_alpha_blends_and_clamps():
    dst = np.full((H, W), rgb565(31, 63, 31), np.uint16)
    gfx.blend_png_layer(dst, layer(0, 0, 0, 128))
    t = np.float32(128) / np.float32(255)
    expect = [int(np.float32(top) * (np.float32(1) - t)) for top in (31, 63, 31)]
    assert dst[0, 0] == rgb565(*expect)
    dst[:] = 0
    gfx.blend_png_layer(dst, layer(8, 4, 8, 64))       # blends to 0 -> clamped to 1
    assert dst[0, 0] == rgb565(1, 1, 1)


def test_wrong_size_is_not_drawn():
    dst = np.zeros((H, W), np.uint16)
    gfx.blend_png_layer(dst, np.full((10, 10, 4), 255, np.uint8))
    assert not dst.any()


def test_hit_mask_threshold():
    mask = np.zeros((H, W), np.uint8)
    rgba = np.zeros((H, W, 4), np.uint8)
    rgba[0, 0, 3], rgba[0, 1, 3] = 127, 126
    gfx.png_hit_mask(mask, rgba, 7)
    assert mask[0, :2].tolist() == [7, 0]


def test_png_roundtrip_rgba(tmp_path):
    img = np.zeros((2, 3, 4), np.uint8)
    img[1, 2] = (1, 2, 3, 4)
    gfx.write_png(tmp_path / "x.png", img)
    assert (gfx.load_png(tmp_path / "x.png") == img).all()


EQUIP = sorted(glob.glob(os.path.join(DATA, "graphics", "equipment", "**", "*.png"), recursive=True))


def test_game_equipment_pngs_are_paperdoll_layers():
    if not EQUIP:
        import pytest
        pytest.skip("game files not available")
    for p in EQUIP:
        rgba = gfx.load_png(p)
        assert rgba.shape == (H, W, 4), p
        assert os.path.basename(p)[:-4].isdigit() and not os.path.exists(p[:-4] + ".256")
