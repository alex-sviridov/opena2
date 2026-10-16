"""Static passability of a campaign map.  Spec: docs/formats/map.md part 3.

The .alm has no passability layer.  The server's path finder derives it from
the Tiles block (raw, dirt flag included), the Objects block and the map
border when it loads the map (FUN_00554626, tables set up in FUN_00553d51),
into a cost layer and a bit-mask "block" layer.  A mover can enter a cell
when `block & MOVE_MASK[movement type] == 0`.  Units and structures stamp
more bits at run time; those are not reproduced here.
"""

from functools import lru_cache

import numpy as np

# Terrain type ids = index of the cost table (0x54146 + id); 0 = none.
(T_NONE, T_LAND, T_GRASS, T_FLOWERS, T_SAND, T_CRACKED, T_STONES, T_SAVANNA,
 T_MOUNTAIN, T_WATER, T_ROAD) = range(11)
TERRAIN_NAMES = ("None", "Land", "Grass", "Flowers", "Sand", "Cracked", "Stones",
                 "Savanna", "Mountain", "Water", "Road")
# map.reg [Terrain] Cost<name> defaults used when a key is missing (T_LAND..T_ROAD)
DEFAULT_COSTS = (0xFF, 8, 8, 9, 0xE, 6, 0xC, 0xB, 0x10, 8, 6)

# (a, b) terrain types of tile set 0..15 (table 0x54126; 8..11 = water, 13..15 never occur)
SET_TYPES = ((T_GRASS, T_LAND), (T_CRACKED, T_LAND), (T_SAND, T_LAND), (T_SAVANNA, T_LAND),
             (T_STONES, T_LAND), (T_CRACKED, T_STONES), (T_FLOWERS, T_SAVANNA),
             (T_MOUNTAIN, T_STONES), (0, 0), (0, 0), (0, 0), (0, 0), (T_ROAD, T_LAND),
             (0, 0), (0, 0), (0, 0))

# Mix shape of tile (strip, row) (table 0x540a6): 1 = only b, 2 = (a + 3b) / 4,
# 3 = (a + b) / 2, 4 = (3a + b) / 4, 5 = only a.  Rows 14, 15 do not exist.
SHAPES = (
    (2, 3, 2, 4, 3, 4, 2, 2, 2, 2, 4, 4, 4, 4),
    (3, 5, 3, 3, 1, 3, 2, 4, 2, 2, 4, 2, 4, 4),
    (2, 3, 2, 4, 3, 4, 2, 4, 2, 2, 4, 2, 4, 4),
    (5, 5, 5, 5, 5, 5, 2, 2, 2, 2, 4, 4, 4, 4),
)

# Bits of the block layer (FUN_00554626, FUN_00550a96, FUN_00557a89).
B_GROUND = 0x01         # water, mountain, dirt (building ground): walkers cannot enter
B_FLYER = 0x02          # only set on the map border by the static build
B_OBJECT = 0x04         # object cell (tree, rock, ...): walkers and ghosts/bees cannot enter
B_BORDER = 0x1F         # the 8-cell border of the map
# Mover masks by units.bin `movementType` (FUN_00557a89): 1 walker, 2 low flyer
# (Ghost, Bee: over water/mountain, not through objects), 3 flyer (Bat, Dragon,
# Succubus: only the border and other flyers block).
MOVE_MASK = {1: 0x41, 2: 0x44, 3: 0x82}

BORDER = 8              # cells of border on each side
COST_NONE = 0xFF


def terrain_class(cell, costs=DEFAULT_COSTS):
    """(terrain type id, cost) of one raw Tiles cell (FUN_0055494d).

    Water (sets 8..11) always costs 8; its type is Water-or-Land only on the
    shore tile (row 4 of strip 1) and 0xFF otherwise.  Tiles with a row
    above 13 have type 0xFF.  `costs` is the 11-entry cost table (index =
    terrain type)."""
    row, strip, tset = cell & 0xF, (cell >> 4) & 3, (cell >> 6) & 0xF
    if cell & 0x300 == 0x200:
        if row >= 8:
            return 0xFF, 8
        return (T_LAND if row == 4 and strip == 1 else T_WATER), 8
    if row >= 14:
        return 0xFF, 8
    a, b = SET_TYPES[tset]
    shape = SHAPES[strip][row]
    ca, cb = costs[a], costs[b]
    cost = {1: cb, 2: (ca + 3 * cb) >> 2, 3: (ca + cb) >> 1, 4: (3 * ca + cb) >> 2, 5: ca}[shape]
    return (b if shape <= 2 else a), cost


@lru_cache(maxsize=None)
def _tables(costs):
    """Lookup arrays over the 13-bit cell value (without the dirt/fog bits)."""
    n = 0x2000
    ttype = np.empty(n, np.uint8)
    tcost = np.empty(n, np.uint8)
    for v in range(n):
        ttype[v], tcost[v] = terrain_class(v, costs)
    return ttype, tcost


def block_layer(terrain, objects):
    """The static block layer, (h, w) uint8, from the raw Tiles (dirt bit
    kept: the server reads the file's tiles, not the runtime copy) and the
    Objects layer (byte != 0 = object).  Order as FUN_00554626: dirt -> 1;
    terrain type Mountain -> 1; water -> 1; object -> 5 (replaces); then the
    8-cell border -> 0x1F (FUN_00553b30).  Square maps only (all campaign
    maps)."""
    h, w = terrain.shape
    if h != w:
        raise NotImplementedError("non-square maps use a 256-wide grid (FUN_00553b30)")
    ttype, _ = _tables(DEFAULT_COSTS)
    t = terrain.astype(np.uint32)
    blk = np.zeros((h, w), np.uint8)
    blk[(t & 0x2000) != 0] = B_GROUND
    blk[ttype[t & 0x1FFF] == T_MOUNTAIN] = B_GROUND
    blk[(t & 0x300) == 0x200] = B_GROUND
    blk[objects != 0] = B_GROUND | B_OBJECT
    blk[:BORDER, :] = blk[-BORDER:, :] = B_BORDER
    blk[:, :BORDER] = blk[:, -BORDER:] = B_BORDER
    return blk


def cost_layer(terrain, costs=DEFAULT_COSTS):
    """Per-cell movement cost, (h, w) uint8 (0xFF = type 0xFF cell)."""
    ttype, tcost = _tables(costs)
    t = terrain.astype(np.uint32) & 0x1FFF
    return np.where(ttype[t] > T_ROAD, COST_NONE, tcost[t]).astype(np.uint8)


def walkable(block, movement_type=1):
    """Boolean (h, w): cells a mover of `movement_type` (1..3) may enter,
    judged on the static layer."""
    return (block & MOVE_MASK[movement_type]) == 0


def costs_from_reg(reg):
    """The 11-entry cost table (index = terrain type) from `world/data/map.reg`
    ([Terrain] Cost<name>, FUN_00553d51); missing keys keep the defaults."""
    out = list(DEFAULT_COSTS)
    for t in range(T_LAND, T_ROAD + 1):
        out[t] = int(reg.get("Terrain/Cost" + TERRAIN_NAMES[t], out[t]))
    return tuple(out)
