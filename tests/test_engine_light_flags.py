"""Light / Darkness cell flags write the terrain light of four vertices and nothing recomputes it until the flag clears (`FUN_0041c18c`)."""

import numpy as np

from allods2.graphics.terrain import TerrainSet
from engine.view import TerrainView
from engine.world import World


def _view():
    w = World.__new__(World)
    w.heights = np.zeros((8, 8), np.int16)
    w.cells = np.zeros((8, 8), np.uint16)
    w.width = w.height = 8
    w.light_vertices, w.light_version, w.cells_version = {}, 0, 0
    terrain = TerrainSet({}, np.zeros((128, 32), np.uint8), np.zeros((256, 3), np.uint8))
    return w, TerrainView(w, terrain)


def test_darkness_and_light_write_four_vertices_and_clear_restores_them():
    w, tv = _view()
    base = tv.light.copy()
    v0 = tv.version
    w.light_write(3, 2, True, 0x50)
    assert tv.version != v0
    assert (tv.light[2:4, 3:5] == 0x50).all() and (tv.light != base).sum() == 4
    w.light_write(3, 2, False, 0x50)                       # FUN_004a5dd2(x, y, 2, 2): the same four vertices from the heights
    assert (tv.light == base).all()
    w.light_write(1, 1, True, 0)
    assert (tv.light[1:3, 1:3] == 0).all()


def test_a_neighbours_clear_takes_the_shared_vertices_and_a_day_step_drops_all():
    w, tv = _view()
    w.light_write(2, 2, True, 0x50)
    w.light_write(3, 2, True, 0x50)
    w.light_write(2, 2, False, 0x50)                        # vertices (3, 2) and (3, 3) belong to the cell at x = 3 as well: lost
    assert tv.light[2, 3] == tv.base_light[2, 3] and tv.light[2, 4] == 0x50
    tv.set_time_flow(True, 0)                               # FUN_0041d3b9 recompute: terrain light rebuilt for the whole map
    assert not w.light_vertices and (tv.light == tv.base_light).all()
