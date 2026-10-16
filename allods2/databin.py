"""world/data/data.bin: the compiled game database (an MFC CArchive).

Spec: docs/formats/databin.md.  Eight groups, each an (always empty) string
array and then one or three record lists: qualities and materials, the
50 stat names, three item-class lists, special items, monsters, humans,
structures, spells.  Every record but the first two kinds is a name plus an
int parameter array plus per-kind extras.
"""

import os
import struct
from dataclasses import dataclass, field

PATH = os.path.join("world", "data", "data.bin")

# Monster parameter index -> server unit field (FUN_0051b12f reads them in
# order; -1 keeps the default).  Names follow the stat list where the field
# use is known; "unit+0x.." where it is not.
MONSTER_PARAMS = (
    "body", "reaction", "mind", "spirit",                     # +0x84 +0x86 +0x88 +0x8a
    "healthMax", "unit+0x98", "manaMax", "unit+0x9e",          # +0x96 (+0x94 = it) .. +0x9c
    "speed", "rotationSpeed", "scanRange",                     # +0x8c, mover+0xa, +0xa5
    "damageMin", "damageMax", "damageKind",                    # -> +0xb4/+0xb5 or +0xb7.. (kind 0..3)
    "unit+0xa6", "unit+0xbe", "unit+0xc0",                     # +0xa6 (+0xa8 = it)
    "attackWindup", "attackRecovery",                          # +0x134, +0x135
    "protectionFire", "protectionWater", "protectionAir",      # +0xc4 .. +0xcc
    "protectionEarth", "protectionAstral",
    "unit+0xcf", "unit+0xd0", "unit+0xd1", "unit+0xd2", "unit+0xd3",
    "unitType",                                                # +0xe, units.reg ID
    "paletteVariant", "unit+0x49", "unit+0x4a", "unused33",   # +0x4b (units.md), +0x49, +0x4a
    "ai+0x40", "ai+0x44", "ai+0x71", "unit+0x1c",              # +0x1c4 object; 37 also FUN_0051b595
)
MONSTER = {name: i for i, name in enumerate(MONSTER_PARAMS)}

# Spell and item parameter indices with a confirmed use.
SPELL_KIND, SPELL_MISSILE_SPEED = 5, 7       # kind 2 = missile; speed in 1/256 cell per tick
ITEM_WEIGHT, ITEM_WINDUP, ITEM_RECOVERY = 3, 12, 13


@dataclass
class Factor:
    """Quality or material: 16 bytes (zero in the file) + 7 doubles.  The
    item weight uses doubles[1] (record +0x38) of both."""
    name: str
    head: bytes
    doubles: tuple


@dataclass
class Record:
    name: str
    params: list
    extra: tuple = ()


@dataclass
class DataBin:
    qualities: list = field(default_factory=list)
    materials: list = field(default_factory=list)
    stats: list = field(default_factory=list)        # index 0 is the empty name
    armour: list = field(default_factory=list)       # 1-based lists start at index 1:
    shields: list = field(default_factory=list)      # element i is list index i + 1
    weapons: list = field(default_factory=list)
    items: list = field(default_factory=list)
    monsters: list = field(default_factory=list)
    humans: list = field(default_factory=list)
    structures: list = field(default_factory=list)
    spells: list = field(default_factory=list)
    headers: list = field(default_factory=list)      # the 8 leading string arrays

    def stat_index(self, name):
        """Effect kind of a stat name (case-insensitive, as FUN_005285cb)."""
        low = name.lower()
        for i, r in enumerate(self.stats):
            if i and r.name.lower() == low:
                return i
        return 0

    def monster(self, name):
        """(type id, record) of the first monster named `name` in the
        server's search order (FUN_0051b595: index 26 up, 30..62 skipped)."""
        n = len(self.monsters) + 1
        i = 26
        while i < n:
            if i == 30:
                i = 63
                continue
            r = self.monsters[i - 1]
            if r.name.lower() == name.lower():
                return i, r
            i += 1
        return None


class _Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, n):
        b = self.data[self.pos:self.pos + n]
        if len(b) != n:
            raise ValueError("data.bin truncated at 0x%x" % self.pos)
        self.pos += n
        return b

    def u8(self):
        return self.take(1)[0]

    def u16(self):
        return struct.unpack("<H", self.take(2))[0]

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def count(self):
        """MFC ReadCount: u16, or u32 after 0xffff."""
        n = self.u16()
        return self.u32() if n == 0xFFFF else n

    def string(self):
        """MFC CString: u8 length, 0xff -> u16, 0xffff -> u32; cp1251."""
        n = self.u8()
        if n == 0xFF:
            n = self.u16()
            if n == 0xFFFF:
                n = self.u32()
        return self.take(n).decode("cp1251")

    def strings(self):
        return [self.string() for _ in range(self.count())]

    def base(self):
        name = self.string()
        n = self.count()
        return name, list(struct.unpack("<%di" % n, self.take(4 * n)))

    def records(self, read, one_based):
        n = self.u32()
        return [read() for _ in range(1 if one_based else 0, n)]


def parse_databin(data):
    r = _Reader(data)
    db = DataBin()

    def factor():
        name = r.string()
        raw = r.take(0x48)
        return Factor(name, raw[:16], struct.unpack("<7d", raw[16:]))

    def base():
        return Record(*r.base())

    def item_class():
        name, params = r.base()
        return Record(name, params, (struct.unpack("<7h", r.take(14)), r.strings()))

    def special_item():
        name, params = r.base()
        return Record(name, params, (r.u8(), r.string()))

    def strings(n):
        def read():
            name, params = r.base()
            return Record(name, params, tuple(r.string() for _ in range(n)))
        return read

    db.headers.append(r.strings())
    db.qualities = r.records(factor, False)
    db.materials = r.records(factor, False)
    db.headers.append(r.strings())
    db.stats = r.records(base, False)
    db.headers.append(r.strings())
    db.armour = r.records(item_class, True)
    db.shields = r.records(item_class, True)
    db.weapons = r.records(item_class, True)
    db.headers.append(r.strings())
    db.items = r.records(special_item, True)
    db.headers.append(r.strings())
    db.monsters = r.records(strings(2), True)
    db.headers.append(r.strings())
    db.humans = r.records(strings(10), True)
    db.headers.append(r.strings())
    db.structures = r.records(base, True)
    db.headers.append(r.strings())
    db.spells = r.records(strings(1), True)
    if r.pos != len(data):
        raise ValueError("data.bin: %d trailing bytes" % (len(data) - r.pos))
    return db


def load_databin(path):
    with open(path, "rb") as f:
        return parse_databin(f.read())


def databin(data_dir):
    """load_databin of the install's world/data/data.bin."""
    return load_databin(os.path.join(data_dir, PATH))


@dataclass
class Modifier:
    """One `name=value[:time]` term (FUN_005285cb)."""
    kind: int                 # stat index = effect kind (effect +0x3c)
    value: int                # effect +0x40
    mode: int                 # effect +0x3d: 0 permanent, 1 duration, 2 continuous, 4 charges, 8 single use
    time: int = 0             # duration / period / charges as written; ticks = time << 4


def parse_modifier(db, text):
    """Plain `stat=±N[:duration T|continuous T|charges T|singleuse|permanent]`
    terms; castSpell/teachSpell/damage* values are not decoded here."""
    if "=" not in text:
        return None
    name, rest = text.split("=", 1)
    kind = db.stat_index(name.strip())
    if not kind:
        return None
    value, _, time = rest.partition(":")
    value = value.strip()
    mod = Modifier(kind, int(value) if value.lstrip("+-").isdigit() else 0, 0)
    t = time.strip().lower()                    # FUN_00528f6d
    if t == "singleuse":
        mod.mode = 8
    elif t != "permanent":
        for word, mode in (("charges", 4), ("duration", 1), ("continuous", 2)):
            at = t.find(word)
            if at >= 0:
                mod.mode, mod.time = mode, int(t[at + len(word):].strip() or 0)
                break
    return mod
