"""docs/formats/map.md part 3: heights and the derived static passability."""

import numpy as np
import pytest

from allods2 import reg
from allods2.common import campaign_maps
from allods2.formats import Map
from allods2.formats import passability as P

from helpers import GFS

MAPS = campaign_maps(GFS) if GFS else []
needs_maps = pytest.mark.skipif(not MAPS, reason="game files not present")


def cell(tset, strip=0, row=0, dirt=False):
    return tset << 6 | strip << 4 | row | (0x2000 if dirt else 0)


# --- synthetic: one test per rule ---------------------------------------------

def test_terrain_class_follows_the_set_and_shape_tables():
    costs = (255, 8, 8, 8, 14, 6, 12, 8, 16, 8, 6)
    # set 0 = (Grass, Land); strip 0 row 0 has shape 2 -> (a + 3b) / 4, type b
    assert P.terrain_class(cell(0, 0, 0), costs) == (P.T_LAND, (8 + 3 * 8) >> 2)
    # set 2 = (Sand, Land); strip 0 row 3 has shape 4 -> (3a + b) / 4, type a
    assert P.terrain_class(cell(2, 0, 3), costs) == (P.T_SAND, (3 * 14 + 8) >> 2)
    # set 5 = (Cracked, Stones); strip 3 row 0 has shape 5 -> only a
    assert P.terrain_class(cell(5, 3, 0), costs) == (P.T_CRACKED, 6)
    # set 7 = (Mountain, Stones); strip 3 row 0 -> pure mountain, cost 16
    assert P.terrain_class(cell(7, 3, 0), costs) == (P.T_MOUNTAIN, 16)
    # set 12 = (Road, Land); strip 1 row 4 has shape 1 -> only b = Land
    assert P.terrain_class(cell(12, 1, 4), costs) == (P.T_LAND, 8)


def test_water_and_missing_rows():
    for s in (8, 9, 10, 11):
        assert P.terrain_class(cell(s, 0, 2)) == (P.T_WATER, 8)
        assert P.terrain_class(cell(s, 1, 4)) == (P.T_LAND, 8)       # shore tile
        assert P.terrain_class(cell(s, 0, 4)) == (P.T_WATER, 8)
        assert P.terrain_class(cell(s, 0, 9)) == (0xFF, 8)           # rows 8..15
    assert P.terrain_class(cell(0, 0, 14))[0] == 0xFF                # past the strip


def n_cells(n, tile=cell(0, 0, 0)):
    return np.full((n, n), tile, np.uint16), np.zeros((n, n), np.uint8)


def test_block_layer_rules_and_order():
    t, o = n_cells(24)
    t[10, 10] = cell(8, 0, 0)                  # water
    t[10, 11] = cell(7, 3, 0)                  # mountain
    t[10, 12] = cell(0, 0, 0, dirt=True)       # dirt (building ground)
    t[10, 13] = cell(0, 0, 0, dirt=True)       # dirt and object: the object replaces it
    o[10, 13] = 7
    o[10, 14] = 1                              # object on grass
    t[2, 2] = cell(8, 0, 0)
    o[3, 3] = 1                                # inside the border: overwritten
    b = P.block_layer(t, o)
    assert [int(x) for x in b[10, 9:15]] == [0, 1, 1, 1, 5, 5]
    assert (b[:8] == 0x1F).all() and (b[-8:] == 0x1F).all()
    assert (b[:, :8] == 0x1F).all() and (b[:, -8:] == 0x1F).all()
    assert b[3, 3] == 0x1F and b[8:-8, 8:-8].max() == 5


def test_mover_masks():
    t, o = n_cells(24)
    t[10, 10] = cell(8, 0, 0)
    o[10, 11] = 1
    b = P.block_layer(t, o)
    walker, low, fly = (P.walkable(b, k) for k in (1, 2, 3))
    assert not walker[10, 10] and not walker[10, 11] and walker[10, 12]
    assert low[10, 10] and not low[10, 11]                           # Ghost/Bee: over water, not objects
    assert fly[10, 10] and fly[10, 11] and not fly[0, 0]             # only the border stops flyers
    assert not low[0, 0] and not walker[0, 0]


def test_non_square_maps_are_refused():
    with pytest.raises(NotImplementedError):
        P.block_layer(np.zeros((16, 24), np.uint16), np.zeros((16, 24), np.uint8))


def test_cost_layer_and_missing_tiles():
    t, _ = n_cells(4, cell(2, 0, 3))
    t[1, 1] = cell(0, 0, 14)
    c = P.cost_layer(t, (255, 8, 8, 8, 14, 6, 12, 8, 16, 8, 6))
    assert c[0, 0] == (3 * 14 + 8) >> 2 and c[1, 1] == 0xFF


def test_costs_from_reg_defaults_and_keys():
    class R(dict):
        def get(self, k, d=None):
            return dict.get(self, k, d)
    assert P.costs_from_reg(R()) == P.DEFAULT_COSTS
    assert P.costs_from_reg(R({"Terrain/CostSand": 3}))[P.T_SAND] == 3


# --- the install's 46 campaign maps -------------------------------------------

@needs_maps
def test_layers_match_the_header_and_value_range():
    for path in MAPS:
        m = Map.load(path, GFS)
        shape = (m.header.height, m.header.width)
        assert m.heights.shape == shape and m.block.shape == shape and m.cost().shape == shape, path
        assert m.heights_i8.min() >= 0 and m.heights_i8.max() <= 127, path   # signed, never negative
        assert set(np.unique(m.block)) <= {0, 1, 5, 0x1F}, path
        assert (m.block[:8] == 0x1F).all() and (m.block[:, -8:] == 0x1F).all(), path
        assert m.passability(3)[8:-8, 8:-8].all(), path                       # flyers: no static obstacle inside


@needs_maps
def test_block_counts_agree_with_the_terrain_data():
    """Water cells (sets 8..11) are blocked for walkers everywhere in the playable area."""
    for path in MAPS:
        m = Map.load(path, GFS)
        water = (((m.terrain & 0x1FFF) >> 6) >= 8) & (((m.terrain & 0x1FFF) >> 6) <= 11)
        inner = (slice(8, -8), slice(8, -8))
        assert (m.block[inner][water[inner]] != 0).all(), path
        assert not m.passability(1)[inner][water[inner]].any(), path


@needs_maps
def test_shipped_costs_and_the_five_missing_tiles():
    costs = P.costs_from_reg(reg.load_reg("world/data/map.reg", GFS))
    assert costs == (255, 8, 8, 8, 14, 6, 12, 8, 16, 8, 6)
    bad = {}
    for path in MAPS:
        m = Map.load(path, GFS)
        n = int((m.cost(costs) == 0xFF).sum())
        if n:
            bad[m.name] = n
    assert bad == {"74.alm": 5}                      # the 5 cells that name a tile past their strip
