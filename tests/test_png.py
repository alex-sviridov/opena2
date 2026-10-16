"""Synthetic tests for docs/formats/png.md (a2mgr paper-doll PNG layers)."""

import glob
import os

import numpy as np

from allods2 import graphics as gfx
from allods2.common import DATA

from helpers import needs

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


@needs("graphics", "equipment")
def test_game_equipment_pngs_are_paperdoll_layers():
    assert EQUIP
    for p in EQUIP:
        rgba = gfx.load_png(p)
        assert rgba.shape == (H, W, 4), p
        assert os.path.basename(p)[:-4].isdigit() and not os.path.exists(p[:-4] + ".256")


def test_partial_alpha_uses_sse_mixed_precision():
    # dst term in double, src term in single: A 65, green 51 under black
    # gives 38 (all-single arithmetic would give 37)
    dst = np.full((H, W), rgb565(0, 51, 0), np.uint16)
    gfx.blend_png_layer(dst, layer(0, 0, 0, 65))
    assert (int(dst[0, 0]) >> 5) & 63 == 38


# --- compositing order and menu blit (png.md) ---------------------------------

def test_doll_order_mage():
    order = gfx.doll_layer_order(mage=True, two_handed=False)
    assert order[:3] == [("P", 7), ("B",), ("P", 11)] and order[-1] == ("S", 7)
    assert ("P", 8) not in order and ("P", 2) not in order
    mask = gfx.doll_mask_order(mage=True, two_handed=False)
    assert (("P", 8), 9) in mask and (("B",), 0) in mask
    assert [m[0] for m in mask].index(("P", 8)) == [m[0] for m in mask].index(("P", 0)) - 1


def test_doll_order_fighter_two_handed():
    one = gfx.doll_layer_order(mage=False, two_handed=False)
    two = gfx.doll_layer_order(mage=False, two_handed=True)
    assert one[0] == ("B",) and one[8] == ("P", 0) and one[-1] == ("P", 1)
    assert two[-1] == ("P", 0) and ("P", 1) not in two and two.count(("P", 0)) == 1
    mask = gfx.doll_mask_order(mage=False, two_handed=True)
    assert ("B",) not in [m[0] for m in mask] and mask[-1] == (("P", 0), 1)


def test_menu_blit_opaque_has_no_floor_and_clamps():
    dst = np.full((10, 20), 0xFFFF, np.uint16)
    img = np.zeros((2, 2, 4), np.uint8)
    img[0, 0] = (0, 0, 0, 255)                # opaque black stays 0 (doll would give 1)
    img[0, 1] = (255, 255, 255, 0)            # skipped
    img[1, 0] = (0, 0, 0, 100)                # hard: <= 127 skipped
    img[1, 1] = (0, 0, 0, 200)                # hard: opaque
    gfx.blend_menu_png(dst, img, 3, 4, hard=True)
    assert dst[4, 3] == 0 and dst[4, 4] == 0xFFFF and dst[5, 3] == 0xFFFF and dst[5, 4] == 0


def test_menu_blit_partial_alpha_and_edges():
    dst = np.zeros((4, 4), np.uint16)
    img = np.zeros((1, 1, 4), np.uint8)
    img[0, 0] = (255, 255, 255, 128)
    gfx.blend_menu_png(dst, img, 0, 0)
    assert dst[0, 0] == rgb565(15, 31, 15)     # no "< 2 -> 1" rule either
    wide = np.full((1, 3, 4), 255, np.uint8)
    dst[:] = 0
    gfx.blend_menu_png(dst, wide, 2, 0)        # would cross the right edge: dropped
    assert (dst == 0).all()
    gfx.blend_menu_png(dst, wide, -1, 0)       # negative x skips source columns
    assert (dst[0, :2] == 0xFFFF).all() and dst[0, 2] == 0
