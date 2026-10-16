"""`.reg` registry files (signature 0x31415926).

Spec: docs/formats/reg.md.  A tree of named entries: sections hold a
contiguous run of child entries; leaves are strings, ints, floats or int
arrays whose payload lives in a data blob after the directory.
"""

import struct
from dataclasses import dataclass, field

from a2res import basename

from .common import read

SIGNATURE = 0x31415926
HEADER = 0x18
ENTRY = 32

T_STRING, T_SECTION, T_INT, T_FLOAT, T_INTS = 0, 1, 2, 4, 6
SORTED = 0x10              # section children sorted: binary search with strcmp
NAME_MAX = 15              # names compare on at most 15 characters


@dataclass
class Entry:
    name: str
    type: int
    a: int                  # +4: child index / int / blob offset / f64 low
    b: int                  # +8: child count / blob length / f64 high
    raw: bytes              # the 8 value bytes at +4

    @property
    def kind(self):
        return self.type & 0xF

    @property
    def is_section(self):
        return self.kind == T_SECTION


@dataclass
class Registry:
    entries: list
    root_entry: Entry       # header +0x04..+0x0f: {first child, count, type 0x11}
    blob: bytes
    name: str = ""
    _cache: dict = field(default_factory=dict, repr=False)

    def value(self, e):
        if e.is_section:
            return Section(self, e)
        if e.type & 0xE == T_INT:                  # FUN_004e6f9f accepts 2 and 3
            return struct.unpack("<i", e.raw[:4])[0]
        if e.type == T_FLOAT:
            return struct.unpack("<d", e.raw)[0]
        if e.type == T_STRING:
            return self.blob[e.a:e.a + e.b].split(b"\0")[0].decode("cp1251")
        if e.type == T_INTS:
            data = self.blob[e.a:e.a + e.b]
            return list(struct.unpack("<%di" % (len(data) // 4), data))
        raise ValueError("unknown entry type %d (%s)" % (e.type, e.name))

    @property
    def root(self):
        return Section(self, self.root_entry)

    def __getitem__(self, path):
        return self.root[path]

    def get(self, path, default=None):
        return self.root.get(path, default)

    def to_dict(self):
        return self.root.to_dict()

    def records(self, prefix, count_key):
        """to_dict() of each section <prefix><n>, n < Global/<count_key>
        (missing sections skipped)."""
        for n in range(self.get("Global/" + count_key, 0)):
            sec = self.get("%s%d" % (prefix, n))
            if sec is not None:
                yield sec.to_dict()


class Section:
    def __init__(self, reg, entry):
        self.reg = reg
        self.entry = entry

    @property
    def name(self):
        return self.entry.name

    def children(self):
        e = self.entry
        return self.reg.entries[e.a:e.a + e.b]

    def keys(self):
        return [c.name for c in self.children()]

    def _find(self, name):
        """FUN_004e918e: sorted sections compare with strcmp on the key cut
        to 15 characters; others with _strnicmp(key, name, 15).  A name with
        trailing spaces therefore never matches."""
        key = name[:NAME_MAX]
        for c in self.children():
            if self.entry.type & SORTED:
                if c.name == key:
                    return c
            elif c.name[:NAME_MAX].lower() == key.lower():
                return c
        raise KeyError(name)

    def __getitem__(self, path):
        node = self
        for part in path.replace("\\", "/").split("/"):
            if not isinstance(node, Section):
                raise KeyError(path)
            node = self.reg.value(node._find(part))
        return node

    def get(self, path, default=None):
        try:
            return self[path]
        except KeyError:
            return default

    def __contains__(self, path):
        return self.get(path) is not None

    def to_dict(self):
        return {c.name: (Section(self.reg, c).to_dict() if c.is_section
                         else self.reg.value(c)) for c in self.children()}

    def __repr__(self):
        return "Section(%r, %d children)" % (self.name, self.entry.b)


def parse_reg(data, name=""):
    data = bytes(data)                      # small files; bytes methods below
    if len(data) < HEADER:
        raise ValueError("file too short")
    sig, first, roots, rtype, count, _ = struct.unpack_from("<6I", data, 0)
    if sig != SIGNATURE:
        raise ValueError("bad signature 0x%08x" % sig)
    end = HEADER + ENTRY * count
    if end + 4 > len(data):
        raise ValueError("directory past end of file")
    entries = []
    for i in range(count):
        o = HEADER + ENTRY * i
        _, a, b, typ = struct.unpack_from("<4I", data, o)
        nm = data[o + 16:o + 32].split(b"\0")[0].decode("cp1251")
        entries.append(Entry(nm, typ, a, b, data[o + 4:o + 12]))
    size, = struct.unpack_from("<I", data, end)
    blob = data[end + 4:end + 4 + size]
    if end + 4 + size != len(data):
        raise ValueError("blob size %d does not reach end of file" % size)
    return Registry(entries, Entry("", rtype, first, roots, data[4:12]), blob, name)


def load_reg(path, fs=None):
    """path in `fs` (a2res FS; None = OS path)."""
    return parse_reg(read(path, fs), basename(path))
