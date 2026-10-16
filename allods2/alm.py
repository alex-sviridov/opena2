"""`.alm` map container (M7R).  Spec: docs/formats/map.md §1 (container),
docs/formats/terrain.md (Tiles block).  The decoded view is formats/map.py.
"""

import struct
from dataclasses import dataclass, field

import numpy as np
from a2res import basename

from .common import read

MAGIC = b"M7R\0"
SECTION0_PAD = 16          # section 0 is followed by 16 bytes past its size

SEC_GENERAL, SEC_TILES, SEC_HEIGHTS, SEC_OBJECTS = 0, 1, 2, 3


@dataclass
class Section:
    tag: int
    id: int
    extra: int
    data: bytes
    tail: bytes = b""      # bytes after the data that the game's reader still consumes


@dataclass
class AlmMap:
    width: int
    height: int
    sections: dict = field(default_factory=dict)     # id -> Section
    name: str = ""

    @property
    def tiles(self):
        """(h, w) uint16 Tiles block."""
        return np.frombuffer(self.sections[SEC_TILES].data, "<u2").reshape(self.height, self.width)

    @property
    def heights(self):
        """(h, w) uint8 Altitudes block (runtime mapping open)."""
        return np.frombuffer(self.sections[SEC_HEIGHTS].data, np.uint8).reshape(self.height, self.width)


def parse_alm(data, name=""):
    if bytes(data[:4]) != MAGIC:
        raise ValueError("not an M7R map")
    hsize, _, count, _ = struct.unpack_from("<4I", data, 4)
    pos = hsize
    sections = {}
    for k in range(count):
        if pos + 20 > len(data):
            raise ValueError("section %d header past end of file" % k)
        tag, shs, size, sid, extra = struct.unpack_from("<5I", data, pos)
        pos += shs
        if pos + size > len(data):
            raise ValueError("section %d data past end of file" % k)
        pad = SECTION0_PAD if k == 0 else 0
        sections[sid] = Section(tag, sid, extra, data[pos:pos + size],
                                data[pos + size:pos + size + pad])
        pos += size + pad
    if pos != len(data):
        raise ValueError("%d bytes after the last section" % (len(data) - pos))
    w, h = struct.unpack_from("<II", sections[SEC_GENERAL].data, 0)
    return AlmMap(w, h, sections, name)


def load_alm(path, fs=None):
    """path in `fs` (None = OS path); section data are views of the file."""
    return parse_alm(read(path, fs), basename(path))
