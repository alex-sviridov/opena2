"""docs/formats/map.md part 4: objects (section 3) and structures (section 4)."""

import struct

import numpy as np
import pytest

from allods2.common import campaign_maps
from allods2.formats import Map
from allods2.formats import objects as O

from helpers import GFS, needs_data

MAPS = campaign_maps(GFS) if GFS else []
needs_maps = pytest.mark.skipif(not MAPS, reason="game files not present")

# Objects whose sprite file is absent from the archives (the 7 burning trees,
# animation.md §1.7); the campaign places them only outside the loaded window.
BURNING = {1, 4, 7, 10, 13, 16, 19}


def entry(x, y, t, a=100, b=2, c=1, size=None):
    d = struct.pack("<iiIHIh", (x << 8) + 0x80, (y << 8) + 0x80, t, a, b, c)
    return d + (struct.pack("<II", *size) if size else b"")


# --- synthetic: one test per rule ---------------------------------------------

def test_entry_fields_and_cells():
    s, = O.parse_structures(entry(67, 36, 55, a=0, b=3, c=7), 1)
    assert (s.x, s.y, s.type, s.intact, s.owner, s.uid, s.size) == (67, 36, 55, 0, 3, 7, None)
    assert not s.is_bridge


def test_bridges_carry_a_size_and_the_flag_forces_the_id():
    data = entry(10, 10, 0x21, size=(4, 9)) + entry(20, 20, 0x1000000 | 0x21, size=(3, 5)) \
        + entry(30, 30, 12)
    a, b, c = O.parse_structures(data, 3)
    assert (a.type, a.size) == (0x21, (4, 9))
    assert (b.type, b.size) == (0x21, (3, 5)) and b.is_bridge
    assert c.size is None and len(data) == 20 * 3 + 16


def test_sections_must_tile_exactly():
    with pytest.raises(ValueError):
        O.parse_structures(entry(1, 1, 5) + b"\0", 1)
    with pytest.raises(ValueError):
        O.parse_structures(entry(1, 1, 5)[:-2], 1)
    with pytest.raises(ValueError):
        O.parse_structures(struct.pack("<iiIHIh", 0, 0, 0x21, 0, 0, 0) + b"\0" * 4, 1)


def test_placed_objects_only_in_the_loaded_window():
    layer = np.zeros((30, 30), np.uint8)
    layer[10, 12] = 6                  # object 5
    layer[7, 12] = 3                   # row 7: outside the window
    layer[10, 22] = 3                  # column w-8: outside
    layer[25, 12] = 3                  # row h-5: inside; h-4 outside
    layer[26, 12] = 3
    assert O.placed_objects(layer) == [O.MapObject(12, 10, 5), O.MapObject(12, 25, 2)]
    assert len(O.placed_objects(layer, window=False)) == 5


def test_footprint_mask_is_row_major_and_wraps_at_32_bits():
    solid = O.mask_cells(3, 2, 55)                   # Goblin Hut 0b110111
    assert solid.tolist() == [[True, True, True], [False, True, True]]
    wide = O.mask_cells(11, 4, 0x7F1FF7FF)           # 44 cells: bit i & 31
    assert wide.shape == (4, 11) and wide[3, 10] == wide[1, 0] and not wide[1, 0]


class Stats:
    def __init__(self, *params):
        self.params = list(params)


def test_stamp_sets_and_clears_the_block_bits():
    stats = [Stats(3, 2, 4, 300, 55, 63)]
    block = np.full((20, 20), 0x01, np.uint8)
    block[12, 7] = 0x1F                                   # unrelated
    out = O.stamp_structures(block, [O.Structure(5, 10, 1, 100, 2, 1)], stats)
    assert out[10, 5:8].tolist() == [5, 5, 5]             # solid: bits 0 and 2
    assert out[11, 5] == 0x00                             # hut door: bit 0 cleared
    assert out[11, 6] == 5 and out[9, 5] == 1 and out[12, 7] == 0x1F
    assert block[10, 5] == 1                              # the input is not modified


def test_cells_outside_the_present_mask_are_untouched():
    stats = [Stats(3, 3, 3, 1000, 63, 63)]                # Cave: 3 x 3 data, 6 cells present
    block = np.full((20, 20), 0x01, np.uint8)
    out = O.stamp_structures(block, [O.Structure(5, 10, 1, 100, 2, 1)], stats)
    assert (out[10:12, 5:8] == 5).all() and (out[12, 5:8] == 1).all()


def test_bridge_footprint_is_walkable():
    block = np.full((20, 20), 0x01, np.uint8)             # "water"
    out = O.stamp_structures(block, [O.Structure(4, 4, 0x21, 100, 2, 1, (6, 3))], [])
    assert (out[4:7, 4:10] == 0).all() and out.sum() == 20 * 20 - 18


def test_ground_height_matches_the_unit_formula():
    h = np.zeros((10, 10), np.int8)
    h[2:4, 2:4] = (40, 80), (20, 60)
    # 1 x 1 at a cell centre: mean of the four corners
    assert O.ground_height(h, (2 << 8) + 0x80, (2 << 8) + 0x80, 1, 1) == 50
    assert O.cell_relief(h, 2, 2) == 50
    assert O.cell_relief(-np.ones((4, 4), np.int8) * 3, 1, 1) == -3     # truncates toward 0
    assert O.ground_height(np.zeros((4, 4), np.uint8), 0x80, 0x80, 1, 1) == 0


# --- the install ----------------------------------------------------------------

@needs_maps
def test_every_structure_section_tiles_exactly_and_resolves():
    from allods2.anim.structures import load_structure_records
    from allods2.databin import databin
    stats = databin(GFS).structures
    recs = load_structure_records(GFS)
    total = bridges = 0
    for p in MAPS:
        m = Map.load(p, GFS)
        assert len(m.structures) == m.header.n_sec4, p
        for s in m.structures:
            total += 1
            bridges += s.is_bridge
            assert s.type in recs and s.type <= len(stats), (p, s)
            w, h, _, _ = O.footprint(s, stats)
            assert 8 <= s.x and s.x + w <= m.width - 8, (p, s)       # inside the playable area
            assert 8 <= s.y and s.y + h <= m.height - 8, (p, s)
            assert s.intact in (0, 10, 100) and 1 <= s.owner <= 8, (p, s)
            if s.is_bridge:
                assert s.type == 0x21 and all(0 < v < 32 for v in s.size)
    assert (total, bridges) == (1721, 21)


@needs_maps
def test_structure_sizes_agree_with_the_pictures_except_two():
    from allods2.anim.structures import load_structure_records
    from allods2.databin import databin
    stats = databin(GFS).structures
    off = {sid for sid, r in load_structure_records(GFS).items()
           if tuple(stats[sid - 1].params[:2]) != (r["TileWidth"], r["TileHeight"])}
    assert off == {14, 57}                                   # Cave, Castle: data.bin footprint != picture


@needs_maps
def test_every_object_id_resolves_or_is_excluded():
    from allods2.anim.objects import load_object_records, object_paths
    recs = load_object_records(GFS)
    missing = {oid for oid, r in recs.items() if not GFS.isfile(object_paths(r, GFS)["main"] or "")}
    assert missing == BURNING
    for p in MAPS:
        m = Map.load(p, GFS)
        h, w = m.objects.shape
        for o in m.placed_objects():
            assert o.id in recs and o.id not in BURNING, (p, o)
            assert 8 <= o.x <= w - 9 and 8 <= o.y <= h - 5
        for o in m.placed_objects(window=False):             # outside the window: unknown ids
            if o.id not in recs or o.id in BURNING:           # allowed only there (52.alm: 208)
                assert not (8 <= o.x <= w - 9 and 8 <= o.y <= h - 5)


@needs_maps
def test_structures_stamp_into_passability():
    from allods2.databin import databin
    stats = databin(GFS).structures
    m = Map.load("scenario/10.alm", GFS)
    plain, stamped = m.passability(1), m.passability(1, stats)
    assert (plain != stamped).any()
    s = next(s for s in m.structures if s.type == 55)
    w, h, mask, present = O.footprint(s, stats)
    solid = O.mask_cells(w, h, mask) & O.mask_cells(w, h, present)
    assert not stamped[s.y:s.y + h, s.x:s.x + w][solid].any()


@needs_data
@needs_maps
def test_scene_draws_objects_and_structures():
    from allods2.anim.scene import Scene, draw_scene
    from allods2.graphics.canvas import Canvas
    m = Map.load("scenario/10.alm", GFS)
    scene = Scene(GFS)
    empty = Canvas(m.width * 32, m.height * 32, (1, 2, 3))
    draw_scene(empty, m, scene, relief=False, objects=False, structures=False)
    assert (empty.pix == (1, 2, 3)).all()
    full = Canvas(m.width * 32, m.height * 32, (1, 2, 3))
    draw_scene(full, m, scene, relief=False)
    drawn = (full.pix != (1, 2, 3)).any(axis=2)
    assert 0.02 < drawn.mean() < 0.6
    s = m.structures[0]                                       # a structure covers its footprint
    assert drawn[s.y * 32:(s.y + 1) * 32, s.x * 32:(s.x + 1) * 32].any()
