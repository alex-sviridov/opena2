"""Map entities: players (section 5), units (section 6), item groups (section 8) and
item property records (section 9).  Spec: docs/formats/map.md part 5.

Read by the map reader FUN_00534ad4 (cases 5, 6, 8, 9); units are instantiated by the
server in FUN_00561bf9, items and inventories by FUN_00564072.
"""

import struct
from dataclasses import dataclass, field

PLAYER_SIZE = 76
UNIT_SIZE = 48
NO_HP = 0xFFFF             # HP override "keep the data.bin value"
HUMAN_FLAG = 0x10          # unit flags: data.bin humans group, else monsters
GROUP_HEADER = 20
MEMBER_SIZE = 10


@dataclass(frozen=True)
class Player:
    """Section 5 record.  `index` is the 1-based record number (the owner value of structures)."""
    index: int
    colour: int            # u32 -> object +0x0c: row of humans/human.pal (0 blue, 1 green, ...)
    flags: int             # u32 -> object +0x34: only bit 1 is read (multiplayer); 0/1 in the files, unused
    money: int             # u32 -> object +0x10: 0 for record 1, else 5000; no reader found
    name: str
    relations: tuple       # 16 x u16 -> array at object +0x38


@dataclass(frozen=True)
class Unit:
    """Section 6 record (48 bytes).  x, y are 1/256 cells (always the cell centre, 128)."""
    x: int
    y: int
    type: int              # units.reg ID (editor copy; the server uses `server_id`)
    tier: int              # u16 at +10, read but unused by the game
    flags: int             # +12, bit 0x10 = human (data.bin group 6), else monster (group 5)
    behaviour: int         # +16, bits 1/2/4/8 set booleans on the unit
    server_id: int         # +20, data.bin `serverID` (humans param 24 / monsters param 55)
    owner: int             # +24, section 5 record number (1-based)
    group: int             # +28, section 8 group (1-based, 0 = none)
    field_32: int          # +32, read but unused
    hp: int                # +36, current HP override, 0xFFFF = default
    max_hp: int            # +38, max HP override, 0xFFFF = default
    uid: int               # +40 low 16 bits; object ID 0x6000 + uid
    stamp: int             # +40 high 16 bits (editor stamp, unused)
    squad: int             # +44, per-owner squad number

    @property
    def is_human(self):
        return bool(self.flags & HUMAN_FLAG)

    @property
    def cell(self):
        return self.x >> 8, self.y >> 8


@dataclass(frozen=True)
class Member:
    """Section 8 member: an item in a group."""
    code: int              # u32 item code (low 16 bits used, see map.md)
    slot: int              # u16, 0 = backpack (always 0 in the files)
    record: int            # u32, 1-based section 9 record (0 = none)


@dataclass(frozen=True)
class Group:
    """Section 8 record.  A unit record's `group` link makes it that unit's inventory (the loader
    writes the unit's uid over `carrier_raw`); a group no unit links to is a sack on the
    ground at (x, y), 1/256 cells."""
    carrier_raw: int
    x: int
    y: int
    extra: int             # +0x48 (0 in 43 groups, 100/5000/10000 in 8)
    members: tuple


@dataclass(frozen=True)
class ItemRecord:
    """Section 9 record: item properties (or a spot / spellbook / building link)."""
    head: int              # u32 (version > 989)
    a: int                 # +8
    b: int                 # +0xc
    flags: bytes           # 6 bytes at +0x10
    c: int                 # u32 at +0x16
    props: tuple           # n x (stat id u16, value u32)


def parse_players(data, count):
    if len(data) != PLAYER_SIZE * count:
        raise ValueError("players: %d bytes for %d records" % (len(data), count))
    from .map import decode_text          # map.py imports this module
    out = []
    for i in range(count):
        colour, flags, money = struct.unpack_from("<III", data, i * PLAYER_SIZE)
        name = decode_text(data[i * PLAYER_SIZE + 12:i * PLAYER_SIZE + 44])
        rel = struct.unpack_from("<16H", data, i * PLAYER_SIZE + 44)
        out.append(Player(i + 1, colour, flags, money, name, rel))
    return out


def parse_units(data, count):
    if len(data) != UNIT_SIZE * count:
        raise ValueError("units: %d bytes for %d records" % (len(data), count))
    out = []
    for i in range(count):
        (x, y, t, tier, fl, beh, sid, own, grp, f32, hp, mhp, u, sq) = \
            struct.unpack_from("<iiHHIIIIIIHHII", data, i * UNIT_SIZE)
        out.append(Unit(x, y, t, tier, fl, beh, sid, own, grp, f32, hp, mhp,
                        u & 0xFFFF, u >> 16, sq))
    return out


def parse_groups(data, count):
    """Section 8; raises ValueError unless the records tile the section exactly."""
    out, pos = [], 0
    for _ in range(count):
        n, carrier, x, y, extra = struct.unpack_from("<IIiiI", data, pos)
        pos += GROUP_HEADER
        mem = []
        for _ in range(n):
            code, slot, rec = struct.unpack_from("<IHI", data, pos)
            pos += MEMBER_SIZE
            mem.append(Member(code, slot, rec))
        out.append(Group(carrier, x, y, extra, tuple(mem)))
    if pos != len(data):
        raise ValueError("groups: %d bytes left" % (len(data) - pos))
    return out


def parse_item_records(data):
    """Section 9: u32 count, then records; raises ValueError unless they tile exactly."""
    (count,) = struct.unpack_from("<I", data, 0)
    pos, out = 4, []
    for _ in range(count):
        if pos + 26 > len(data):
            raise ValueError("item records end inside a record")
        head, a, b = struct.unpack_from("<III", data, pos)
        flags = bytes(data[pos + 12:pos + 18])
        c, n = struct.unpack_from("<II", data, pos + 18)
        pos += 26
        if pos + 6 * n > len(data):
            raise ValueError("item records end inside a property list")
        props = tuple(struct.unpack_from("<HI", data, pos + 6 * j) for j in range(n))
        pos += 6 * n
        out.append(ItemRecord(head, a, b, flags, c, props))
    if pos != len(data):
        raise ValueError("item records: %d bytes left" % (len(data) - pos))
    return out


def server_ids(db):
    """({serverID: monster record}, {serverID: human record}) of a DataBin (FUN_004fd62f /
    FUN_004fd5ad: the unit record's `server_id` is matched against the `serverID` column)."""
    out = []
    for group, recs in (("monsters", db.monsters), ("humans", db.humans)):
        col = db.columns(group).index("serverID")
        out.append({r.params[col]: r for r in recs if len(r.params) > col})
    return tuple(out)


def template(db, unit, _cache={}):
    """The data.bin record a unit is built from, or None."""
    key = id(db)
    if key not in _cache:
        _cache[key] = (db, server_ids(db))
    monsters, humans = _cache[key][1]
    return (humans if unit.is_human else monsters).get(unit.server_id)
