"""Campaign map: header (section 0) and terrain layer.  Spec: docs/formats/map.md.

The container walk is allods2/alm.py.  `Map.load` decodes the General block
the way the game's reader FUN_00534ad4 does (sequential reads with version
gates) and exposes the Tiles block as a numpy array.  Section 4 is decoded by
formats/objects.py (`Map.structures`); every other section
stays raw in `Map.sections` until a later spec decodes it.
"""

import struct
from dataclasses import dataclass

import numpy as np
from a2res import basename

from ..alm import (SEC_GENERAL, SEC_HEIGHTS, SEC_OBJECTS, SEC_TILES, AlmMap, parse_alm)
from ..common import read
from . import entities as ent
from . import objects as obj
from . import passability as pas

TEXT_ENCODING = "cp1251"
NAME_SIZE = 0x40           # name buffer
TEXT_SIZE = 0x200          # description buffer (runs 16 bytes past the section's size)
MIN_VERSION = 1300         # earlier files lack fields; the game still reads them (see _fields)
MAX_VERSION = 1600         # the game refuses newer maps ("Map version too new")
DIRT_FLAG = 0x2000         # editor-only: cleared by the game when it builds the runtime map
FOG_BITS = 0xC000          # run-time fog of war


def decode_text(buf):
    """A fixed text buffer: bytes up to the first NUL, decoded as cp1251.
    Whatever follows the NUL is uninitialised editor memory."""
    return bytes(buf).split(b"\0", 1)[0].decode(TEXT_ENCODING, errors="replace")


@dataclass
class MapHeader:
    """Section 0 (General block) plus the file header's version.  Offsets are
    in the section data; the order is the game's read order."""
    version: int           # file header u32 #4: 1300 or 1600; gates the optional fields
    tag: int               # section header tag, equal in all 13 sections: 5 or 7
    id_extra: int          # section 0's 5th header u32 (unused by the reader)
    width: int             # +0x00
    height: int            # +0x04
    angle: float           # +0x08 f32 initial sun angle; overwritten by FUN_004a5dd2
    field_0c: int          # +0x0c 360 or 720 (runtime map +0x2c; consumer not traced)
    ambient: int           # +0x10 initial ambient light; overwritten by FUN_004a5dd2
    diffuse: int           # +0x14 initial diffuse light; overwritten by FUN_004a5dd2
    tile_sets: int         # +0x18 bit mask of the tile sets (0..12) used by the Tiles block
    player_count: int      # +0x1c records in section 5 (76 bytes each)
    n_sec4: int            # +0x20 entries of section 4
    n_sec6: int            # +0x24 records of section 6 (48 bytes each)
    n_sec7: int            # +0x28 records of section 7
    n_sec8: int            # +0x2c records of section 8
    n_sec10: int           # +0x30 records of section 10
    n_sec11: tuple         # +0x34, +0x38, +0x3c three counts of section 11 (12 bytes each)
    n_sec12: int           # +0x40 entries of section 12
    name: str              # +0x44 64-byte buffer
    name_raw: bytes
    field_84: int          # +0x84 1 in all but a few maps (1..4); default 1
    field_88: int          # +0x88 1..4; default 1
    field_8c: int          # +0x8c mostly 0; garbage in a few maps
    field_90: int          # +0x90 0 or 60000000; garbage in a few maps
    description: str       # +0x94 512-byte buffer
    description_raw: bytes

    @property
    def cells(self):
        return self.width * self.height

    @property
    def tile_set_list(self):
        return [t for t in range(13) if self.tile_sets >> t & 1]


class _Reader:
    """Sequential reads from section 0 and the 16 bytes the game reads after it."""

    def __init__(self, data):
        self.data, self.pos = bytes(data), 0

    def take(self, n):
        if self.pos + n > len(self.data):
            raise ValueError("General block ends inside a field (+0x%x)" % self.pos)
        b = self.data[self.pos:self.pos + n]
        self.pos += n
        return b

    def i32(self):
        return struct.unpack("<i", self.take(4))[0]

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]


def parse_header(sec0, version, tag=0, id_extra=0):
    """MapHeader from a Section 0 (data + tail).  Field gates as FUN_00534ad4:
    version > 1149 n_sec10, > 1229 n_sec11, > 1299 n_sec12, > 1159 field_8c/90;
    fields absent in an old file keep the reader's default (0, or 1 for
    field_84/field_88 when section 0 is missing)."""
    r = _Reader(bytes(sec0.data) + bytes(sec0.tail))
    w, h = r.u32(), r.u32()
    angle = struct.unpack("<f", r.take(4))[0]
    f0c, amb, dif, sets = r.i32(), r.i32(), r.i32(), r.u32()
    players, n4, n6, n7, n8 = (r.u32() for _ in range(5))
    n10 = r.u32() if version > 1149 else 0
    n11 = tuple(r.u32() for _ in range(3)) if version > 1229 else (0, 0, 0)
    n12 = r.u32() if version > 1299 else 0
    name_raw = r.take(NAME_SIZE)
    f84, f88 = r.i32(), r.i32()
    f8c, f90 = (r.i32(), r.i32()) if version > 1159 else (0, 0)
    desc_raw = r.take(TEXT_SIZE)
    return MapHeader(version, tag, id_extra, w, h, angle, f0c, amb, dif, sets, players, n4, n6,
                     n7, n8, n10, n11, n12, decode_text(name_raw), name_raw, f84, f88, f8c, f90,
                     decode_text(desc_raw), desc_raw)


class Map:
    """A campaign map.  `terrain` holds the raw Tiles block values (cell
    layout in terrain.md; the dirt bit is the editor's, see `runtime_terrain`)."""

    def __init__(self, alm, header, name=""):
        self.alm, self.header, self.name = alm, header, name
        self._block = None
        self._structures = None
        self._entities = {}
        self.sections = {sid: bytes(s.data) for sid, s in alm.sections.items()
                         if sid not in (SEC_GENERAL, SEC_TILES, SEC_HEIGHTS, SEC_OBJECTS)}
        self.terrain = alm.tiles.copy()                   # (h, w) uint16
        self.heights = alm.heights.copy()                 # (h, w) uint8, read signed by the game
        self.objects = np.frombuffer(alm.sections[SEC_OBJECTS].data, np.uint8) \
            .reshape(alm.height, alm.width).copy()        # object index + 1

    @classmethod
    def parse(cls, data, name=""):
        alm = parse_alm(data, name)
        h = parse_header(alm.sections[SEC_GENERAL], struct.unpack_from("<I", data, 16)[0],
                         alm.sections[SEC_GENERAL].tag, alm.sections[SEC_GENERAL].extra)
        if (h.width, h.height) != (alm.width, alm.height):
            raise ValueError("size mismatch")
        for sid, bpc in ((SEC_TILES, 2), (SEC_HEIGHTS, 1), (SEC_OBJECTS, 1)):
            if len(alm.sections[sid].data) != h.cells * bpc:
                raise ValueError("section %d is not width*height*%d bytes" % (sid, bpc))
        return cls(alm, h, name)

    @classmethod
    def load(cls, path, fs=None):
        """`path` in `fs` (None = OS path)."""
        return cls.parse(read(path, fs), basename(path))

    @property
    def width(self):
        return self.header.width

    @property
    def height(self):
        return self.header.height

    @property
    def heights_i8(self):
        """`heights` as the game reads them: signed bytes (no campaign map has a negative one)."""
        return self.heights.view(np.int8)

    @property
    def block(self):
        """The server's static block layer, (h, w) uint8, derived from the raw tiles, the
        objects and the border; see passability.py and map.md part 3."""
        if self._block is None:
            self._block = pas.block_layer(self.terrain, self.objects)
        return self._block

    @property
    def structures(self):
        """Section 4 as `objects.Structure` records (buildings and bridges)."""
        if self._structures is None:
            self._structures = obj.parse_structures(self.sections[4], self.header.n_sec4)
        return self._structures

    def _entity(self, key, fn):
        if key not in self._entities:
            self._entities[key] = fn()
        return self._entities[key]

    @property
    def players(self):
        """Section 5 as `entities.Player` records (record number = `index`, 1-based)."""
        return self._entity("players", lambda: ent.parse_players(
            self.sections[5], self.header.player_count))

    @property
    def units(self):
        """Section 6 as `entities.Unit` records (monsters and humans)."""
        return self._entity("units", lambda: ent.parse_units(
            self.sections[6], self.header.n_sec6))

    @property
    def item_groups(self):
        """Section 8 as `entities.Group` records: unit inventories and sacks on the ground."""
        return self._entity("groups", lambda: ent.parse_groups(
            self.sections[8], self.header.n_sec8))

    @property
    def item_records(self):
        """Section 9 as `entities.ItemRecord` records (item properties, spellbook and building links)."""
        return self._entity("records", lambda: ent.parse_item_records(self.sections[9]))

    @property
    def ground_groups(self):
        """The item groups no unit record links to: sacks lying on the ground."""
        used = {u.group for u in self.units if u.group}
        return [g for i, g in enumerate(self.item_groups, 1) if i not in used]

    @property
    def items(self):
        """Alias of `ground_groups` plus the carried ones: every item group."""
        return self.item_groups

    def placed_objects(self, window=True):
        """The Objects block as `objects.MapObject` records (trees, rocks,
        decorations), row-major; only the cells the game loads unless `window=False`."""
        return obj.placed_objects(self.objects, window)

    def block_with_structures(self, stats):
        """`block` plus the structures' footprints (FUN_00550a96); `stats` = DataBin.structures."""
        return obj.stamp_structures(self.block, self.structures, stats)

    def passability(self, movement_type=1, stats=None):
        """(h, w) bool: cells a mover of `movement_type` (data.bin movementType 1 walker,
        2 Ghost/Bee, 3 flyer) may enter on the static layer; with `stats` (DataBin.structures)
        the structures' footprints are stamped too, units never."""
        block = self.block if stats is None else self.block_with_structures(stats)
        return pas.walkable(block, movement_type)

    def cost(self, costs=pas.DEFAULT_COSTS):
        """(h, w) uint8 movement cost of each cell; `costs` as `pas.costs_from_reg`."""
        return pas.cost_layer(self.terrain, costs)

    def runtime_terrain(self):
        """The cells as the game holds them after loading (FUN_004a449c clears
        bit 13, the dirt flag, in every cell; fog bits are 0 in the files)."""
        return self.terrain & np.uint16(~DIRT_FLAG & 0xFFFF)
