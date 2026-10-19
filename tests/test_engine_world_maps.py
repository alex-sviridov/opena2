"""Engine world state on the install's maps (skipped without it); spec
2026-10-16-world-state-design.md "Tests"."""

import json
import os
import subprocess
import sys

import numpy as np
import pytest

from allods2.assets import AssetCache
from allods2.common import campaign_maps
from allods2.formats import Map
from engine.world import OBJECT_ID_BASE, STRUCTURE_ID_BASE, World

from helpers import GFS

MAPS = campaign_maps(GFS) if GFS else []
pytestmark = pytest.mark.skipif(not MAPS, reason="game files not present")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Independent reference, written from docs/formats/map.md part 3 "Passability: derived"
# and part 4 "Footprint and blocking"; it shares no code with allods2.formats.passability.
# Mix shape of tile (strip, row): 1 only b, 2 (a+3b)/4, 3 (a+b)/2, 4 (3a+b)/4, 5 only a.
SHAPES = (
    (2, 3, 2, 4, 3, 4, 2, 2, 2, 2, 4, 4, 4, 4),
    (3, 5, 3, 3, 1, 3, 2, 4, 2, 2, 4, 2, 4, 4),
    (2, 3, 2, 4, 3, 4, 2, 4, 2, 2, 4, 2, 4, 4),
    (5, 5, 5, 5, 5, 5, 2, 2, 2, 2, 4, 4, 4, 4),
)


def ref_is_mountain(cell):
    """Tile set 7 is (Mountain a, Stones b); type = a when the shape is 3, 4 or 5."""
    row, strip, tset = cell & 0xF, cell >> 4 & 3, cell >> 6 & 0xF
    if cell & 0x300 == 0x200 or tset != 7 or row >= 14:
        return False
    return SHAPES[strip][row] >= 3


def ref_block(m, stats):
    h, w = m.terrain.shape
    blk = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            t = int(m.terrain[y, x])
            if t & 0x2000 or ref_is_mountain(t) or t & 0x300 == 0x200:
                blk[y][x] = 1
            if m.objects[y, x]:
                blk[y][x] = 5
            if x < 8 or y < 8 or x >= w - 8 or y >= h - 8:
                blk[y][x] = 0x1F
    claimed = set()
    for s in m.structures:                                   # record order, first wins
        if s.size is not None:
            sw, sh, solid, present = s.size[0], s.size[1], 0, 0xFFFFFFFF
        else:
            p = stats[s.type - 1].params
            sw, sh, solid, present = p[0], p[1], p[4] & 0xFFFFFFFF, p[5] & 0xFFFFFFFF
        stop = False
        for r in range(sh):
            for c in range(sw):
                bit = (r * sw + c) % 32
                x, y = s.x + c, s.y + r
                if present >> bit & 1 and 0 <= x < w and 0 <= y < h:
                    if (x, y) in claimed:                    # FUN_00559890 fails, registration ends
                        stop = True
                        break
                    claimed.add((x, y))
                    blk[y][x] = blk[y][x] | 5 if solid >> bit & 1 else blk[y][x] & 0xFA
            if stop:
                break
    return np.array(blk, np.uint8)


ASSETS = AssetCache(GFS) if GFS else None


@pytest.fixture(scope="module", params=MAPS)
def built(request):
    m = Map.load(request.param, GFS)
    return m, World.from_map(m, ASSETS)


def test_counts_ids_and_index(built):
    m, w = built
    assert len(w.objects) == len(m.placed_objects()) + len(m.structures)
    assert len(w.objects) == sum(w.report.counts.values())
    for i, o in w.objects.items():
        assert o.id == i
        if o.kind == "object":
            assert OBJECT_ID_BASE <= i < OBJECT_ID_BASE + len(m.objects.nonzero()[0])
        else:
            assert i == STRUCTURE_ID_BASE + o.uid and 0x6001 <= i < 0x8000
        for dx, dy, _ in o.footprint:
            x, y = o.x + dx, o.y + dy
            if 0 <= x < w.width and 0 <= y < w.height:
                assert i in w.objects_at(x, y)
    for (x, y), ids in w._cells.items():
        assert ids and ids <= w.objects.keys()
    assert w.report.unknown == [] and all(o.known for o in w.objects.values())


def test_block_equals_reference_and_format_layer(built):
    m, w = built
    stats = ASSETS.databin().structures
    assert np.array_equal(w.block, ref_block(m, stats))
    assert np.array_equal(w.block, m.block_with_structures(stats))
    assert np.array_equal(w.block, w.rebuild_block())


def test_block_identical_with_all_objects(built):
    """Spec decision 3: cells outside the loaded window lie in the border."""
    m, w = built
    from allods2.formats import passability as pas
    from allods2.formats.objects import stamp_structures
    full = stamp_structures(pas.block_layer(m.terrain, m.objects), m.structures,
                            ASSETS.databin().structures)
    assert np.array_equal(w.block, full)
    assert len(m.placed_objects(window=False)) == len(m.placed_objects()) + w.report.ignored_outside_window


def test_remove_then_readd_everything_on_one_map():
    m = Map.load(MAPS[0], GFS)
    w = World.from_map(m, ASSETS)
    before = w.block.copy()
    objs = sorted(w.objects.values(), key=lambda o: o.seq)
    for o in objs:
        w.remove_object(o.id)
    assert not w.objects and not w._cells
    assert np.array_equal(w.block, w.rebuild_block())
    for o in objs:
        w.add_object(o)
    assert np.array_equal(w.block, before)


def test_cli_world_info_without_pygame():
    r = subprocess.run([sys.executable, "-c",
                        "import sys, engine.__main__ as m; m.main(['world-info', '10', '--install', %r]);"
                        "assert 'pygame' not in sys.modules" % os.environ.get(
                            "ALLODS2_INSTALL", os.path.join(ROOT, "samples", "allods2_en_gog"))],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    assert "unknown types: 0" in r.stdout and "10.alm: 80 x 80" in r.stdout


def test_golden_world_dumps():
    gold = json.load(open(os.path.join(ROOT, "tests", "golden.json")))
    for name, want in gold.items():
        if name in ("screenshots", "minimaps", "interface", "units", "items", "spells", "progression", "paths", "orders", "orders_slots", "casts"):   # drawing goldens: test_engine_objects.py, test_engine_minimap.py, test_engine_interface.py
            continue
        w = World.from_map(Map.load("scenario/%s.alm" % name, GFS), ASSETS)
        assert w.dump_hash() == want, (
            "world-dump of map %s changed; if intended run tools/update_golden.py" % name)
