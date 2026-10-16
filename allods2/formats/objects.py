"""Map objects: the Objects block (section 3) and the Structures list (section 4).
Spec: docs/formats/map.md part 4.

Section 3 is a per-cell layer of `objects.reg` IDs (trees, rocks, decorations;
byte = ID + 1).  Section 4 lists the buildings and bridges ("structures"):
20 bytes per entry plus 8 for a bridge with a size, read by the map reader
FUN_00534ad4 (case 4) and instantiated by the runtime builder FUN_004a449c
(0x4a479b onward).  The footprint stamp is FUN_00550a96.
"""

import struct
from dataclasses import dataclass

import numpy as np

BRIDGE_ID = 0x21           # VariableSize bridge (9 pieces); 0x25 (14 pieces) never occurs in a file
BRIDGE_FLAG = 0x1000000    # type bit: "bridge with a size", the reader forces the ID to 0x21
ENTRY_SIZE = 20
BRIDGE_EXTRA = 8
WINDOW = 8                 # the loader copies rows 8..h-5, columns 8..w-9 of section 3

SOLID = 0x05               # block bits 0 and 2 (FUN_00550a96)
CLEAR = 0xFA               # mask that clears them


@dataclass(frozen=True)
class Structure:
    """One section 4 entry.  x, y are the footprint's top-left cell (the file
    stores 1/256 cells, always a cell centre: multiples of 128)."""
    x: int
    y: int
    type: int              # structures.reg / data.bin structure ID (1..179)
    intact: int            # u16: 0 = starts destroyed, else full HP (0, 10 or 100 in the files)
    owner: int             # u32, 1..8: a player value, see map.md (resolution open)
    uid: int               # s16, the structure's object ID is 0x6000 + uid
    size: tuple = None     # (w, h) in cells, bridges only

    @property
    def is_bridge(self):
        return self.size is not None


@dataclass(frozen=True)
class MapObject:
    """One non-empty cell of the Objects block."""
    x: int
    y: int
    id: int                # objects.reg ID (cell byte - 1)


def parse_structures(data, count):
    """Structures of a section 4; raises ValueError unless the entries tile the
    section exactly."""
    out, pos = [], 0
    for _ in range(count):
        if pos + ENTRY_SIZE > len(data):
            raise ValueError("structures end inside an entry")
        x, y, t, a, b, c = struct.unpack_from("<iiIHIh", data, pos)
        pos += ENTRY_SIZE
        size = None
        if t == BRIDGE_ID or t & BRIDGE_FLAG:
            if pos + BRIDGE_EXTRA > len(data):
                raise ValueError("structures end inside a bridge size")
            w, h = struct.unpack_from("<II", data, pos)
            pos += BRIDGE_EXTRA
            t, size = BRIDGE_ID, (w & 0xFFFF, h & 0xFFFF)     # the builder passes the low words
        out.append(Structure(x >> 8, y >> 8, t & 0xFFFF, a, b, c, size))
    if pos != len(data):
        raise ValueError("%d bytes after the last structure" % (len(data) - pos))
    return out


def placed_objects(layer, window=True):
    """MapObject list of an Objects layer (h, w), row-major.  With `window` only
    the cells the game loads (rows 8..h-5, columns 8..w-9) are listed."""
    h, w = layer.shape
    ys, xs = np.nonzero(layer)
    out = []
    for y, x in zip(ys.tolist(), xs.tolist()):
        if window and not (WINDOW <= y <= h - 5 and WINDOW <= x <= w - 9):
            continue
        out.append(MapObject(x, y, int(layer[y, x]) - 1))
    return out


def footprint(s, stats):
    """(w, h, solid mask, present mask) of a structure: data.bin `sizeX`, `sizeY`,
    `Passability`, `BuildingPresent` (`stats` = DataBin.structures).  A bridge takes its
    size from the map and has solid mask 0, present mask all ones (constructor 0x51ff33)."""
    if s.size is not None:
        return s.size[0], s.size[1], 0, 0xFFFFFFFF
    p = stats[s.type - 1].params
    return p[0], p[1], p[4] & 0xFFFFFFFF, p[5] & 0xFFFFFFFF


def mask_cells(w, h, mask):
    """(h, w) bool of a footprint mask: bit `row * w + col`, taken mod 32 (the game
    tests `1 << (i & 0x1f)`), so a footprint of more than 32 cells repeats its mask."""
    i = np.arange(w * h).reshape(h, w) & 31
    return ((mask >> i) & 1).astype(bool)


def stamp_structures(block, structures, stats):
    """Block layer after the structures (FUN_005599df registers a structure in the cells
    of its `BuildingPresent` mask, FUN_00550a96 then refreshes each): a registered cell
    gets bits 0 and 2 if its `Passability` bit is set and loses them otherwise (a bridge
    makes water walkable); cells outside the present mask are untouched.  Returns a copy."""
    out = block.copy()
    H, W = out.shape
    for s in structures:
        w, h, solid, present = footprint(s, stats)
        solid, present = mask_cells(w, h, solid), mask_cells(w, h, present)
        for r in range(h):
            for c in range(w):
                y, x = s.y + r, s.x + c
                if present[r, c] and 0 <= y < H and 0 <= x < W:
                    out[y, x] = out[y, x] | SOLID if solid[r, c] else out[y, x] & CLEAR
    return out


def ground_height(heights, x, y, sx, sy):
    """Height under a structure/unit at position (x, y) (1/256 cell) with a
    footprint of sx x sy cells (FUN_0046025d, map.md part 3).  A structure's
    position is its top-left cell * 256 + 0x80."""
    H = np.asarray(heights).astype(np.int8).astype(np.int64)
    X, Y = x - 0x80 + sx * 0x80, y - 0x80 + sy * 0x80
    c, r, fx, fy = X >> 8, Y >> 8, (X >> 3) & 31, (Y >> 3) & 31
    Hh, Ww = H.shape
    g = lambda rr, cc: int(H[min(rr, Hh - 1), min(cc, Ww - 1)])
    tdiv = lambda a, b: int(a / b)                     # C division, toward 0
    a = g(r, c) + tdiv((g(r, c + 1) - g(r, c)) * fx, 32)
    b = g(r + 1, c) + tdiv((g(r + 1, c + 1) - g(r + 1, c)) * fx, 32)
    return a + tdiv((b - a) * fy, 32)


def cell_relief(heights, x, y):
    """Relief of a cell (view `+0xc0`): mean of its four corner heights,
    truncated toward 0 (terrain.md, vertex table)."""
    H = np.asarray(heights).astype(np.int8).astype(np.int64)
    Hh, Ww = H.shape
    s = sum(int(H[min(y + dy, Hh - 1), min(x + dx, Ww - 1)]) for dy in (0, 1) for dx in (0, 1))
    return int(s / 4)
