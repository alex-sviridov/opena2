"""Engine world state, synthetic (spec 2026-10-16-world-state-design.md): always runs."""

import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

import engine.__main__ as cli
from allods2.databin import Record
from allods2.formats.objects import Structure
from engine.world import (OBJECT_ID_BASE, STRUCTURE_ID_BASE, MapObject, World,
                          structure_footprint)

N = 32
GRASS = 0 << 6 | 0 << 4 | 0          # set 0 strip 0 row 0: Land
WATER = 8 << 6 | 0x200               # set 8 water
MOUNTAIN = 7 << 6 | 3 << 4 | 0       # set 7 strip 3 row 0: pure Mountain


def world(tiles=None):
    t = np.full((N, N), GRASS, np.uint16)
    if tiles:
        for (x, y), v in tiles.items():
            t[y, x] = v
    return World(t, np.zeros((N, N), np.int8), "syn", terrain=t)


def obj(i, x, y):
    return MapObject(i, "object", 1, x, y)


def struct(i, x, y, fp, kind="structure"):
    return MapObject(i, kind, 5, x, y, footprint=tuple(fp))


def check(w):
    """Index and block equal a from-scratch rebuild; index has no dead keys or ghosts."""
    assert np.array_equal(w.block, w.rebuild_block())
    seen = {}
    for i, o in w.objects.items():
        for dx, dy, _ in o.footprint:
            c = (o.x + dx, o.y + dy)
            if 0 <= c[0] < N and 0 <= c[1] < N:
                seen.setdefault(c, set()).add(i)
    assert w._cells == seen and all(w._cells.values())


def test_border_and_terrain_base():
    w = world({(10, 10): WATER, (11, 10): MOUNTAIN, (12, 10): GRASS | 0x2000})
    assert w.block[10, 10] == 1 and w.block[10, 11] == 1 and w.block[10, 12] == 1
    assert w.block[10, 13] == 0
    assert (w.block[:8] == 0x1F).all() and (w.block[:, N - 8:] == 0x1F).all()
    assert w.blocked(10, 10) and not w.blocked(13, 10) and w.blocked(-1, 0) and w.blocked(5, 5)
    assert w.walkable(1)[10, 13] and not w.walkable(1)[10, 10]


def test_object_add_remove_move_restores_block():
    w = world({(10, 10): WATER})
    before = w.block.copy()
    w.add_object(obj(1, 10, 10))
    assert w.block[10, 10] == 5          # object replaces the water bit
    w.add_object(obj(2, 12, 12))
    assert w.block[12, 12] == 5 and w.objects_at(12, 12) == {2}
    check(w)
    w.move_object(2, 13, 12)
    assert w.block[12, 12] == 0 and w.block[12, 13] == 5 and w.objects_at(12, 12) == frozenset()
    check(w)
    w.remove_object(2)
    w.remove_object(1)
    assert np.array_equal(w.block, before) and not w._cells
    check(w)


def test_object_on_border_stays_border():
    w = world()
    w.add_object(obj(1, 3, 3))
    assert w.block[3, 3] == 0x1F


def test_structure_solid_free_and_water():
    w = world({(10, 10): WATER, (11, 10): WATER})
    # 2x1 structure: left cell solid, right cell present but free
    w.add_object(struct(1, 10, 10, [(0, 0, True), (1, 0, False)]))
    assert w.block[10, 10] == 1 | 5 and w.block[10, 11] == 0     # free cell loses bits 0 and 2
    check(w)
    w.remove_object(1)
    assert w.block[10, 10] == 1 and w.block[10, 11] == 1
    # a bridge (mask 0): water becomes walkable
    w.add_object(struct(2, 10, 10, [(0, 0, False), (1, 0, False)], "bridge"))
    assert w.block[10, 10] == 0 and w.block[10, 11] == 0
    check(w)


def test_structure_overlap_first_wins_and_registration_aborts():
    """FUN_00559890 fails on a cell that already holds a structure and FUN_005599df
    then stops: the rest of the later structure stays unregistered (map.md part 4)."""
    w = world()
    a = struct(1, 10, 10, [(0, 0, True), (1, 0, True)])
    b = struct(2, 11, 10, [(0, 0, False), (1, 0, False), (2, 0, True)])
    w.add_object(a)
    w.add_object(b)
    # b's first cell (11, 10) is a's: b registers nothing, so its cells 12 and 13 stay 0
    assert w.block[10, 10] == 5 and w.block[10, 11] == 5 and w.block[10, 12] == 0
    assert w.block[10, 13] == 0 and w.objects_at(11, 10) == {1, 2}   # still geometrically there
    check(w)
    w.remove_object(1)                   # a released its cells; b is re-resolved and registers
    assert w.block[10, 10] == 0 and w.block[10, 11] == 0 and w.block[10, 13] == 5
    check(w)
    w.add_object(a)                      # a is now the later one: it loses cell 11, keeps 10
    assert w.block[10, 10] == 5 and w.block[10, 11] == 0
    check(w)
    # a conflict in the middle: cells before it are registered, the rest are not
    c = struct(3, 9, 10, [(0, 0, True), (1, 0, True), (2, 0, True), (3, 0, True)])
    w.add_object(c)
    assert w.block[10, 9] == 5 and w.block[10, 10] == 5 and w.block[10, 12] == 0
    check(w)
    seq = w.objects[2].seq
    w.move_object(2, 5, 12)              # moving keeps the seq
    assert w.objects[2].seq == seq
    check(w)


def test_structure_clipped_at_map_edge():
    w = world()
    w.add_object(struct(1, N - 1, 10, [(0, 0, True), (1, 0, True), (2, 0, True)]))
    assert w.objects_at(N - 1, 10) == {1} and (N, 10) not in w._cells
    check(w)
    w.remove_object(1)
    check(w)


def test_failed_add_leaves_world_unchanged():
    w = world()
    w.add_object(obj(1, 10, 10))
    block, cells, n = w.block.copy(), {k: set(v) for k, v in w._cells.items()}, w._next_seq
    for bad in (obj(1, 12, 12), obj(2, N, 3), obj(3, -1, 3), MapObject(4, "bogus", 1, 3, 3)):
        with pytest.raises(ValueError):
            w.add_object(bad)
    with pytest.raises(ValueError):
        w.move_object(1, 99, 99)
    with pytest.raises(KeyError):
        w.remove_object(77)
    assert np.array_equal(w.block, block) and w._cells == cells and w._next_seq == n
    assert list(w.objects) == [1] and (w.objects[1].x, w.objects[1].y) == (10, 10)


def test_block_is_read_only():
    w = world()
    with pytest.raises(ValueError):
        w.block[0, 0] = 3


def test_random_sequence_matches_rebuild():
    rng = np.random.default_rng(3)
    w = world({(x, 9): WATER for x in range(8, 14)})
    live = []
    for step in range(120):
        r = rng.integers(0, 3)
        if r == 0 or not live:
            i = 100 + step
            x, y = (int(v) for v in rng.integers(6, N - 5, 2))
            if rng.integers(0, 2):
                w.add_object(obj(i, x, y))
            else:
                fp = [(dx, dy, bool(rng.integers(0, 2))) for dy in range(2) for dx in range(3)
                      if rng.integers(0, 4)]
                w.add_object(struct(i, x, y, fp or [(0, 0, True)]))
            live.append(i)
        elif r == 1:
            w.move_object(live[rng.integers(0, len(live))], *(int(v) for v in rng.integers(0, N, 2)))
        else:
            w.remove_object(live.pop(int(rng.integers(0, len(live)))))
        check(w)


# --- from_map with a synthetic map -----------------------------------------------

def fake_map(structures, placed, extra_outside=0):
    t = np.full((N, N), GRASS, np.uint16)
    t[10, 10] |= 0x2000                                  # dirt flag: block 1, cleared in cells
    layer = np.zeros((N, N), np.uint8)
    for p in placed:
        layer[p.y, p.x] = p.id + 1
    layer[N - 2, 3] = 5                                   # outside the loaded window
    return SimpleNamespace(
        name="fake.alm", terrain=t, runtime_terrain=lambda: t & np.uint16(0xDFFF),
        heights_i8=np.zeros((N, N), np.int8), structures=structures, objects=layer,
        placed_objects=lambda window=True: list(placed))


class FakeAssets:
    def __init__(self, n_stats=10):
        self.stats = [Record("S%d" % i, [2, 1, 4, 0, 1, 3]) for i in range(n_stats)]

    def databin(self):
        return SimpleNamespace(structures=self.stats)

    def objects_reg(self):
        return {1: {}, 2: {}}


def test_from_map_ids_footprints_hp_and_unknown():
    from allods2.formats.objects import MapObject as Placed
    structs = [Structure(10, 12, 3, 100, 2, 1), Structure(14, 12, 4, 0, 1, 2),
               Structure(9, 9, 99, 10, 1, 3),                       # not in data.bin
               Structure(12, 14, 0x21, 100, 1, 4, size=(2, 2))]    # bridge
    placed = [Placed(11, 11, 1), Placed(13, 11, 77)]               # 77 not in objects.reg
    w = World.from_map(fake_map(structs, placed), FakeAssets())
    assert sorted(w.objects) == [0x6001, 0x6002, 0x6003, 0x6004, OBJECT_ID_BASE, OBJECT_ID_BASE + 1]
    s1, s2, s3, br = (w.objects[STRUCTURE_ID_BASE + i] for i in (1, 2, 3, 4))
    assert s1.footprint == ((0, 0, True), (1, 0, False)) and s1.hp == s1.hp_max == 1000
    assert s2.hp == 0 and s2.flags == 1 and s2.hp_max == 1000 and s2.owner == 1 and s2.uid == 2
    assert not s3.known and s3.footprint == ((0, 0, True),)
    assert br.kind == "bridge" and all(not s for *_, s in br.footprint) and len(br.footprint) == 4
    assert w.report.unknown == [("structure", 99, 9, 9), ("object", 77, 13, 11)]
    assert w.report.ignored_outside_window == 1
    assert w.report.counts[("object", 1)] == 1 and w.report.counts[("bridge", 0x21)] == 1
    assert not w.objects[OBJECT_ID_BASE + 1].known
    assert w.block[10, 10] == 1 and w.cells[10, 10] == GRASS      # dirt in block, not in cells
    assert np.array_equal(w.block, w.rebuild_block())
    check(w)


def test_from_map_duplicate_structure_id_is_error():
    structs = [Structure(10, 12, 3, 1, 1, 7), Structure(14, 12, 3, 1, 1, 7)]
    with pytest.raises(ValueError):
        World.from_map(fake_map(structs, []), FakeAssets())


def test_structure_footprint_mask_repeats_mod_32():
    s = Structure(0, 0, 1, 1, 1, 1)
    stats = [Record("X", [6, 6, 0, 0, 0, 0xFFFFFFFF])]           # 36 cells, all present, none solid
    fp, known, hp = structure_footprint(s, stats)
    assert known and len(fp) == 36 and hp == 1000


# --- CLI ------------------------------------------------------------------------------

def test_world_info_prints_unknown(monkeypatch, capsys):
    from allods2.formats.objects import MapObject as Placed
    structs = [Structure(9, 9, 99, 10, 1, 3)]
    w = World.from_map(fake_map(structs, [Placed(13, 11, 77)]), FakeAssets())
    monkeypatch.setattr(cli, "_world", lambda a: w)
    assert cli.main(["world-info", "x"]) == 0
    out = capsys.readouterr().out
    assert "unknown types: 2" in out and "structure type 99 at (9, 9)" in out \
        and "object type 77 at (13, 11)" in out and "ignored outside the window: 1" in out
    assert cli.main(["world-info", "x", "--strict"]) == 2


def test_world_dump_is_deterministic_json(monkeypatch, tmp_path):
    import json
    w = world()
    w.add_object(obj(1, 10, 10))
    monkeypatch.setattr(cli, "_world", lambda a: w)
    d = tmp_path / "d.json"
    assert cli.main(["world-dump", "x", str(d)]) == 0
    data = json.loads(d.read_text())
    assert d.read_text() == w.dump_json() and "seq" not in data["objects"][0]
    assert len(data["block"]) == N and data["block"][10][10 * 2:10 * 2 + 2] == "05"


def test_world_path_never_imports_pygame():
    code = ("import sys, engine.world, engine.__main__ as m\n"
            "w = m.World if hasattr(m, 'World') else None\n"
            "assert 'pygame' not in sys.modules, 'pygame imported'\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
