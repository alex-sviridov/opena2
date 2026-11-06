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
        self.burn_start = {}


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


class _ObjAssets(_Assets):
    def object_set(self, tid):
        return _Aset({"DeadObject": 5 if tid == 1 else -1})


class _BurnWorld(_World):
    def __init__(self, objs, burn):
        super().__init__(objs)
        self.burn_start = burn

    def objects_at(self, x, y):
        return frozenset(i for i, o in self.objects.items() if (o.x, o.y) == (x, y))


def test_burning_cell_stamps_radius_one_by_counter_and_ends_at_22():
    w = _BurnWorld([_Ent(1, 4, 4, kind="object"), _Ent(2, 9, 9, kind="object")], {(4, 4): 100, (9, 9): 100})
    a = _ObjAssets({})
    plus = {(4, 4), (3, 4), (5, 4), (4, 3), (4, 5)}                            # r = 1: dx^2 + dy^2 < 2
    assert L.light_map(w, a, 100) == {v: 36 for v in plus}                     # counter 0: phase 0 = 36
    assert L.light_map(w, a, 106)[(4, 4)] == 0                                 # counter 6 -> phase 3
    assert L.light_map(w, a, 116)[(4, 4)] == 20                                # counter 16 -> phase 8
    assert L.light_map(w, a, 121)[(4, 4)] == 36                                # counter 21 -> phase 10
    assert L.light_map(w, a, 122) == {} and L.light_map(w, a, 99) == {}        # removed at 22; not yet born
    assert (9, 9) not in L.light_map(w, a, 100)                                # object without DeadObject: no entry
