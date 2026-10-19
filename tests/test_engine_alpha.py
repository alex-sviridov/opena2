"""The `.16a` alpha blend of the engine's sprite cache (animation.md 4.4): `src * (a + 1) / 16 + dst * (15 - a) / 16`."""

import os

import numpy as np
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
pygame = pytest.importorskip("pygame")

from engine.backend_pygame.sprites import SpriteCache, alpha_mix, blend_alpha
from engine.view.drawlist import DrawItem

from helpers import GFS, needs_data


def test_alpha_mix_endpoints_and_truncation():
    src, dst = np.uint16(200), np.uint16(100)
    assert alpha_mix(src, dst, np.uint16(0)) == (200 * 1 >> 4) + (100 * 15 >> 4)       # 12 + 93
    assert alpha_mix(src, dst, np.uint16(15)) == 200                                     # a = 15: the source
    assert alpha_mix(src, dst, np.uint16(7)) == (200 * 8 >> 4) + (100 * 8 >> 4)          # 100 + 50
    assert alpha_mix(np.uint16(255), np.uint16(255), np.uint16(15)) == 255               # never above 255


def test_blend_alpha_changes_only_the_covered_pixels_and_clips():
    surf = pygame.Surface((6, 4))
    surf.fill((100, 100, 100))
    mask_t = np.array([[True, False], [True, True], [False, True]])                      # (w=3, h=2), x first
    src_t = np.full((3, 2, 3), 200, np.uint16)
    alpha_t = np.full((3, 2), 15, np.uint16)
    blend_alpha(surf, 1, 1, (mask_t, src_t, alpha_t))
    assert tuple(surf.get_at((1, 1))[:3]) == (200, 200, 200)
    assert tuple(surf.get_at((1, 2))[:3]) == (100, 100, 100)                              # uncovered
    assert tuple(surf.get_at((3, 2))[:3]) == (200, 200, 200)
    blend_alpha(surf, -2, -1, (mask_t, src_t, alpha_t))                                   # partly outside: clipped, no error
    blend_alpha(surf, 50, 50, (mask_t, src_t, alpha_t))                                   # fully outside


@needs_data
def test_the_firebolt_frame_builds_an_alpha_entry():
    from allods2.assets import AssetCache
    assets = AssetCache(GFS)
    pset = assets.projectile_set(10)
    assert pset is not None and pset.rec["A16"] == 1
    cache = SpriteCache(assets)
    item = DrawItem(kind="sprite", sprite=("projectile", 10, "main"), frame=0, blend="alpha")
    mask_t, src_t, alpha_t = cache.get(item)
    assert mask_t.any() and src_t.shape[:2] == mask_t.shape == alpha_t.shape and src_t.shape[2] == 3
    assert alpha_t[mask_t].max() <= 15
