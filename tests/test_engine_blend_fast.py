"""The packed-word shadow / half blends equal the per-channel formulas on random inputs (clipped too)."""

import numpy as np
import pytest

from engine.backend_pygame.sprites import Frame, SparseMask, frame_half, frame_shadow, pack_rgb


@pytest.mark.parametrize("x,y", [(5, 4), (-3, -2), (28, 17), (-40, 3), (7, 40)])
def test_shadow_and_half_equal_the_channel_formulas(x, y):
    rng = np.random.default_rng(abs(x * 31 + y))
    bg = rng.integers(0, 256, (20, 32, 3)).astype(np.uint8)
    mask = rng.random((9, 12)) < 0.5
    src = rng.integers(0, 128, (9, 12, 3)).astype(np.uint8)
    for level in (2, 4, 8):
        f = Frame(32, 20)
        f.bytes[..., :3] = bg
        frame_shadow(f, x, y, SparseMask(mask, 3), level)
        want = bg.copy()
        for r, c in zip(*np.nonzero(mask)):
            yy, xx = y + r, x + 3 + c
            if 0 <= yy < 20 and 0 <= xx < 32:
                want[yy, xx] = bg[yy, xx].astype(np.uint16) * (16 - level) >> 4
        assert np.array_equal(f.bytes[..., :3], want)
    f = Frame(32, 20)
    f.bytes[..., :3] = bg
    frame_half(f, x, y, SparseMask(mask, 0, pack_rgb(src)))
    want = bg.copy()
    for r, c in zip(*np.nonzero(mask)):
        yy, xx = y + r, x + c
        if 0 <= yy < 20 and 0 <= xx < 32:
            want[yy, xx] = src[r, c] + (bg[yy, xx] >> 1)
    assert np.array_equal(f.bytes[..., :3], want)
