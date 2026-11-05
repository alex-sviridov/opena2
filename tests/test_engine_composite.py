"""The vectorised terrain cell composite equals the column-by-column reference (`TerrainView.composite_reference`)."""

import numpy as np
import pytest

from allods2.graphics.terrain import TerrainSet, cell_value
from engine.view import TerrainView
from engine.world import World


def _view(seed, size=14):
    rng = np.random.default_rng(seed)
    w = World.__new__(World)
    w.heights = rng.choice([0, 0, 0, 3, -5, 12, 40, 100, -100, 127, -128], size=(size, size)).astype(np.int16)
    sets, strips = rng.integers(0, 16, size=(size, size)), rng.integers(0, 4, size=(size, size))
    w.cells = np.array([[cell_value(int(sets[r, c]), int(strips[r, c]), int(rng.integers(0, 5)), bool(rng.integers(0, 2)))
                         for c in range(size)] for r in range(size)], np.uint16)
    tiles = {(s, j): rng.integers(0, 256, size=(128, 32), dtype=np.uint8) for s in range(16) for j in range(4)}
    terrain = TerrainSet(tiles, rng.integers(0, 4, size=(128, 32), dtype=np.uint8), rng.integers(0, 256, size=(256, 3), dtype=np.uint8))
    return TerrainView(w, terrain)


@pytest.mark.parametrize("seed", range(4))
def test_composite_equals_reference(seed):
    tv = _view(seed)
    n = 0
    for row in range(13):
        for col in range(13):
            for phase in (0, 3):
                a, b = tv.composite(col, row, phase), tv.composite_reference(col, row, phase)
                assert (a is None) == (b is None)
                if a is not None:
                    assert a[1] == b[1] and (a[0] == b[0]).all()
                    n += 1
    assert n > 100
