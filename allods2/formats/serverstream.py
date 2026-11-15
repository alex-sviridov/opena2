"""The server stream of a saved game as typed objects (docs/formats/saves.md 6.2, 6.4-6.11; step L10c).

`ServerStream.parse(stream)` / `.pack()` are the two directions of `FUN_004ec732` over the MFC layer (`mfc.py`): the head (tick, block, map
name, 11 option words, scenario id, difficulty), the player manager (`u32` word, players), the unit container, the loaded flag, the two
`0xbadface1` words and the 400-byte debug block.  Every field the engine does not model is a typed-but-opaque value (raw bytes or a plain
integer) so `parse -> pack` is byte-exact; the objects share Python identity exactly where the stream shares MFC back-references (a hero is
one `Unit` object in its group and in the unit container; a weapon is one `Item` object at `+0x74` and in equipment slot 1).

Loaded flag 1 (a mission save, L10e-A): `ServerStream.mission` = `Mission`, the typed branch in store order: buildings (`FUN_0052c3da`), spell effects
(`FUN_0052d5cb`), the map dynamic layer (`FUN_00550008`: `MapLayer`), the script state (`FUN_0057468d`: `ScriptState`), sacks (`FUN_0052d5b2`) and
virtual casters (`FUN_0053bbd0`).  Field layouts of the raw blocks inside (`serverblocks.py`) name what the engine needs.  A mission branch that
does not parse as that layout (a hand-made blob) is kept as `mission_raw`, the bytes between the flag and the `0xbadface1` pair.

Layout facts and their tags: docs/formats/saves.md 6.4-6.11; the routine of each class is cited at its dataclass.
"""

import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .mfc import ArchiveError, MfcClass, MfcReader, MfcWriter
from .serverblocks import BRAIN, MOVER, POSITION, position_raw

XOR_WORD = 0x5C073F4D           # FUN_00546740: gold (+0x3c) and +0xa48 are stored xor this
BADFACE = 0xBADFACE1
DEBUG_SIZE = 400                # [server+0x170] (6.11)
TABLE_SIZE = 0xA00              # player +0x44: the viewer's knowledge table (saves.md 3.5)

# vtable pointers of the classes (town saves only: the 0xc raw bytes of an object are its Position, 6.12; these are what the town-save writer puts there, INFERRED harmless)
VT_UNIT, VT_HUMANOID, VT_ITEM, VT_EFFECT = 0x5D0EB0, 0x5D0FB8, 0x5D1388, 0x5D1178
VT_SACK, VT_BUILDING, VT_SPELLEFFECT, VT_CASTER = 0x5D1530, 0x5D1268, 0x5D1060, 0x5D0E78

SLOTS = 12                      # Humanoid: equipment slots 1..12 (`+0x20c .. +0x238`)


def _s16(v):
    return v - 0x10000 if v & 0x8000 else v


def _u16(v):
    return v & 0xFFFF


# --- small helpers over the MFC primitives ------------------------------------------------------------------------------------------

def read_ucount(r):
    """`FUN_005aab7b`: the MFC count of a `CList<u16>`: u16, or 0xffff + u32."""
    n = r.u16()
    n = r.u32() if n == 0xFFFF else n
    if n > len(r.data) - r.pos:
        raise ArchiveError("count %d past the end of the archive" % n)
    return n


def write_ucount(w, n):
    if n < 0xFFFF:
        w.u16(n)
    else:
        w.u16(0xFFFF)
        w.u32(n)


def read_cells(r):
    """`CList<u16>` (`FUN_00542230`): MFC count, then u16 elements."""
    return [r.u16() for _ in range(read_ucount(r))]


def write_cells(w, cells):
    write_ucount(w, len(cells))
    for c in cells:
        w.u16(c)


def read_list(r, classes, expect=None):
    """A counted list of MFC object pointers (`u32 count`, then the pointers, 6.4)."""
    n = r.count()
    if n > len(r.data) - r.pos:             # every element takes at least a 2-byte tag: a larger count is garbage, not a list
        raise ArchiveError("list of %d objects past the end of the archive" % n)
    return [r.object(classes, expect) for _ in range(n)]


def write_list(w, items, put):
    w.count(len(items))
    for it in items:
        put(w, it)


# --- the object base (FUN_0052cf8d) --------------------------------------------------------------------------------------------------

@dataclass
class Base:
    """The part every game object writes first: 0xc raw bytes (the object's Position: cell, sub-cell, saves.md 6.12; `raw12` still builds the old vtable form town saves use), `+4` id, `+0xc` / `+0xe` words,
    `+8`, `+0x18` (the loader forces 0), `+0x1c`, the object's own raw pointer (the key of the load map, any unique non-zero value) and `+0x14`
    (a pointer key: the owner)."""
    raw12: bytes = bytes(12)
    id: int = 0
    w0c: int = 0
    w0e: int = 0
    d08: int = 0
    w18: int = 0
    d1c: int = 0
    ptr: int = 0
    link: int = 0

    @property
    def pos(self):
        """The first 12 bytes are the object's Position (`FUN_0052cf8d`, CONFIRMED): `serverblocks.POSITION` fields as a dict."""
        return POSITION.decode(self.raw12)

    def with_pos(self, **fields):
        self.raw12 = POSITION.set(self.raw12, **fields)
        return self

    @classmethod
    def read(cls, r):
        raw = r.raw(12)
        idv, w0c, w0e, d08, w18, d1c, ptr, link = (r.u32(), _s16(r.u16()), _s16(r.u16()), r.u32(), _s16(r.u16()), r.u32(), r.u32(), r.u32())
        return cls(raw, idv, w0c, w0e, d08, w18, d1c, ptr, link)

    def write(self, w):
        if len(self.raw12) != 12:
            raise ValueError("object base: 12 raw bytes")
        w.raw(self.raw12)
        w.u32(self.id)
        w.u16(_u16(self.w0c))
        w.u16(_u16(self.w0e))
        w.u32(self.d08)
        w.u16(_u16(self.w18))
        w.u32(self.d1c)
        w.u32(self.ptr)
        w.u32(self.link)


def raw12(vtable, obj_id=0, d08=0):
    return struct.pack("<III", vtable, obj_id, d08)


# --- Effect, Item, Spell (6.9) ------------------------------------------------------------------------------------------------------

@dataclass
class Effect:
    """`FUN_0051c5ed`: base, u8 `+0x3c` (kind = the data.bin stat id), u8 `+0x3d` (flags), u32 `+0x40` (value bytes: `a | b << 8` for the min / max
    kinds 44-48, `a | charges << 16` for castSpell 41, as `.a2c` items carry them), i16 `+0xc` (tag)."""
    base: Base = field(default_factory=Base)
    kind: int = 0
    flags: int = 0
    value: int = 0
    tag: int = 0

    @staticmethod
    def read(r):
        e = Effect(Base.read(r))
        e.kind, e.flags, e.value, e.tag = r.u8(), r.u8(), r.u32(), _s16(r.u16())
        return e

    def write(self, w):
        self.base.write(w)
        w.u8(self.kind)
        w.u8(self.flags)
        w.u32(self.value)
        w.u16(_u16(self.tag))


@dataclass
class Item:
    """`FUN_0052d65a` (class `Item`): base (`+0xc` = the index of the class record, `+0x1c` = the price), the effect list, i16 `+0x40` (the item code, the
    same 16 bits as the `.a2c` item), i16 `+0x42` (the stack count), u8 `+0x44` (group: 1 armour, 2 weapon, 3 potion, 4 scroll, 5 book, 0 quest), u8
    `+0x45`, `+0x46`, u16 `+0x48` (capacity left for modifiers), `+0x4a` (weight), u8 `+0x47`."""
    base: Base = field(default_factory=Base)
    effects: List[Effect] = field(default_factory=list)
    code: int = 0
    count: int = 1
    group: int = 0
    b45: int = 0
    b46: int = 0
    w48: int = 0
    w4a: int = 0
    b47: int = 0

    @staticmethod
    def read(r):
        it = Item(Base.read(r))
        it.effects = read_list(r, CLASSES, "Effect")
        it.code, it.count = _u16(_s16(r.u16())), _s16(r.u16())
        it.group, it.b45, it.b46 = r.u8(), r.u8(), r.u8()
        it.w48, it.w4a, it.b47 = r.u16(), r.u16(), r.u8()
        return it

    def write(self, w):
        self.base.write(w)
        write_list(w, self.effects, lambda w_, e: w_.object(e, C_EFFECT, e.write))
        w.u16(_u16(self.code))
        w.u16(_u16(self.count))
        w.u8(self.group)
        w.u8(self.b45)
        w.u8(self.b46)
        w.u16(self.w48)
        w.u16(self.w4a)
        w.u8(self.b47)


@dataclass
class Spell:
    """`FUN_0051bf44` (class `Spell`, size 0x14): u8 `+8` (the spell number), u8 `+9`, u8 `+0xa`, u16 `+0xc`, u32 `this`."""
    number: int = 0
    b9: int = 0
    ba: int = 0
    wc: int = 0
    ptr: int = 0

    @staticmethod
    def read(r):
        return Spell(r.u8(), r.u8(), r.u8(), r.u16(), r.u32())

    def write(self, w):
        w.u8(self.number)
        w.u8(self.b9)
        w.u8(self.ba)
        w.u16(self.wc)
        w.u32(self.ptr)


@dataclass
class Spellbook:
    """`FUN_0051c505` (the unit's `+0x140`, a CArray indexed by the spell number): u32 `+0x18`, u32 `GetSize`, then the elements `1 .. GetSize - 1` as
    Spell pointers (null for a spell the hero does not know; element 0 is not saved).  `size` is `GetSize`."""
    d18: int = 0
    size: int = 0
    spells: List[Optional[Spell]] = field(default_factory=list)       # elements 1 .. size - 1

    @staticmethod
    def read(r):
        sb = Spellbook(r.u32(), r.u32())
        sb.spells = [r.object(CLASSES, "Spell") for _ in range(max(0, sb.size - 1))]
        return sb

    def write(self, w):
        w.u32(self.d18)
        w.u32(self.size)
        if len(self.spells) != max(0, self.size - 1):
            raise ValueError("spell book: %d elements for GetSize %d" % (len(self.spells), self.size))
        for s in self.spells:
            w.object(s, C_SPELL, s.write if s is not None else None)

    @property
    def mask(self):
        """Bit n set = spell n present (the `.a2c` spell mask)."""
        return sum(1 << (i + 1) for i, s in enumerate(self.spells) if s is not None)

    @classmethod
    def from_mask(cls, mask, d18=0):
        top = mask.bit_length()
        return cls(d18, top + 1 if top else 0,
                   [Spell(i + 1) if mask >> (i + 1) & 1 else None for i in range(top)])


@dataclass
class Pack:
    """`FUN_0052da4d` (unit `+0x7c`, also a Sack's body): the counted list of Item pointers, u32 `+0x1c` (the insertion index, 0x7fff = the end), u32 `+0x20`."""
    items: List[Item] = field(default_factory=list)
    d1c: int = 0x7FFF
    d20: int = 0

    @staticmethod
    def read(r):
        p = Pack()
        p.items = read_list(r, CLASSES, "Item")
        p.d1c, p.d20 = r.u32(), r.u32()
        return p

    def write(self, w):
        write_list(w, self.items, lambda w_, it: w_.object(it, C_ITEM, it.write))
        w.u32(self.d1c)
        w.u32(self.d20)


# --- Unit / Humanoid (6.8, 6.10) --------------------------------------------------------------------------------------------------------

@dataclass
class Humanoid:
    """The part a human adds after `Unit::Serialize` (`FUN_0052d7c8`): 0x18 raw bytes at `+0x23c` (u32 best school, then the five school XP pools) and the
    equipment slots 1..12 (`+0x20c .. +0x238`) as Item pointers (null = empty; slots 1 and 2 are the same objects as the unit's `+0x74` / `+0x78`)."""
    block: bytes = bytes(0x18)
    slots: List[Optional[Item]] = field(default_factory=lambda: [None] * SLOTS)


@dataclass
class Unit:
    """`FUN_0052c618` (class `Unit`, or `Humanoid` when `hum` is set), store order of 6.8 / 6.10.  Unmodelled blocks are raw: `blk_a6` / `blk_be` /
    `blk_114` / `blk_d4` (attack block, armour block, school-skill copy, bonus accumulators), `mover` (0xb4, `+0x1c0`), `brain` (0xb8, `+0x1c4`) with its
    `CList<u16>`.  `words` = `+0x84 .. +0x9e`: body, reaction, mind, spirit, speed, `+0x8e`, `+0x90`, `+0x92`, HP, max HP, HP regeneration, mana, max
    mana, mana regeneration (6.8 / unit-struct 2)."""
    base: Base = field(default_factory=Base)
    effects: List[Effect] = field(default_factory=list)
    list1c8: List[int] = field(default_factory=list)
    list1e4: List[int] = field(default_factory=list)
    blk_a6: bytes = bytes(0x18)
    blk_be: bytes = bytes(0x16)
    blk_114: bytes = bytes(0x18)
    blk_d4: bytes = bytes(0x40)
    mover: bytes = bytes(0xB4)
    brain: bytes = bytes(0xB8)
    brain_list: List[int] = field(default_factory=list)
    b49: int = 0
    b4a: int = 0
    b4b: int = 0
    b4c: int = 0
    r50: bytes = bytes(4)
    r54: bytes = bytes(4)
    r58: bytes = bytes(4)
    b60: int = 0
    b61: int = 0
    b6c: int = 0
    weapon: Optional[Item] = None          # +0x74
    second: Optional[Item] = None          # +0x78
    name: str = ""                         # +0x80
    words: Tuple[int, ...] = (0,) * 14
    b_a2: int = 0
    b_a3: int = 0
    w_a0: int = 0
    w_a4: int = 0                          # signed
    b12c: int = 0
    d130: int = 0
    b134: int = 0
    b135: int = 0
    b136: int = 0
    d138: int = 0
    b13c: int = 0
    packed: int = 0                        # word(+0x14c) | (+0x204 != 0) << 16 | (+0x1a0 != 0) << 24
    d144: int = 0
    held: Optional[Item] = None            # +0x68
    pack: Optional[Pack] = None            # +0x7c (flag byte, then the body)
    spells: Optional[Spellbook] = None     # +0x140 (flag byte, then the body)
    d5c: int = 0
    d64: int = 0
    d44: int = 0
    d40: int = 0
    b48: int = 0
    hum: Optional[Humanoid] = None

    @property
    def class_name(self):
        return "Humanoid" if self.hum is not None else "Unit"

    def mover_get(self, name):
        return MOVER.get(self.mover, name)

    def mover_set(self, **values):
        self.mover = MOVER.set(self.mover, **values)

    def brain_get(self, name):
        return BRAIN.get(self.brain, name)

    def brain_set(self, **values):
        self.brain = BRAIN.set(self.brain, **values)

    @property
    def number(self):
        """`+0x14c`: the hero / type number (low word of the packed field)."""
        return self.packed & 0xFFFF

    def read_body(self, r):
        self.base = Base.read(r)
        self.effects = read_list(r, CLASSES, "Effect")
        self.list1c8 = read_cells(r)
        self.list1e4 = read_cells(r)
        self.blk_a6, self.blk_be, self.blk_114, self.blk_d4 = r.raw(0x18), r.raw(0x16), r.raw(0x18), r.raw(0x40)
        self.mover = r.raw(0xB4)
        self.brain = r.raw(0xB8)
        self.brain_list = read_cells(r)
        self.b49, self.b4a, self.b4b, self.b4c = r.u8(), r.u8(), r.u8(), r.u8()
        self.r50, self.r54, self.r58 = r.raw(4), r.raw(4), r.raw(4)
        self.b60, self.b61, self.b6c = r.u8(), r.u8(), r.u8()
        self.weapon = r.object(CLASSES, "Item")
        self.second = r.object(CLASSES, "Item")
        self.name = r.cstring()
        w14 = [r.u16() for _ in range(14)]
        self.words = tuple(w14)
        self.b_a2, self.b_a3 = r.u8(), r.u8()
        self.w_a0, self.w_a4 = r.u16(), _s16(r.u16())
        self.b12c, self.d130 = r.u8(), r.u32()
        self.b134, self.b135, self.b136 = r.u8(), r.u8(), r.u8()
        self.d138, self.b13c = r.u32(), r.u8()
        self.packed, self.d144 = r.u32(), r.u32()
        self.held = r.object(CLASSES, "Item")
        self.pack = Pack.read(r) if r.u8() else None
        self.spells = Spellbook.read(r) if r.u8() else None
        self.d5c, self.d64, self.d44, self.d40 = r.u32(), r.u32(), r.u32(), r.u32()
        self.b48 = r.u8()

    def write_body(self, w):
        self.base.write(w)
        write_list(w, self.effects, lambda w_, e: w_.object(e, C_EFFECT, e.write))
        write_cells(w, self.list1c8)
        write_cells(w, self.list1e4)
        for blk, n in ((self.blk_a6, 0x18), (self.blk_be, 0x16), (self.blk_114, 0x18), (self.blk_d4, 0x40), (self.mover, 0xB4), (self.brain, 0xB8)):
            if len(blk) != n:
                raise ValueError("unit raw block: %d bytes, expected %d" % (len(blk), n))
            w.raw(blk)
        write_cells(w, self.brain_list)
        w.u8(self.b49)
        w.u8(self.b4a)
        w.u8(self.b4b)
        w.u8(self.b4c)
        for b in (self.r50, self.r54, self.r58):
            w.raw(b)
        w.u8(self.b60)
        w.u8(self.b61)
        w.u8(self.b6c)
        _put_item(w, self.weapon)
        _put_item(w, self.second)
        w.cstring(self.name)
        if len(self.words) != 14:
            raise ValueError("unit words: 14 u16 (+0x84 .. +0x9e)")
        for v in self.words:
            w.u16(_u16(v))
        w.u8(self.b_a2)
        w.u8(self.b_a3)
        w.u16(self.w_a0)
        w.u16(_u16(self.w_a4))
        w.u8(self.b12c)
        w.u32(self.d130)
        w.u8(self.b134)
        w.u8(self.b135)
        w.u8(self.b136)
        w.u32(self.d138)
        w.u8(self.b13c)
        w.u32(self.packed)
        w.u32(self.d144)
        _put_item(w, self.held)
        if self.pack is None:
            w.u8(0)
        else:
            w.u8(1)
            self.pack.write(w)
        if self.spells is None:
            w.u8(0)
        else:
            w.u8(1)
            self.spells.write(w)
        w.u32(self.d5c)
        w.u32(self.d64)
        w.u32(self.d44)
        w.u32(self.d40)
        w.u8(self.b48)
        if self.hum is not None:
            if len(self.hum.block) != 0x18 or len(self.hum.slots) != SLOTS:
                raise ValueError("humanoid: 0x18 raw bytes and 12 slots")
            w.raw(self.hum.block)
            for s in self.hum.slots:
                _put_item(w, s)


def _put_item(w, it):
    w.object(it, C_ITEM, it.write if it is not None else None)


def _put_unit(w, u):
    w.object(u, C_HUMANOID if u.hum is not None else C_UNIT, u.write_body)


def _read_humanoid_tail(u, r):
    u.hum.block = r.raw(0x18)
    u.hum.slots = [r.object(CLASSES, "Item") for _ in range(SLOTS)]


# --- other object classes (6.9; typed, not yet wired to the flag-1 branch) -------------------------------------------------------------------

@dataclass
class SackObj:
    """`FUN_0052d8de` (class `Sack`): base, u32 `+0x3c`, then a `Pack` body."""
    base: Base = field(default_factory=Base)
    d3c: int = 0
    pack: Pack = field(default_factory=Pack)

    def read_body(self, r):
        self.base, self.d3c, self.pack = Base.read(r), r.u32(), Pack.read(r)

    def write_body(self, w):
        self.base.write(w)
        w.u32(self.d3c)
        self.pack.write(w)


# the derived carrier classes and what each adds after the SpellEffect part (FUN_0051c7e5 PointEffect, FUN_0051c88e AreaEffect, FUN_0051c718 SpellTransport; saves.md 6.12):
# "o" = an MFC object pointer (usually a back-reference to a unit already written), "p" = a raw u32 pointer key, "b" = u8, "h" = u16
EFFECT_TAILS = {
    "SpellEffect": (),
    "PointEffect": (("o4c", "o"), ("p48", "p")),
    "AreaEffect": (("b4c", "b"), ("b4d", "b"), ("b4e", "b"), ("b4f", "b"), ("h50", "h"), ("o48", "o")),
    "SpellTransport": (("o48", "o"), ("o4c", "o"), ("h50", "h")),
}


@dataclass
class SpellEffectObj:
    """`FUN_0051c6b5` (class `SpellEffect`): base, u8 `+0x40` (done flag), u8 `+0x41` (1).  `kind` is the runtime class actually written: the base class itself, or one of its three derived
    carriers (`EFFECT_TAILS`), whose own serialisers append the fields in `tail` (name -> value; `o*` entries are the MFC-referenced objects)."""
    base: Base = field(default_factory=Base)
    b40: int = 0
    b41: int = 0
    kind: str = "SpellEffect"
    tail: dict = field(default_factory=dict)

    def read_body(self, r):
        self.base, self.b40, self.b41 = Base.read(r), r.u8(), r.u8()
        self.tail = {}
        for name, code in EFFECT_TAILS[self.kind]:
            self.tail[name] = r.object(CLASSES) if code == "o" else r.u32() if code == "p" else r.u8() if code == "b" else r.u16()

    def write_body(self, w):
        self.base.write(w)
        w.u8(self.b40)
        w.u8(self.b41)
        for name, code in EFFECT_TAILS[self.kind]:
            v = self.tail.get(name, None if code == "o" else 0)
            if code == "o":
                w.object(v, C_UNIT, _no_new_object)
            elif code == "p":
                w.u32(v)
            elif code == "b":
                w.u8(v)
            else:
                w.u16(v)


def _no_new_object(w):
    raise ValueError("an effect's object reference must point to an object already written")


@dataclass
class VirtualCasterObj:
    """`FUN_0052db3e` (class `VirtualCaster`): base, u8 `+0x3c`, 6 raw bytes (the sub-object at `+0x40`)."""
    base: Base = field(default_factory=Base)
    b3c: int = 0
    sub: bytes = bytes(6)

    def read_body(self, r):
        self.base, self.b3c, self.sub = Base.read(r), r.u8(), r.raw(6)

    def write_body(self, w):
        self.base.write(w)
        w.u8(self.b3c)
        w.raw(self.sub)


@dataclass
class BuildingObj:
    """`FUN_0052029c` (class `Building`): base, 0x16 raw bytes, u8 `+0x40`, u16 `+0x42`, `+0x44`, `+0x46`, u8 `+0x48`, `+0x60`, `+0x61`, u32 `+0x64`, `+0x68`."""
    base: Base = field(default_factory=Base)
    blk: bytes = bytes(0x16)
    b40: int = 0
    w42: int = 0
    w44: int = 0
    w46: int = 0
    b48: int = 0
    b60: int = 0
    b61: int = 0
    d64: int = 0
    d68: int = 0

    def read_body(self, r):
        self.base, self.blk = Base.read(r), r.raw(0x16)
        self.b40, self.w42, self.w44, self.w46 = r.u8(), r.u16(), r.u16(), r.u16()
        self.b48, self.b60, self.b61, self.d64, self.d68 = r.u8(), r.u8(), r.u8(), r.u32(), r.u32()

    def write_body(self, w):
        self.base.write(w)
        w.raw(self.blk)
        w.u8(self.b40)
        w.u16(self.w42)
        w.u16(self.w44)
        w.u16(self.w46)
        w.u8(self.b48)
        w.u8(self.b60)
        w.u8(self.b61)
        w.u32(self.d64)
        w.u32(self.d68)


# --- Group and Player (6.6, 6.7) ---------------------------------------------------------------------------------------------------------

@dataclass
class Group:
    """`FUN_0052d932` (written inline in the player's group list, no class tag): the embedded `CList<u16>` at `+0x20` (INFERRED same kind), the
    `*(group+0x3c)` block (0x50 raw bytes + a `CList<u16>`), the unit list (counted Unit pointers), u32 `+0x1c`, `+0x40` (pointer key), `+0x44` (pointer key)."""
    list20: List[int] = field(default_factory=list)
    ai: bytes = bytes(0x50)
    ai_list: List[int] = field(default_factory=list)
    units: List[Unit] = field(default_factory=list)
    d1c: int = 0
    d40: int = 0
    d44: int = 0

    @staticmethod
    def read(r):
        g = Group()
        g.list20 = read_cells(r)
        g.ai, g.ai_list = r.raw(0x50), read_cells(r)
        g.units = read_list(r, CLASSES)
        g.d1c, g.d40, g.d44 = r.u32(), r.u32(), r.u32()
        for u in g.units:
            if not isinstance(u, Unit):
                raise ArchiveError("a group holds a non-unit object")
        return g

    def write(self, w):
        write_cells(w, self.list20)
        if len(self.ai) != 0x50:
            raise ValueError("group AI block: 0x50 bytes")
        w.raw(self.ai)
        write_cells(w, self.ai_list)
        write_list(w, self.units, _put_unit)
        w.u32(self.d1c)
        w.u32(self.d40)
        w.u32(self.d44)


@dataclass
class Player:
    """`FUN_0052d1c5` (class `Player`, size 0xa80), 6.6.  `gold` = `+0x3c` and `kills_monsters` = `+0xa48` are stored xor `0x5c073f4d`; `hero_deaths`
    (`+0xa54`) and `kills_players` (`+0xa4c`) are stored clamped to 0x7fff; `main_hero` = `+0x38` (the id of the main hero unit); `table` = `+0x44` (0xa00
    bytes), `stats_block` = the 0x24 bytes of `FUN_00574656` (INFERRED `player+0x34`)."""
    name: str = ""
    w04: int = 0
    d08: int = 0
    b10: bytes = bytes(8)
    b_a44: int = 0
    d2c: int = 0
    w30: int = 0
    gold: int = 0
    b40: int = 0
    b41: int = 0
    kills_monsters: int = 0
    d_a50: int = 0
    hero_deaths: int = 0
    kills_players: int = 0
    d_a5c: int = 0
    main_hero: int = 0
    ptr: int = 0
    table: bytes = bytes(TABLE_SIZE)
    groups: List[Group] = field(default_factory=list)
    stats_block: bytes = bytes(0x24)

    def read_body(self, r):
        self.name = r.cstring()
        self.w04, self.d08, self.b10, self.b_a44 = r.u16(), r.u32(), r.raw(8), r.u8()
        self.d2c, self.w30 = r.u32(), r.u16()
        self.gold = r.u32() ^ XOR_WORD
        self.b40, self.b41 = r.u8(), r.u8()
        self.kills_monsters = r.u32() ^ XOR_WORD
        self.d_a50 = r.u32()
        self.hero_deaths, self.kills_players = r.u16(), r.u16()
        self.d_a5c, self.main_hero, self.ptr = r.u32(), r.u32(), r.u32()
        self.table = r.raw(TABLE_SIZE)
        self.groups = [Group.read(r) for _ in range(r.count())]
        self.stats_block = r.raw(0x24)

    def write_body(self, w):
        w.cstring(self.name)
        w.u16(self.w04)
        w.u32(self.d08)
        if len(self.b10) != 8 or len(self.table) != TABLE_SIZE or len(self.stats_block) != 0x24:
            raise ValueError("player raw blocks: 8, 0xa00 and 0x24 bytes")
        w.raw(self.b10)
        w.u8(self.b_a44)
        w.u32(self.d2c)
        w.u16(self.w30)
        w.u32(self.gold ^ XOR_WORD)
        w.u8(self.b40)
        w.u8(self.b41)
        w.u32(self.kills_monsters ^ XOR_WORD)
        w.u32(self.d_a50)
        w.u16(min(self.hero_deaths, 0x7FFF))
        w.u16(min(self.kills_players, 0x7FFF))
        w.u32(self.d_a5c)
        w.u32(self.main_hero)
        w.u32(self.ptr)
        w.raw(self.table)
        w.count(len(self.groups))
        for g in self.groups:
            g.write(w)
        w.raw(self.stats_block)

    @property
    def human(self):
        return self.d2c == 0

    @property
    def units(self):
        return [u for g in self.groups for u in g.units]


# --- the mission branch (loaded flag 1; L10e-A) ---------------------------------------------------------------------------------------------------

@dataclass
class MapLayer:
    """`FUN_00550008` (the map object): `cells` = the sparse dynamic layer, one u32 per scanned index `0x807 .. 0xeded` whose plane-2 byte is above 0xf
    (`index << 16 | plane2 << 8 | plane1`, `FUN_0055fc20`: MFC count then u32s); `records` = the CMap at `map+0x54084` (`FUN_0055f6b0`: MFC count, then per
    entry u16 key and a 60-byte `CELL_RECORD`), in the order the stream has them; `ptr` = the map's own pointer key."""
    cells: List[int] = field(default_factory=list)
    records: List[Tuple[int, bytes]] = field(default_factory=list)
    ptr: int = 0

    @staticmethod
    def cell(index, plane2, plane1):
        return (index & 0xFFFF) << 16 | (plane2 & 0xFF) << 8 | (plane1 & 0xFF)

    @staticmethod
    def split(v):
        return v >> 16, (v >> 8) & 0xFF, v & 0xFF

    @staticmethod
    def read(r):
        m = MapLayer()
        m.cells = [r.u32() for _ in range(read_ucount(r))]
        m.records = [(r.u16(), r.raw(60)) for _ in range(read_ucount(r))]
        m.ptr = r.u32()
        return m

    def write(self, w):
        write_ucount(w, len(self.cells))
        for v in self.cells:
            w.u32(v)
        write_ucount(w, len(self.records))
        for k, val in self.records:
            if len(val) != 60:
                raise ValueError("cell record: 60 bytes")
            w.u16(k)
            w.raw(val)
        w.u32(self.ptr)


@dataclass
class ScriptState:
    """`FUN_0057468d` (the script runner / server object; offsets from it).  `values` `+0xc784` (1000 x i32: check results, constants, variables),
    `fired` `+0xe6c4` (1000 flags), `b30` `+8` (0x30 bytes), `b400` `+0xa728`, `relations` `+0xa8bc` (0x132c = 8 header bytes + 70 x 70 relation bytes,
    `serverblocks.relation`), u8 `+0xa48`, `+0xa49`, u32 `+0xa4c` (`FUN_00543570`), `complete` `+0xbe0c` (mission complete counter), `d_be10`, `fail`
    `+0xbe14` (fail cause)."""
    values: bytes = bytes(4000)
    fired: bytes = bytes(1000)
    b30: bytes = bytes(0x30)
    b400: bytes = bytes(400)
    relations: bytes = bytes(0x132C)
    b_a48: int = 0
    b_a49: int = 0
    d_a4c: int = 0
    complete: int = 0
    d_be10: int = 0
    fail: int = 0

    SIZES = (("values", 4000), ("fired", 1000), ("b30", 0x30), ("b400", 400), ("relations", 0x132C))

    @staticmethod
    def read(r):
        s = ScriptState()
        s.values, s.fired, s.b30, s.b400, s.relations = r.raw(4000), r.raw(1000), r.raw(0x30), r.raw(400), r.raw(0x132C)
        s.b_a48, s.b_a49, s.d_a4c = r.u8(), r.u8(), r.u32()
        s.complete, s.d_be10, s.fail = r.u32(), r.u32(), r.u32()
        return s

    def write(self, w):
        for name, n in self.SIZES:
            if len(getattr(self, name)) != n:
                raise ValueError("script state %s: %d bytes expected" % (name, n))
            w.raw(getattr(self, name))
        w.u8(self.b_a48)
        w.u8(self.b_a49)
        w.u32(self.d_a4c)
        w.u32(self.complete)
        w.u32(self.d_be10)
        w.u32(self.fail)

    @property
    def variables(self):
        return struct.unpack("<1000i", self.values)

    @variables.setter
    def variables(self, vals):
        self.values = struct.pack("<1000i", *vals)

    @property
    def fired_flags(self):
        return tuple(self.fired)


@dataclass
class Mission:
    """The part of a mission save after the loaded flag, store order of 6.5: `buildings`, `effects` (SpellEffect), `map`, `script`, `sacks`, `casters`."""
    buildings: List["BuildingObj"] = field(default_factory=list)
    effects: List["SpellEffectObj"] = field(default_factory=list)
    map: MapLayer = field(default_factory=MapLayer)
    script: ScriptState = field(default_factory=ScriptState)
    sacks: List["SackObj"] = field(default_factory=list)
    casters: List["VirtualCasterObj"] = field(default_factory=list)

    @staticmethod
    def read(r):
        m = Mission()
        m.buildings = read_list(r, CLASSES, "Building")
        m.effects = read_list(r, CLASSES)
        for e in m.effects:
            if not isinstance(e, SpellEffectObj):
                raise ArchiveError("class of an effect is not derived from SpellEffect")
        m.map = MapLayer.read(r)
        m.script = ScriptState.read(r)
        m.sacks = read_list(r, CLASSES, "Sack")
        m.casters = read_list(r, CLASSES, "VirtualCaster")
        return m

    def write(self, w):
        write_list(w, self.buildings, lambda w_, b: w_.object(b, C_BUILDING, b.write_body))
        write_list(w, self.effects, lambda w_, e: w_.object(e, MfcClass(e.kind), e.write_body))
        self.map.write(w)
        self.script.write(w)
        write_list(w, self.sacks, lambda w_, k: w_.object(k, C_SACK, k.write_body))
        write_list(w, self.casters, lambda w_, c: w_.object(c, C_CASTER, c.write_body))


# --- the class table (6.4, 6.10) --------------------------------------------------------------------------------------------------------

C_PLAYER, C_UNIT, C_HUMANOID, C_ITEM, C_EFFECT, C_SPELL = (MfcClass(n) for n in ("Player", "Unit", "Humanoid", "Item", "Effect", "Spell"))
C_SACK, C_BUILDING, C_SPELLEFFECT, C_CASTER = (MfcClass(n) for n in ("Sack", "Building", "SpellEffect", "VirtualCaster"))


def _simple(name, make, read_body):
    return MfcClass(name, 1, make, lambda o, r: read_body(o, r))


def _fill(dst, src):
    dst.__dict__.update(src.__dict__)


def _load_item(o, r):
    _fill(o, Item.read(r))


def _load_effect(o, r):
    _fill(o, Effect.read(r))


def _load_spell(o, r):
    _fill(o, Spell.read(r))


def _make_unit():
    return Unit()


def _make_humanoid():
    return Unit(hum=Humanoid())


def _load_unit(o, r):
    o.read_body(r)


def _load_humanoid(o, r):
    o.read_body(r)
    _read_humanoid_tail(o, r)


CLASSES = {
    "Player": MfcClass("Player", 1, Player, lambda o, r: o.read_body(r)),
    "Unit": MfcClass("Unit", 1, _make_unit, _load_unit),
    "Humanoid": MfcClass("Humanoid", 1, _make_humanoid, _load_humanoid),
    "Item": MfcClass("Item", 1, Item, _load_item),
    "Effect": MfcClass("Effect", 1, Effect, _load_effect),
    "Spell": MfcClass("Spell", 1, Spell, _load_spell),
    "Sack": MfcClass("Sack", 1, SackObj, lambda o, r: o.read_body(r)),
    "Building": MfcClass("Building", 1, BuildingObj, lambda o, r: o.read_body(r)),
    **{k: MfcClass(k, 1, (lambda k=k: SpellEffectObj(kind=k)), lambda o, r: o.read_body(r)) for k in EFFECT_TAILS},
    "VirtualCaster": MfcClass("VirtualCaster", 1, VirtualCasterObj, lambda o, r: o.read_body(r)),
}


# --- the whole stream ---------------------------------------------------------------------------------------------------------------

@dataclass
class ServerStream:
    """`FUN_004ec732`.  `words` = the 11 option words (`+0x174, +0x17c, +0x180, +0x184, +0x188, +0x18c, +0x190, +0x194, +0x1a0, +0x19c, +0x198`: all 0
    in a game the engine writes, 6.11); `d20` = `server+0x20` (`FUN_0052d16b`); `container` = the unit container at `[server+0x7c]+0xc` (counted Unit
    pointers, back-references to the units of the groups); `loaded` = the u8 flag (0 town save, 1 mission); `mission` = the typed branch of a mission save (`Mission`), `mission_raw` = the same bytes when
    they do not parse as that layout; `tail_words` = the two `0xbadface1`; `debug` = the 400 bytes of `[server+0x170]`; `pad` = the byte that
    makes the stream even."""
    tick: int = 0
    block: int = 0
    map_name: str = ""
    words: Tuple[int, ...] = (0,) * 11
    scenario: int = 0
    difficulty: int = 2
    d20: int = 0
    players: List[Player] = field(default_factory=list)
    container: List[Unit] = field(default_factory=list)
    loaded: int = 0
    mission_raw: bytes = b""
    tail_words: Tuple[int, int] = (BADFACE, BADFACE)
    debug: bytes = bytes(DEBUG_SIZE)
    pad: bytes = field(default=b"", compare=False)
    mission: Optional[Mission] = None

    @property
    def units(self):
        return [u for p in self.players for u in p.units]

    @classmethod
    def parse(cls, stream):
        stream = bytes(stream)
        r = MfcReader(stream)
        s = cls()
        s.tick, s.block = r.u32(), r.u32()
        s.map_name = r.cstring()
        s.words = tuple(r.u32() for _ in range(11))
        s.scenario, s.difficulty = r.u32(), r.u32()
        s.d20 = r.u32()
        s.players = read_list(r, CLASSES, "Player")
        s.container = read_list(r, CLASSES)
        for u in s.container:
            if not isinstance(u, Unit):
                raise ArchiveError("the unit container holds a non-unit object")
        s.loaded = r.u8()
        if s.loaded:
            rest = len(stream) - r.pos
            saved = (r.pos, list(r._map))
            try:
                s.mission = Mission.read(r)
                if rest - (r.pos - saved[0]) not in (8 + DEBUG_SIZE, 9 + DEBUG_SIZE):
                    raise ArchiveError("mission branch does not end at the 0xbadface1 pair")
            except (ArchiveError, ValueError):
                # not the layout: keep the bytes up to the pair of 0xbadface1 words that precedes the 400-byte block (an even pad byte may follow it)
                s.mission = None
                r.pos, r._map = saved[0], saved[1]
                end = None
                for pad in (0, 1):
                    at = len(stream) - DEBUG_SIZE - 8 - pad
                    if at >= r.pos and struct.unpack_from("<II", stream, at) == (BADFACE, BADFACE):
                        end = at
                        break
                if end is None:
                    raise ArchiveError("mission save: no 0xbadface1 pair before the 400-byte block")
                s.mission_raw = r.raw(end - r.pos)
        s.tail_words = (r.u32(), r.u32())
        s.debug = r.raw(DEBUG_SIZE)
        s.pad = r.rest()
        if len(s.pad) > 1:
            raise ArchiveError("%d bytes after the stream" % len(s.pad))
        return s

    def pack(self):
        w = MfcWriter()
        w.u32(self.tick)
        w.u32(self.block)
        w.cstring(self.map_name)
        if len(self.words) != 11:
            raise ValueError("11 option words")
        for v in self.words:
            w.u32(v)
        w.u32(self.scenario)
        w.u32(self.difficulty)
        w.u32(self.d20)
        write_list(w, self.players, lambda w_, p: w_.object(p, C_PLAYER, p.write_body))
        write_list(w, self.container, _put_unit)
        w.u8(self.loaded)
        if self.loaded:
            if self.mission is not None:
                self.mission.write(w)
            else:
                w.raw(self.mission_raw)
        elif self.mission_raw or self.mission is not None:
            raise ValueError("a mission branch needs the loaded flag")
        w.u32(self.tail_words[0])
        w.u32(self.tail_words[1])
        if len(self.debug) != DEBUG_SIZE:
            raise ValueError("the debug block is 400 bytes")
        w.raw(self.debug)
        out = w.getvalue()
        if self.pad or len(out) & 1:
            out += self.pad or b"\0"
        return out
