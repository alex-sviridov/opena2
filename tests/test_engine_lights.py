"""The dynamic light map (engine/view/lights.py, lighting.md section 3-4): structure lights, cell rows, terrain corners."""

import numpy as np

from engine.view import lights as L


class _Aset:
    def __init__(self, rec, W=2, TH=2):
        self.rec, self.W, self.TH = rec, W, TH


class _Assets:
    def __init__(self, recs):
        self.recs = recs

    def structure_set(self, tid, size):
        return _Aset(self.recs[tid])


class _Ent:
    def __init__(self, tid, x, y, hp=10, kind="structure"):
        self.type_id, self.x, self.y, self.hp, self.kind = tid, x, y, hp, kind


class _World:
    def __init__(self, objs):
        self.objects = {i: o for i, o in enumerate(objs)}
        self.carriers = []


def test_structure_light_writes_the_footprint_corner_vertices_with_the_pulse():
    w = _World([_Ent(1, 5, 7), _Ent(2, 20, 20), _Ent(1, 30, 30, hp=0)])
    a = _Assets({1: {"LightRadius": 1, "LightPulse": 8}, 2: {}})
    m = L.light_map(w, a, 3)
    assert set(m) == {(x, y) for x in (5, 6, 7) for y in (7, 8, 9)}          # R = 1: x .. x + W; the dead one and the unlit type write nothing
    assert set(m.values()) == {33}                                           # pulse 8, clock 3 (lighting.md: 28 30 31 33 ...)
    assert L.light_map(w, a, 11)[(5, 7)] == 27


def test_cell_row_and_terrain_corners_follow_the_light_map():
    lights = {(5, 7): 0, (6, 7): 0, (5, 8): 0, (6, 8): 0}
    assert L.cell_row(lights, 5, 7, 32) == 0                                 # torch: row 0 (x2)
    assert L.cell_row(lights, 20, 20, 32) is None
    base = np.full((40, 40), 30, np.int16)
    assert L.corner_lights(lights, base, 5, 7) == (0, 0, 0, 0)
    assert L.corner_lights(lights, base, 6, 7) == (0, 30, 0, 30)              # min(terrain, light) only where lit
    assert L.corner_lights(lights, base, 9, 9) is None
