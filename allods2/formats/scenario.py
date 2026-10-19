"""Map scenario sections: the trigger script (section 7), repop records (10), the multiplayer inn / shop and
signpost records (11), the music zones (12).  Spec: docs/formats/map.md part 6; runtime: docs/engine/triggers.md.

Read by the map reader FUN_00534ad4 (cases 7, 10, 11, 12); the server compiles section 7 at map start in
FUN_00562745, section 10 is read by FUN_00560d9b, section 11 by FUN_00561422 and section 12 by the client
(FUN_004a449c -> FUN_004754e9).
"""

import struct
from dataclasses import dataclass

from ..text import decode_text as _decode

RECORD_SIZE = 0x31C                 # instant / check record (alloc 0x31c, FUN_00536ab0)
TRIGGER_SIZE = 0xB8                 # trigger record, read as one block into the array at map +0x78
NAME_SIZE = 0x40
LABEL_SIZE = 0x40
ARGS = 10
PAIRS, INSTANTS_PER_TRIGGER = 3, 4
REPOP_SIZE = 16                     # section 10 record (map +0x310)
INN_SIZE, SHOP_SIZE, POINTER_SIZE = 12, 0x54, 12       # section 11 lists (map +0x338, +0x324, +0x34c)
ZONE_SIZE = 0x1C                    # section 12 record (map +0x374 default, +0x360 list)

# argument kinds (record +0x70, the compiler's switch in FUN_00562745)
K_NONE, K_INT, K_GROUP, K_PLAYER, K_UNIT, K_X, K_Y, K_CONST, K_ITEM, K_BUILDING = range(10)
OBJECT_KINDS = (K_GROUP, K_PLAYER, K_UNIT)
CONSTANT = 0x10002                  # check: constant value; instant: "Drop Location"
VAR_LOW, VAR_HIGH = 8000, 9999      # a group / player / unit argument in this range is a variable reference
HERO_BASE, NAMED_BASE = 10001, 11001    # unit ids: < 10001 scenario uid, 10001.. hero index, >= 11001 by name
ITEM_BASE = 0xE18                   # item argument value + 0xe18 = special item code (class 14, index + 0x18)
OPS = ("==", "!=", ">", "<", ">=", "<=")    # trigger pair operators 0..5 (FUN_00574ba1)


def _text(buf):
    return _decode(bytes(buf).split(b"\0", 1)[0])


@dataclass(frozen=True)
class Record:
    """An instant (section 7 list 1) or check (list 2) record, 796 bytes, file order:
    name[64], type, id, flag (object +0x318), values[10] (+0x48), kinds[10] (+0x70), labels[10][64] (+0x98)."""
    name: str
    type: int               # instant / check kind (FUN_00574f3f / FUN_00574955 switch); 0x10002 constant
    id: int                 # +0x44 the number triggers refer to (unique per list, gaps where records were deleted)
    flag: int               # +0x318, copied to check +0x74; no reader found
    values: tuple           # +0x48 10 x i32
    kinds: tuple            # +0x70 10 x i32 argument kinds (K_*)
    labels: tuple           # +0x98 10 x 64-byte editor labels ("<None>" for unused)

    def args(self):
        """(kind, value) of the used arguments, in slot order (a kind-0 slot is unused)."""
        return [(k, v) for k, v in zip(self.kinds, self.values) if k != K_NONE]


@dataclass(frozen=True)
class Trigger:
    """Section 7 list 3 record (184 bytes): name[64], 64 bytes the game never reads, then
    3 check pairs (+0x80), 4 instant ids (+0x98), 3 pair operators (+0xa8), the once flag (+0xb4)."""
    name: str
    reserved: bytes         # +0x40..+0x7f editor memory, not read by FUN_00562745
    pairs: tuple            # 3 x (check id a, check id b); a pair counts only when both ids are non-zero
    instants: tuple         # 4 instant ids, 0 = empty slot
    ops: tuple              # 3 operators (OPS index) of the pairs
    once: int               # +0xb4: non-zero = fires at most once

    @property
    def active(self):
        """The compiler skips a trigger whose first check id is 0 (FUN_00562745 0x563ba9)."""
        return self.pairs[0][0] != 0


@dataclass(frozen=True)
class Scenario:
    instants: tuple
    checks: tuple
    triggers: tuple


def parse_record(b):
    if len(b) != RECORD_SIZE:
        raise ValueError("scenario record is %d bytes, not %d" % (len(b), RECORD_SIZE))
    t, rid, flag = struct.unpack_from("<iii", b, NAME_SIZE)
    values = struct.unpack_from("<10i", b, 0x4C)
    kinds = struct.unpack_from("<10i", b, 0x74)
    labels = tuple(_text(b[0x9C + LABEL_SIZE * k:0x9C + LABEL_SIZE * (k + 1)]) for k in range(ARGS))
    return Record(_text(b[:NAME_SIZE]), t, rid, flag, values, kinds, labels)


def parse_trigger(b):
    if len(b) != TRIGGER_SIZE:
        raise ValueError("trigger record is %d bytes, not %d" % (len(b), TRIGGER_SIZE))
    v = struct.unpack_from("<14i", b, 0x80)
    pairs = tuple((v[2 * k], v[2 * k + 1]) for k in range(PAIRS))
    return Trigger(_text(b[:NAME_SIZE]), bytes(b[NAME_SIZE:0x80]), pairs, v[6:10], v[10:13], v[13])


def parse_scenario(data):
    """Section 7: three counted lists (u32 n + n records each): instants, checks, triggers.  The header's
    `n_sec7` (= the sum) is not used: each count is read in front of its list.  Must consume all bytes."""
    data = bytes(data)
    pos, lists = 0, []
    for size, fn in ((RECORD_SIZE, parse_record), (RECORD_SIZE, parse_record), (TRIGGER_SIZE, parse_trigger)):
        if pos + 4 > len(data):
            raise ValueError("section 7 ends before a list count")
        n = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        if pos + n * size > len(data):
            raise ValueError("section 7 list of %d records runs past the end" % n)
        lists.append(tuple(fn(data[pos + i * size:pos + (i + 1) * size]) for i in range(n)))
        pos += n * size
    if pos != len(data):
        raise ValueError("%d bytes after the section 7 lists" % (len(data) - pos))
    return Scenario(*lists)


# --- section 10 -------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Repop:
    """Section 10 record (16 bytes; none in the campaign): read by the scripted squad creation FUN_00560d9b."""
    squad: int              # +0 matched against the group's squad number (+0x1c)
    delay: int              # +4 repop delay in percent of the base (`* [0x690418] / 100`)
    flags: int              # +8 bit 1: run the instant below, 2: keep +0xbc, 4: group flag +0x48, 8: group flag +0x4c
    instant: int            # +0xc instant position (counted like a signpost's, see `Pointer`)


def _records(data, size, count, fn, what):
    data = bytes(data)
    if len(data) != size * count:
        raise ValueError("%s: %d bytes, expected %d x %d" % (what, len(data), count, size))
    return tuple(fn(data[i * size:(i + 1) * size]) for i in range(count))


def parse_repops(data, count):
    return _records(data, REPOP_SIZE, count, lambda b: Repop(*struct.unpack("<iiIi", b)), "section 10")


# --- section 11 -------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Inn:
    """Section 11 list A (12 bytes): settings of a multiplayer inn (structure types 0x43-0x45, 0x63-0x65, 0x6f-0x71)."""
    uid: int                # structure uid
    flags: int              # 2: +0xd4 := value, 0x10: +0xc4, 0x20: +0xc8, 0x40: +0xcc, 4: +0xd0 (FUN_00561422)
    value: int


@dataclass(frozen=True)
class Shop:
    """Section 11 list B (84 bytes; none in the campaign): 4 slots of 5 words for a multiplayer shop (types 0x22, 0x23,
    0x5d-0x5f, 0x69-0x6b), copied to the shop object +0x70 + 0x14 * slot (slot words b, c, d, e, a)."""
    uid: int
    a: tuple                # +0x04 4 x i32 -> slot +0x10
    b: tuple                # +0x14 -> slot +0x00
    c: tuple                # +0x24 -> slot +0x04
    d: tuple                # +0x34 -> slot +0x08
    e: tuple                # +0x44 -> slot +0x0c


@dataclass(frozen=True)
class Pointer:
    """Section 11 list C (12 bytes): a usable signpost (types 0x46-0x4b, class "Pointer") and the instant it runs."""
    uid: int                # structure uid
    enabled: int            # 0: the signpost keeps instant -1 (none)
    instant: int            # position n in the instant list; the runtime index = the number of non-0x10002 instants before it


def parse_section11(data, counts):
    data = bytes(data)
    na, nb, nc = counts
    if len(data) != na * INN_SIZE + nb * SHOP_SIZE + nc * POINTER_SIZE:
        raise ValueError("section 11: %d bytes, counts %s" % (len(data), counts))
    inns = _records(data[:na * INN_SIZE], INN_SIZE, na, lambda b: Inn(*struct.unpack("<iIi", b)), "section 11 A")
    off = na * INN_SIZE

    def shop(b):
        v = struct.unpack("<21i", b)
        return Shop(v[0], v[1:5], v[5:9], v[9:13], v[13:17], v[17:21])

    shops = _records(data[off:off + nb * SHOP_SIZE], SHOP_SIZE, nb, shop, "section 11 B")
    off += nb * SHOP_SIZE
    pointers = _records(data[off:], POINTER_SIZE, nc, lambda b: Pointer(*struct.unpack("<iii", b)), "section 11 C")
    return inns, shops, pointers


# --- section 12 -------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class MusicZone:
    """Section 12 record (28 bytes): a music node.  The client takes the zone nearest to the camera position whose
    radius contains it, then one of its 4 themes at random (-1 = none, redrawn)."""
    x: int                  # cell; (0, 0) marks the default record
    y: int
    radius: int             # cells (compared with the distance in 1/256 cell against radius << 8)
    themes: tuple           # 4 x i32 music numbers, -1 = none

    @property
    def is_default(self):
        return self.x == 0 and self.y == 0


def parse_music(data, count):
    """Section 12: the default record (map +0x374), then `count` zones (+0x360).  Returns (default, zones)."""
    def zone(b):
        v = struct.unpack("<7i", b)
        return MusicZone(v[0], v[1], v[2], v[3:7])

    allz = _records(data, ZONE_SIZE, count + 1, zone, "section 12")
    return allz[0], allz[1:]


def runtime_instant_index(instants, position):
    """The runtime instant index of the instant at file `position` (signposts, repop records): the count of
    instants of type < 0x10002 among the first `position` records (FUN_00561422 0x561951-, FUN_00560d9b)."""
    return sum(1 for r in instants[:position] if r.type < CONSTANT)
