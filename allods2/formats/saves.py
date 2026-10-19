"""Character files (`.a2c`), the hall of fame (`famehall.dat`) and saved games (`game%d.sav`).

Spec: docs/formats/saves.md.  The `.a2c` reader follows FUN_004ee7cb (chunk reader) and FUN_004ea6ab (hero builder), the
writer FUN_004edbaf; the item stream is FUN_004ed5f5 / FUN_005241bf; the hall of fame FUN_004a91d5 / FUN_004a90c9; the
saved game FUN_004e9816 (server block), FUN_004e9b95 and FUN_004ec732 (server stream), FUN_0048dc9f (client tail) and the
Scenario.dll exports ScenarioSave / ScenarioLoad.  The install holds only a `famehall.dat`; the `.a2c` and `.sav` layouts
are decoded from the code and tested on synthetic files (docs/formats/saves.md, "Evidence").
"""

import random
import struct
from dataclasses import dataclass, field

from ..reg import HEADER as REG_HEADER, ENTRY as REG_ENTRY, parse_reg
from ..text import decode_text

U32 = 0xFFFFFFFF

# --- the byte layer ------------------------------------------------------------------------------------------------


def checksum(data):
    """FUN_004edacd: `h = h * 2 + byte` over the plain bytes, 32 bits."""
    h = 0
    for b in data:
        h = ((h << 1) + b) & U32
    return h


def xor_stream(data, key):
    """FUN_004edb23 (its own inverse): `r = key | key << 16`; every byte is xored with `(r >> 16) & 0xff`, then `r <<= 1`
    (32 bits) and after every 16th byte `r |= key`.  `key` is the 16-bit flags word of the chunk header."""
    key &= 0xFFFF
    r = key | key << 16
    out = bytearray(data)
    for i in range(len(out)):
        out[i] ^= (r >> 16) & 0xFF
        r = (r << 1) & U32
        if i & 15 == 15:
            r |= key
    return bytes(out)


def rle_decode(data, unit=1):
    """FUN_00421080 (`unit` 1: bytes) / FUN_0053a330 (`unit` 2: 16-bit words).  `u32` unit count, then ops: a byte
    with bit 7 = run of `byte & 0x7f` copies of the next unit; else a literal of `byte` units."""
    data = bytes(data)
    total, = struct.unpack_from("<I", data, 0)
    out = bytearray()
    pos = 4
    while pos < len(data):
        c = data[pos]
        if c & 0x80:
            out += data[pos + 1:pos + 1 + unit] * (c & 0x7F)
            pos += 1 + unit
        else:
            out += data[pos + 1:pos + 1 + c * unit]
            pos += 1 + c * unit
    if len(out) != total * unit:
        raise ValueError("RLE stream holds %d units, header says %d" % (len(out) // unit, total))
    return bytes(out)


def rle_encode(data, unit=1):
    """FUN_0053c140 / FUN_00539e70: the exe's greedy encoder (a run needs two equal units and holds at most 0x7f; a literal
    ends before the next pair, at most 0x7e units, and takes the last unit when it reaches the end).  The exe peeks one unit
    past the end of the buffer; here that unit never matches, which can change the encoding of the last unit only (the
    stream decodes identically)."""
    data = bytes(data)
    if len(data) % unit:
        raise ValueError("length is not a multiple of %d" % unit)
    units = [data[i:i + unit] for i in range(0, len(data), unit)]
    n = len(units)
    out = bytearray(struct.pack("<I", n))
    pos = 0
    nxt = lambda i: units[i] if i < n else None
    while pos < n:
        if units[pos] == nxt(pos + 1):
            count = 1
            while units[pos + count - 1] == nxt(pos + count) and count < 0x7F and pos + count < n:
                count += 1
            out.append(0x80 | count)
            out += units[pos]
            pos += count
        else:
            count = 1
            while units[pos + count - 1] != nxt(pos + count) and count < 0x7F and pos + count < n:
                count += 1
            if pos + count == n:
                count += 1
            out.append(count - 1)
            out += b"".join(units[pos:pos + count - 1])
            pos += count - 1
    return bytes(out)


# --- items (the wire item stream) ----------------------------------------------------------------------------------

K_CAST_SPELL = 41               # ')' : spell id, charges (record `)` v 0x32 w)
K_MINMAX = (44, 45, 46, 47, 48)     # ',' '-' '.' '/' '0' : min, spread (record `k v k w`)
K_SKIPPED = 1                   # a modifier of kind 1 is not written


@dataclass
class Item:
    """One item of the stream (FUN_004ed5f5 reads it, FUN_005241bf writes it).  `code` is the 16-bit item code
    (`material << 12 | class << 8 | quality << 5 | index`, items.md); 0 = an empty slot.  Without `mods`: a stack of `count`.
    With `mods`: a single item with the u32 `price` field (item `+0x1c`) and the modifier records
    `(kind, a, b)`: kind 41 castSpell (spell id, charges), kinds 44-48 min / spread, any other kind has only `a`."""
    code: int = 0
    count: int = 1
    price: int = 0
    mods: tuple = ()
    new: bool = False               # flag 0x40, written when the item was unseen; the reader ignores it

    @property
    def cls(self):
        return (self.code >> 8) & 15

    @property
    def quality(self):
        return (self.code >> 5) & 7

    @property
    def material(self):
        return self.code >> 12

    @property
    def index(self):
        return self.code & 0x1F


def encode_item(it):
    """FUN_005241bf (without the optional trailing byte)."""
    out = bytearray(struct.pack("<H", it.code))
    if not it.mods:
        if it.count < 0x40:
            out.append((it.count & 0x3F) | 0x80 | (0x40 if it.new else 0))
        else:
            out.append(0x40 if it.new else 0)
            out += struct.pack("<H", it.count)
        return bytes(out)
    body, units, cast = bytearray(), 0, False
    for kind, a, b in it.mods:
        if kind == K_SKIPPED:
            continue
        body += bytes((kind, a))
        if kind == K_CAST_SPELL:
            body += bytes((0x32, b))
            units += 2
            cast = True
        elif kind in K_MINMAX:
            body += bytes((kind, b))
            units += 2
        else:
            units += 1
    out.append(0x20 | (0x10 if cast else 0) | (0x40 if it.new else 0) | (units & 0xF))
    out += struct.pack("<I", it.price & U32)
    return bytes(out) + bytes(body)


def decode_item(data, pos=0):
    """FUN_004ed5f5: returns (Item, next position)."""
    code, f = struct.unpack_from("<HB", data, pos)
    pos += 3
    if code == 0:
        return Item(0, 0), pos
    if f & 0x80:
        return Item(code, f & 0x3F, new=bool(f & 0x40)), pos
    if not f & 0x20:
        count, = struct.unpack_from("<H", data, pos)
        return Item(code, count, new=bool(f & 0x40)), pos + 2
    units = f & 0xF
    price, = struct.unpack_from("<I", data, pos)
    pos += 4
    mods = []
    while units:
        kind, a = data[pos], data[pos + 1]
        pos += 2
        if kind == K_CAST_SPELL or kind in K_MINMAX:
            b = data[pos + 1]               # the byte between is 0x32 for castSpell, else the kind again
            pos += 2
            units -= 2
        else:
            b = 0
            units -= 1
        mods.append((kind, a, b))
    return Item(code, 1, price, tuple(mods), bool(f & 0x40)), pos


@dataclass
class ItemPacket:
    """The inventory message (type 0x76, net packet object ctor FUN_0050c7f5) as stored in a chunk: 9 bytes from the packet
    `+0xa` (`head` 3 bytes uninitialised in the exe, `count` u16 `+0xd`, `extra` u16 `+0xf`, `length` u16 `+0x11` = bytes of
    the stream), then the items."""
    items: list
    head: bytes = b"\0\0\0"
    count: int = 0
    extra: int = 0

    def pack(self):
        stream = b"".join(encode_item(i) for i in self.items)
        return self.head + struct.pack("<HHH", self.count, self.extra, len(stream)) + stream

    @classmethod
    def parse(cls, data, fixed=None):
        """`fixed`: read exactly that many items (the equipment list, FUN_004ea6ab reads 12), else until `length`."""
        head = bytes(data[:3])
        count, extra, length = struct.unpack_from("<HHH", data, 3)
        items, pos = [], 9
        if fixed is not None:
            for _ in range(fixed):
                it, pos = decode_item(data, pos)
                items.append(it)
        else:
            while pos < 9 + length:
                it, pos = decode_item(data, pos)
                items.append(it)
        return cls(items, head, count, extra)


# --- the character file ----------------------------------------------------------------------------------------------

A2C_MAGIC = 0x04507989
TAG_ID, TAG_STATS, TAG_BLOB, TAG_EQUIP, TAG_PACK, TAG_HOTKEYS = 0xAAAAAAAA, 0x41392521, 0x55555555, 0xDE0DE0DE, 0x3A5A3A5A, 0x40A40A40
ID_SIZE = 0x34
STATS_SIZE = 0x34
BLOB_SIZE = 0xA00
EQUIP_SLOTS = 12
START_TEMPLATES = {0: "Start_MF", 0x40: "Start_MM", 0x80: "Start_FF", 0xC0: "Start_FM"}     # by `flags & 0xc0`

def _stats_decode(raw):
    """Stored 0x34 bytes -> plain (the reader's per-field transforms; each field depends on the decoded ones before)."""
    w = list(struct.unpack("<13I", raw))
    b = bytearray(raw)
    v0 = w[0] ^ 0x01529251
    v1 = (w[1] + 0x13141516 + v0 * 5) & U32
    v2 = (w[2] + 0xABCDEF + v1 * 7) & U32
    v3 = w[3] ^ 0x17FF12AA
    v4 = (w[4] - 0x21524542 + v0 * 3) & U32
    v5 = (b[0x14] + ((v4 & 0xFF) * 0x11) + ((v0 & 0xFF) * 0x13)) & 0xFF
    v6 = (b[0x15] + v5 * 3) & 0xFF
    v7 = (b[0x16] + v5 + v6 * 5) & 0xFF
    v8 = (b[0x17] + v5 * 7 + v7 * 9) & 0xFF
    v9 = (w[6] - 0x10121974) & U32
    v10 = w[7]
    pools = [w[8] ^ 0xDADEDADE]
    prev = pools[0]
    for i in range(1, 5):
        prev = (w[8 + i] + prev * -0x771) & U32
        pools.append(prev)
    out = struct.pack("<5I4B2I5I", v0, v1, v2, v3, v4, v5, v6, v7, v8, v9, v10, *pools)
    return out


def _stats_encode(plain):
    """Inverse of `_stats_decode` (FUN_004edbaf)."""
    v = struct.unpack("<5I4B2I5I", plain)
    v0, v1, v2, v3, v4, v5, v6, v7, v8, v9, v10 = v[:11]
    pools = v[11:]
    s0 = v0 ^ 0x01529251
    s1 = (v1 - (v0 * 5 + 0x13141516)) & U32
    s2 = (v2 - (v1 * 7 + 0xABCDEF)) & U32
    s3 = v3 ^ 0x17FF12AA
    s4 = (v4 - (v0 * 3 - 0x21524542)) & U32
    s5 = (v5 - ((v4 & 0xFF) * 0x11 + (v0 & 0xFF) * 0x13)) & 0xFF
    s6 = (v6 - v5 * 3) & 0xFF
    s7 = (v7 - (v5 + v6 * 5)) & 0xFF
    s8 = (v8 - (v5 * 7 + v7 * 9)) & 0xFF
    s9 = (v9 + 0x10121974) & U32
    sp = [pools[0] ^ 0xDADEDADE]
    for i in range(1, 5):
        sp.append((pools[i] - pools[i - 1] * -0x771) & U32)
    return struct.pack("<5I4B2I5I", s0, s1, s2, s3, s4, s5, s6, s7, s8, s9, v10, *sp)


@dataclass
class Identity:
    """Chunk 0xAAAAAAAA (0x34 bytes; written by FUN_004e9e97 / the creation screen FUN_004915cd, read by FUN_004904c5)."""
    ids: tuple = (0, 0)             # +0 two u32: the file name is `%u%u.a2c`
    field8: int = 0                 # +8 (client this+0x64)
    name: str = ""                  # +0xc, 32 bytes, "name|title" shown by the character list
    flags: int = 0                  # +0x2c: 0x80 female, 0x40 mage (template Start_MF / MM / FF / FM)
    portrait: int = 0               # +0x2d -> hero +0x4b
    school: int = 0                 # +0x2e best school 1..5 -> hero +0x23c
    kind: int = 4                   # +0x2f (server writes 4; the creation screen writes its own byte)
    difficulty: int = 0             # +0x30 (player +0xa44)
    pad: bytes = b"\0\0\0"          # +0x31..+0x33, stack garbage

    def pack(self):
        name = self.name.encode("cp1251")[:31]
        return (struct.pack("<3I", self.ids[0], self.ids[1], self.field8) + name.ljust(0x20, b"\0")
                + bytes((self.flags, self.portrait, self.school, self.kind, self.difficulty)) + self.pad)

    @classmethod
    def parse(cls, raw):
        a, b, f8 = struct.unpack_from("<3I", raw, 0)
        name = decode_text(bytes(raw[0xC:0x2C]).split(b"\0", 1)[0])
        return cls((a, b), f8, name, raw[0x2C], raw[0x2D], raw[0x2E], raw[0x2F], raw[0x30], bytes(raw[0x31:0x34]))

    @property
    def template(self):
        return START_TEMPLATES[self.flags & 0xC0]

    @property
    def filename(self):
        return "%u%u.a2c" % self.ids


@dataclass
class Stats:
    """Chunk 0x41392521 (0x34 bytes of fields with the transforms of FUN_004ee7cb).  Offsets and the player fields they come
    from (FUN_004e9e97) / go to (FUN_004ea6ab)."""
    kills_monsters: int = 0         # +0x00 player +0xa48
    kills_players: int = 0          # +0x04 player +0xa4c
    stat_a58: int = 0               # +0x08 player +0xa58
    hero_deaths: int = 0            # +0x0c player +0xa54
    gold: int = 0                   # +0x10 player +0x3c
    attributes: tuple = (30, 30, 30, 30)    # +0x14..+0x17 body, reaction, mind, spirit (base: stat minus the effect bonus byte)
    spells: int = 0                 # +0x18 spell book mask, bit n = spell n (1..29)
    spell_slot: int = 0             # +0x1c brain +0x78: the selected special spell slot
    school_xp: tuple = (0, 0, 0, 0, 0)  # +0x20..+0x30 XP pools of schools 1..5 (hero +0x240..+0x250)

    def pack(self):
        plain = struct.pack("<5I4B2I5I", self.kills_monsters, self.kills_players, self.stat_a58, self.hero_deaths, self.gold,
                            *self.attributes, self.spells, self.spell_slot, *self.school_xp)
        return plain

    @classmethod
    def parse(cls, plain):
        v = struct.unpack("<5I4B2I5I", plain)
        return cls(v[0], v[1], v[2], v[3], v[4], tuple(v[5:9]), v[9], v[10], tuple(v[11:16]))

    @property
    def spell_ids(self):
        return [n for n in range(1, 30) if self.spells >> n & 1]


@dataclass
class Character:
    """A `.a2c` file: the chunks in file order (`order` lists the tags as found).  `layout` keeps per chunk the header flags and
    the junk bytes so that `build` reproduces a parsed file byte for byte."""
    identity: Identity = None
    stats: Stats = None
    settings: bytes = None          # chunk 0x55555555: 0xa00 bytes copied to player +0x44 (client UI settings, client +0x3f70)
    equipment: ItemPacket = None    # chunk 0xDE0DE0DE: 12 items in slot order
    pack: ItemPacket = None         # chunk 0x3A5A3A5A: the backpack
    settings_rle: bytes = None      # the stored RLE image of `settings`, kept so that `build_a2c` reproduces a parsed file
    hotkeys: bytes = None           # chunk 0x40A40A40: 9 records (u16, u16, u32 length, data), client +0x8c / +0x4dc
    order: list = field(default_factory=list)
    layout: dict = field(default_factory=dict)      # tag -> (flags, junk bytes, header length field)

    @property
    def template(self):
        return self.identity.template

    def hotkey_records(self):
        return parse_hotkeys(self.hotkeys) if self.hotkeys is not None else []


def parse_hotkeys(data, count=9):
    """Records of FUN_0041df0c / FUN_0041df74: `u16 a, u16 b, u32 length, length bytes`, 9 of them."""
    out, pos = [], 0
    for _ in range(count):
        a, b, n = struct.unpack_from("<HHI", data, pos)
        pos += 8
        out.append((a, b, bytes(data[pos:pos + n])))
        pos += n
    return out


def pack_hotkeys(records):
    return b"".join(struct.pack("<HHI", a, b, len(d)) + bytes(d) for a, b, d in records)


def parse_a2c(data):
    """FUN_004ee7cb: magic, then chunks (`tag u32, length u32, u16 0, u16 flags, u32 checksum`) up to the end of the file.
    Raises ValueError on a bad magic, an unknown tag or a checksum mismatch (the exe returns 0)."""
    data = bytes(data)
    if len(data) < 4 or struct.unpack_from("<I", data, 0)[0] != A2C_MAGIC:
        raise ValueError("not a character file (bad magic)")
    ch = Character()
    pos = 4
    while pos < len(data):
        tag, length, _zero, flags, csum = struct.unpack_from("<IIHHI", data, pos)
        pos += 16
        if tag == TAG_STATS:
            raw, junk, p = _read_stats(data, pos, flags)
            plain = _stats_decode(bytes(raw))
            if checksum(plain) != csum:
                raise ValueError("bad checksum in the stats chunk")
            ch.stats = Stats.parse(plain)
            ch.layout[tag] = (flags, bytes(junk), length)
            pos = p
        else:
            body = xor_stream(data[pos:pos + length], flags)
            if checksum(body) != csum:
                raise ValueError("bad checksum in chunk 0x%08x" % tag)
            pos += length
            if tag == TAG_ID:
                ch.identity = Identity.parse(body)
            elif tag == TAG_BLOB:
                ch.settings = rle_decode(body)
                ch.settings_rle = body
            elif tag == TAG_EQUIP:
                ch.equipment = ItemPacket.parse(body, fixed=EQUIP_SLOTS)
            elif tag == TAG_PACK:
                ch.pack = ItemPacket.parse(body)
            elif tag == TAG_HOTKEYS:
                ch.hotkeys = body
            else:
                raise ValueError("unknown chunk 0x%08x" % tag)
            ch.layout[tag] = (flags, b"", length)
        ch.order.append(tag)
    return ch


def _read_stats(data, pos, flags):
    """The stats chunk body: 13 words with an optional junk byte before field i when its flag bit is set (bit 0x2000 is
    used by both the word at +0x1c and the last pool word)."""
    plan = [(0x00, 4, 0x1), (0x04, 4, 0x2), (0x08, 4, 0x4), (0x0C, 4, 0x8), (0x10, 4, 0x10), (0x14, 1, 0x20), (0x15, 1, 0x40),
            (0x16, 1, 0x80), (0x17, 1, 0x100), (0x18, 4, 0x4000), (0x1C, 4, 0x2000)]
    plan += [(0x20 + 4 * i, 4, 0x200 << i) for i in range(5)]
    raw, junk = bytearray(), bytearray()
    for _off, size, bit in plan:
        if flags & bit:
            junk.append(data[pos])
            pos += 1
        raw += data[pos:pos + size]
        pos += size
    return raw, junk, pos


def build_a2c(ch, rng=None):
    """FUN_004edbaf for a whole file.  Chunks are written in `ch.order` (default: identity, stats, settings, equipment, pack,
    hotkeys as the exe writes them); header flags and junk come from `ch.layout` or, for a new chunk, from `rng`
    (a `random.Random`; the exe draws `rand(0x7fff)` and `rand(0xff)`)."""
    rng = rng or random.Random(0)
    order = ch.order or [t for t, v in ((TAG_ID, ch.identity), (TAG_STATS, ch.stats), (TAG_BLOB, ch.settings),
                                        (TAG_EQUIP, ch.equipment), (TAG_PACK, ch.pack), (TAG_HOTKEYS, ch.hotkeys))
                         if v is not None]
    out = bytearray(struct.pack("<I", A2C_MAGIC))
    for tag in order:
        flags, junk, _ = ch.layout.get(tag) or (rng.randrange(0x8000), None, None)
        if tag == TAG_STATS:
            plain = ch.stats.pack()
            stored = _stats_encode(plain)
            plan = [(0x00, 4, 0x1), (0x04, 4, 0x2), (0x08, 4, 0x4), (0x0C, 4, 0x8), (0x10, 4, 0x10), (0x14, 1, 0x20),
                    (0x15, 1, 0x40), (0x16, 1, 0x80), (0x17, 1, 0x100), (0x18, 4, 0x4000), (0x1C, 4, 0x2000)]
            plan += [(0x20 + 4 * i, 4, 0x200 << i) for i in range(5)]
            body, j = bytearray(), 0
            for off, size, bit in plan:
                if flags & bit:
                    body.append(junk[j] if junk is not None and j < len(junk) else rng.randrange(256))
                    j += 1
                body += stored[off:off + size]
            length = STATS_SIZE + sum(1 for i in range(16) if flags >> i & 1)
            out += struct.pack("<IIHHI", tag, length, 0, flags, checksum(plain)) + body
            continue
        if tag == TAG_ID:
            plain = ch.identity.pack()
        elif tag == TAG_BLOB:
            keep = ch.settings_rle is not None and rle_decode(ch.settings_rle) == ch.settings
            plain = ch.settings_rle if keep else rle_encode(ch.settings)
        elif tag == TAG_EQUIP:
            plain = ch.equipment.pack()
        elif tag == TAG_PACK:
            plain = ch.pack.pack()
        elif tag == TAG_HOTKEYS:
            plain = ch.hotkeys
        else:
            raise ValueError("unknown chunk 0x%08x" % tag)
        out += struct.pack("<IIHHI", tag, len(plain), 0, flags, checksum(plain)) + xor_stream(plain, flags)
    return bytes(out)


def load_a2c(path):
    with open(path, "rb") as f:
        return parse_a2c(f.read())


# --- famehall.dat -----------------------------------------------------------------------------------------------------


@dataclass
class HallEntry:
    """One entry of the hall of fame (FUN_004a91d5 / FUN_004a90c9): a CString (stored with its NUL) and three u32 values; the
    install's file sorts by the first value, descending (a score)."""
    name: str
    a: int
    b: int
    c: int


def parse_famehall(data):
    """`u32 count`, then per entry `u32 length` (name bytes with the NUL), the name, three u32.  Count 0 = the default hall."""
    data = bytes(data)
    n, = struct.unpack_from("<I", data, 0)
    pos, out = 4, []
    for _ in range(n):
        ln, = struct.unpack_from("<I", data, pos)
        pos += 4
        name = decode_text(data[pos:pos + ln].split(b"\0", 1)[0])
        pos += ln
        out.append(HallEntry(name, *struct.unpack_from("<3I", data, pos)))
        pos += 12
    if pos != len(data):
        raise ValueError("famehall.dat: %d trailing bytes" % (len(data) - pos))
    return out


def build_famehall(entries):
    out = bytearray(struct.pack("<I", len(entries)))
    for e in entries:
        nm = e.name.encode("cp1251") + b"\0"
        out += struct.pack("<I", len(nm)) + nm + struct.pack("<3I", e.a, e.b, e.c)
    return bytes(out)


# --- saved games (game%d.sav) -----------------------------------------------------------------------------------------

SAVE_MAGIC, SAVE_VERSION = 0x26677342, 0x0BAD0002
DESC_SIZE = 0x100
SCENARIO_VARS = 0x1000          # bytes of the Scenario.dll variable array written by ScenarioSave (1024 i32)
SCENARIO_SHOP = 16 * 0x14       # 4 towns x 4 blocks x 20 bytes
LOC_SIZE = 24                   # u32 index, u32 type (1 mission, 2 town), 16 name bytes


def _archive_string(data, pos):
    """MFC CArchive CString: length byte, 0xff + u16 for longer ones (the ANSI forms the exe writes)."""
    n = data[pos]
    pos += 1
    if n == 0xFF:
        n, = struct.unpack_from("<H", data, pos)
        pos += 2
    return decode_text(data[pos:pos + n]), pos + n


def _pack_archive_string(s):
    b = s.encode("cp1251")
    return bytes((len(b),)) + b if len(b) < 0xFF else b"\xff" + struct.pack("<H", len(b)) + b


SERVER_WORDS = ("w174", "w17c", "w180", "w184", "w188", "w18c", "w190", "w194", "w1a0", "w19c", "w198", "scenario", "difficulty")


@dataclass
class ServerHead:
    """The first fields of the server stream (FUN_004ec732, the decompressed block of the save), in stream order.
    `tick` is server `+4`, `block` server `+0`: a loaded game resumes with both counters exactly as stored.  `map_name` is
    server `+0x90` (the map the loader starts), the 13 words are server `+0x174, +0x17c, +0x180, +0x184, +0x188, +0x18c,
    +0x190, +0x194, +0x1a0, +0x19c, +0x198`, then `scenario` (`+0xd4`, nonzero adds "Scenario\\"-prefixed text at load)
    and `difficulty` (`+0xd8`, applied only when 1..3).  `rest` is the unparsed remainder (players, creatures, maps,
    script state: docs/formats/saves.md)."""
    tick: int
    block: int
    map_name: str
    words: tuple
    rest: bytes

    def pack(self):
        return (struct.pack("<II", self.tick, self.block) + _pack_archive_string(self.map_name)
                + struct.pack("<13I", *self.words) + self.rest)

    @classmethod
    def parse(cls, stream):
        tick, block = struct.unpack_from("<II", stream, 0)
        name, pos = _archive_string(stream, 8)
        words = struct.unpack_from("<13I", stream, pos)
        return cls(tick, block, name, words, bytes(stream[pos + 52:]))

    @property
    def scenario(self):
        return self.words[11]

    @property
    def difficulty(self):
        return self.words[12]


@dataclass
class ScenarioState:
    """What ScenarioSave writes (Scenario.dll `0x10003585`): the variable array, the shop table and the location list."""
    variables: tuple = (0,) * (SCENARIO_VARS // 4)      # 1024 i32 (docs/engine/triggers.md: scripts use the first 1000)
    shops: bytes = bytes(SCENARIO_SHOP)                 # 4 towns x 4 blocks x (min, max, count, stack, flags) u32
    locations: list = field(default_factory=list)       # (index, type, name16) in list order
    current: int = 0                                    # position of the current location in the list

    def pack(self):
        out = struct.pack("<1024i", *self.variables) + self.shops + struct.pack("<I", len(self.locations))
        for index, typ, name in self.locations:
            out += struct.pack("<II", index, typ) + name.ljust(16, b"\0")[:16]
        return out + struct.pack("<I", self.current)

    @classmethod
    def parse(cls, data, pos=0):
        """Returns (ScenarioState, next position)."""
        v = struct.unpack_from("<1024i", data, pos)
        pos += SCENARIO_VARS
        shops = bytes(data[pos:pos + SCENARIO_SHOP])
        pos += SCENARIO_SHOP
        n, = struct.unpack_from("<I", data, pos)
        pos += 4
        locs = []
        for _ in range(n):
            index, typ = struct.unpack_from("<II", data, pos)
            locs.append((index, typ, bytes(data[pos + 8:pos + 24])))
            pos += LOC_SIZE
        cur, = struct.unpack_from("<I", data, pos)
        return cls(v, shops, locs, cur), pos + 4


@dataclass
class ClientTail:
    """The client part appended to the server block (FUN_0048dc9f): the 0x100-byte slot description, the `.reg` tree, the
    mission list (client `+0x598`, FUN_004a8f96), the Scenario.dll block and nine hotkey records."""
    description: str
    reg: object                     # allods2.reg.Registry
    reg_bytes: bytes
    missions: list                  # (u32, u32) records
    mission_tail: tuple             # the two u32 of the object (`+4`, `+8`)
    scenario: ScenarioState
    hotkeys: list                   # 9 x (u16, u16, bytes)


def reg_length(data, pos=0):
    """Size of the `.reg` image starting at `pos`: 0x18 + 32 N + 4 + D (docs/formats/reg.md)."""
    n, = struct.unpack_from("<I", data, pos + 0x10)
    size, = struct.unpack_from("<I", data, pos + REG_HEADER + REG_ENTRY * n)
    return REG_HEADER + REG_ENTRY * n + 4 + size


def parse_tail(data, pos):
    desc = decode_text(bytes(data[pos:pos + DESC_SIZE]).split(b"\0", 1)[0])
    pos += DESC_SIZE
    n = reg_length(data, pos)
    reg_bytes = bytes(data[pos:pos + n])
    reg = parse_reg(reg_bytes, "save")
    pos += n
    cnt, = struct.unpack_from("<I", data, pos)
    pos += 4
    missions = [struct.unpack_from("<II", data, pos + 8 * i) for i in range(cnt)]
    pos += 8 * cnt
    tail = struct.unpack_from("<II", data, pos)
    pos += 8
    scenario, pos = ScenarioState.parse(data, pos)
    hot = []
    for _ in range(9):
        a, b, ln = struct.unpack_from("<HHI", data, pos)
        pos += 8
        hot.append((a, b, bytes(data[pos:pos + ln])))
        pos += ln
    if pos != len(data):
        raise ValueError("saved game: %d trailing bytes after the client block" % (len(data) - pos))
    return ClientTail(desc, reg, reg_bytes, missions, tail, scenario, hot)


def pack_tail(t):
    out = t.description.encode("cp1251")[:DESC_SIZE - 1].ljust(DESC_SIZE, b"\0") + t.reg_bytes
    out += struct.pack("<I", len(t.missions)) + b"".join(struct.pack("<II", *m) for m in t.missions) + struct.pack("<II", *t.mission_tail)
    return out + t.scenario.pack() + pack_hotkeys(t.hotkeys)


@dataclass
class SaveGame:
    """`game%d.sav`: `u32 0x26677342, u32 end of the server block, u32 version 0x0BAD0002, u32 length`, the word-RLE stream
    (`stream` = the decompressed bytes), then the client tail.  A multiplayer save has 0x100 more bytes after the server block
    (not handled)."""
    stream: bytes
    tail: ClientTail
    version: int = SAVE_VERSION

    @property
    def head(self):
        return ServerHead.parse(self.stream)

    def pack(self):
        comp = rle_encode(self.stream + (b"\0" if len(self.stream) & 1 else b""), unit=2)
        return (struct.pack("<IIII", SAVE_MAGIC, 16 + len(comp), self.version, len(comp)) + comp + pack_tail(self.tail))


def parse_save(data):
    """FUN_004e9b95 (server block) + the client reader FUN_0048c2e9.  Raises ValueError for "Invalid save file" (bad magic)
    and "Outdated save file" (version below 0x0BAD0002)."""
    data = bytes(data)
    magic, end, version, ln = struct.unpack_from("<IIII", data, 0)
    if magic != SAVE_MAGIC:
        raise ValueError("Invalid save file")
    if version < SAVE_VERSION:
        raise ValueError("Outdated save file")
    stream = rle_decode(data[16:16 + ln], unit=2)
    if end != 16 + ln:
        raise ValueError("server block ends at 0x%x, header says 0x%x" % (16 + ln, end))
    return SaveGame(stream, parse_tail(data, end), version)
