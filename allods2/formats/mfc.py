"""MFC `CArchive` reader / writer for the server stream of a saved game (docs/formats/saves.md 6.4, 6.10).

Pure byte layer, little endian.  Primitives, CStrings, counted lists and *object pointers* with MFC's class-tag /
back-reference scheme (`WriteObject`, FUN_005ac36a): classes and objects share one counter; a new class takes the next
index when its record is written, the object takes the next one *before* its body is serialised.  The first index is 1
(index 0 = null; INFERRED, standard MFC: `first_index` overrides it).

Writer:  `w.object(obj, CLASS, lambda w: ...body...)`; the same `obj` object again writes a back-reference.
Reader:  `r.object({"Unit": MfcClass("Unit", create=..., load=...)})`; `create()` makes the empty object, which is
registered before `load(obj, reader)` reads the body, so a child's back-reference to its parent resolves.
"""

import struct
from dataclasses import dataclass
from typing import Callable, Optional

from ..text import decode_text

NEW_CLASS = 0xFFFF              # u16 tag: a class record follows
BIG = 0x7FFF                    # u16 tag: the index is a u32 that follows
CLASS_BIT = 0x8000              # u16 tag bit: known class (index in the low 15 bits)
BIG_CLASS_BIT = 0x80000000      # u32 after BIG: known class


class ArchiveError(ValueError):
    """Truncated stream, bad tag, index outside the map, wrong class."""


@dataclass(frozen=True)
class MfcClass:
    """A `CRuntimeClass`: `schema` is 1 for every class of the game (6.10).  `create` / `load` are used by the reader."""
    name: str
    schema: int = 1
    create: Optional[Callable] = None       # () -> new empty object
    load: Optional[Callable] = None         # (obj, MfcReader) -> None


class MfcWriter:
    def __init__(self, first_index=1):
        self.buf = bytearray()
        self.counter = first_index          # archive+0x30
        self._objects = {}                  # id(obj) -> (index, obj)  (obj kept alive so ids stay unique)
        self._classes = {}                  # name -> index

    def getvalue(self):
        return bytes(self.buf)

    def u8(self, v):
        self.buf += struct.pack("<B", v)

    def u16(self, v):
        self.buf += struct.pack("<H", v)

    def u32(self, v):
        self.buf += struct.pack("<I", v & 0xFFFFFFFF)

    def raw(self, data):
        self.buf += data

    def count(self, n):
        """Counted lists (6.4): a u32."""
        self.u32(n)

    def cstring(self, s):
        b = s.encode("cp1251") if isinstance(s, str) else bytes(s)
        if len(b) < 0xFF:
            self.u8(len(b))
        elif len(b) < 0xFFFF:
            self.u8(0xFF)
            self.u16(len(b))
        else:
            raise ArchiveError("CString longer than 0xfffe")
        self.buf += b

    def _tag(self, index, class_bit):
        if index < BIG:
            self.u16(index | (CLASS_BIT if class_bit else 0))
        else:
            self.u16(BIG)
            self.u32(index | (BIG_CLASS_BIT if class_bit else 0))

    def object(self, obj, cls=None, body=None):
        """FUN_005ac36a.  `None` = null pointer; a pointer already written = back-reference (`cls` / `body` unused);
        else the class tag (a class record the first time), the object takes the next index, then `body(writer)`."""
        if obj is None:
            self.u16(0)
            return
        known = self._objects.get(id(obj))
        if known is not None:
            self._tag(known[0], False)
            return
        ci = self._classes.get(cls.name)
        if ci is None:
            self.u16(NEW_CLASS)
            name = cls.name.encode("cp1251")
            self.u16(cls.schema)
            self.u16(len(name))
            self.buf += name
            self._classes[cls.name] = self.counter
            self.counter += 1
        else:
            self._tag(ci, True)
        self._objects[id(obj)] = (self.counter, obj)    # index taken before the body
        self.counter += 1
        body(self)


class MfcReader:
    def __init__(self, data, pos=0, first_index=1):
        self.data = bytes(data)
        self.pos = pos
        self._first = first_index
        self._map = [None] * first_index    # position = index; entries: MfcClass or object

    def _take(self, fmt):
        try:
            v, = struct.unpack_from(fmt, self.data, self.pos)
        except struct.error:
            raise ArchiveError("unexpected end of archive at 0x%x" % self.pos) from None
        self.pos += struct.calcsize(fmt)
        return v

    def u8(self):
        return self._take("<B")

    def u16(self):
        return self._take("<H")

    def u32(self):
        return self._take("<I")

    def raw(self, n):
        if self.pos + n > len(self.data):
            raise ArchiveError("unexpected end of archive at 0x%x" % self.pos)
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def count(self):
        return self.u32()

    def cstring(self):
        n = self.u8()
        if n == 0xFF:
            n = self.u16()
        return decode_text(self.raw(n))

    def rest(self):
        return self.data[self.pos:]

    def _entry(self, index):
        if index <= 0 or index >= len(self._map):
            raise ArchiveError("object index %d outside the map (%d entries)" % (index, len(self._map)))
        return self._map[index]

    def object(self, classes, expect=None):
        """FUN_005ac3e9.  `classes`: name -> MfcClass with `create` / `load`.  `expect`: a class name the pointer must
        have (else error 6 of the exe).  Returns None for a null pointer."""
        tag = self.u16()
        if tag == 0:
            return None
        if tag == NEW_CLASS:
            schema = self.u16()
            name = self.raw(self.u16()).decode("cp1251")
            cls = classes.get(name)
            if cls is None:
                raise ArchiveError("unknown class %r" % name)
            if cls.schema != schema:
                raise ArchiveError("class %r: schema %d, expected %d" % (name, schema, cls.schema))
            self._map.append(cls)
        else:
            is_class = False
            if tag == BIG:
                big = self.u32()
                is_class = bool(big & BIG_CLASS_BIT)
                index = big & ~BIG_CLASS_BIT & 0xFFFFFFFF
            elif tag & CLASS_BIT:
                is_class, index = True, tag & ~CLASS_BIT
            else:
                index = tag
            target = self._entry(index)
            if not is_class:
                if isinstance(target, MfcClass):
                    raise ArchiveError("back-reference %d names a class" % index)
                return target
            if not isinstance(target, MfcClass):
                raise ArchiveError("class tag %d names an object" % index)
            cls = target
        if expect is not None and cls.name != expect:
            raise ArchiveError("class %r where %r is required" % (cls.name, expect))
        obj = cls.create()
        self._map.append(obj)           # registered before the body
        cls.load(obj, self)
        return obj
