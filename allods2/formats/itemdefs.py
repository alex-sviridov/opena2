"""Item definitions: weapons, shields, armour and special items of data.bin, with the exe's
quality/material scaling, price and modifier rules.

Spec: docs/data/items.md.  Nothing is copied out of the game: the table is built from the install's
data.bin (and itemname.bin/.txt for display names) on load.  Raw class params are kept in `raw`
(-1 = "not set": the exe keeps its default).  Rounding follows the exe: `__ftol` truncates, and
most scaled values add 0.5 first (see `scaled`).
"""

import math
import re
import struct
from dataclasses import asdict, dataclass

from ..common import as_fs
from ..databin import databin
from ..text import decode_text
from .entities import ItemCode, decode_item

WEAPON, SHIELD, ARMOUR, SPECIAL = "weapon", "shield", "armour", "special"
KINDS = (WEAPON, SHIELD, ARMOUR, SPECIAL)
GROUP = {WEAPON: "weapons", SHIELD: "shields", ARMOUR: "armour", SPECIAL: "items"}
CLASS_OF = {WEAPON: 1, SHIELD: 2, SPECIAL: 14}          # armour: the record's Slot

# data.bin class params by index (columns of databin.md); P is the index into `raw`.
CLASS_FIELDS = ("shape", "material", "price", "weight", "slot", "attack_type", "damage_min",
                "damage_max", "to_hit", "defence", "absorption", "range", "windup", "recovery",
                "two_handed", "suitable_for", "other")
P = {n: i for i, n in enumerate(CLASS_FIELDS)}
# Factor (quality / material) f64 indices: record +0x30 + 8k (FUN_00528c92, FUN_0052765b).
F_PRICE, F_WEIGHT, F_DAMAGE, F_TOHIT, F_DEFENCE, F_ABSORPTION, F_LEVEL = range(7)

STAT_PRICE, STAT_CAST, STAT_TEACH, STAT_DAMAGE, STAT_DAMAGE_BONUS = 1, 41, 42, 43, 49
ELEMENT_DAMAGE = (44, 45, 46, 47, 48)                   # damageFire .. damageAstral: (min, spread)
PRICE_CAP = 0x1312CFF                                   # 19,999,999, FUN_00528e04
FIGHTER, MAGE = 1, 2                                    # `suitable_for` / stat `UsableBy` bits
MODE_PERMANENT, MODE_DURATION, MODE_CONTINUOUS, MODE_CHARGES, MODE_SINGLE_USE = 0, 1, 2, 4, 8
DEFAULT_QUALITY, DEFAULT_MATERIAL = 0, 15                  # equipment strings without a name part
SUBTYPE = (("Potion", 3), ("Book", 5), ("Scroll", 4), ("SuperScroll", 4))   # name prefix, FUN_00523148


def effects_from_mods(mods):
    """Wire modifier records `(kind, a, b)` (`saves.Item.mods`) -> effects: castSpell `(41, spell, charges)`, elemental damage `(44..48, min, spread)`,
    any other kind `(kind, value)` (`FUN_004ed5f5`: the value byte lands in the word `+0x40`, flags 0 = permanent)."""
    out = []
    for kind, a, b in mods:
        if kind == STAT_CAST:
            out.append(Effect(kind, a, 0, b))
        elif kind in ELEMENT_DAMAGE:
            out.append(Effect(kind, a, b))
        else:
            out.append(Effect(kind, a))
    return tuple(out)


def mods_from_effects(effects):
    """The inverse (`FUN_005241bf`: the price modifier, kind 1, is not written)."""
    out = []
    for e in effects:
        if e.kind == 1:
            continue
        if e.kind == STAT_CAST:
            out.append((e.kind, e.value, e.count))
        elif e.kind in ELEMENT_DAMAGE:
            out.append((e.kind, e.value, e.spread))
        else:
            out.append((e.kind, e.value, 0))
    return tuple(out)


def ftol(x):
    """The exe's `__ftol`: truncation toward zero."""
    return int(x)


def scaled(param, quality, material, k, half=True):
    """`param x material.f64[k] x quality.f64[k]`, +0.5 first when `half` (FUN_00528c92 and kin)."""
    x = param * material[k] * quality[k]
    return ftol(x + 0.5) if half else ftol(x)


@dataclass(frozen=True)
class StatDef:
    """One row of the data.bin `stats` group (the modifier / enchantment table)."""
    id: int
    name: str
    cost: int              # cost.MP, price weight per point (FUN_0051e318)
    affect_min: int        # affectMin: smallest generated magnitude
    affect_max: int        # affectMax: largest generated magnitude
    usable_by: int         # UsableBy: bit 1 fighters, bit 2 mages (FUN_0052397e)
    slot_weights: tuple    # 24 cumulative `in.<slot>` columns: 12 fighter slots, 12 mage slots


@dataclass(frozen=True)
class Effect:
    """One modifier of an item: section 9 pair, `{...}` equipment text term or special-item text.

    kind   data.bin stat index (effect `+0x3c`); value `+0x40` (castSpell/teachSpell: spell id,
           `count` = charges `+0x42`; damage kinds 44-48: (value, spread) = bytes `+0x40`, `+0x41`)."""
    kind: int
    value: int = 0
    spread: int = 0
    count: int = 0
    mode: int = MODE_PERMANENT
    time: int = 0


@dataclass(frozen=True)
class ItemDef:
    """One data.bin item record.

    kind     "weapon" (code class 1), "shield" (2), "armour" (3-13), "special" (14)
    cls      item code class: 1, 2, the armour `Slot`, 14
    index    1-based record index (the code's index field)
    fields   class params by `CLASS_FIELDS` (special: price, weight)
    masks    7 u16, one per quality: bit m = material m may be made of (classes only)
    flag     special-item byte (always 1); effects_text the special-item modifier text
    raw      all params in file order
    """
    kind: str
    cls: int
    index: int
    name: str
    price: int
    weight: int
    fields: dict
    masks: tuple = ()
    flag: int = 0
    effects_text: str = ""
    raw: tuple = ()

    def __getattr__(self, key):
        try:
            return self.__dict__["fields"][key]
        except KeyError:
            raise AttributeError(key) from None

    @property
    def subtype(self):
        """Special items: 3 potion, 4 scroll / super scroll, 5 book, 0 other (name prefix)."""
        for prefix, v in SUBTYPE:
            if self.name.startswith(prefix):
                return v
        return 0

    def allows(self, quality, material):
        """May this class be made in `quality` of `material` (FUN_005247db)?"""
        return bool(self.masks and (self.masks[quality] & 0xFFFF) >> material & 1)

    def can_use(self, mage):
        """Fighters need `suitable_for` bit 1, mages bit 2 (FUN_00512573)."""
        return bool(self.fields.get("suitable_for", 0) & (MAGE if mage else FIGHTER))

    def to_dict(self):
        d = {"kind": self.kind, "cls": self.cls, "index": self.index, "name": self.name,
             "price": self.price, "weight": self.weight, "fields": dict(self.fields)}
        if self.kind == SPECIAL:
            d.update(flag=self.flag, effects=self.effects_text)
        else:
            d["masks"] = list(self.masks)
        return d


@dataclass(frozen=True)
class ItemStats:
    """The values the exe computes when it creates a class item (quality/material applied)."""
    price: int             # item +0x1c, base price before modifiers
    weight: int            # +0x4a
    magic_cap: int         # +0x48: truncated quality.f64[6] x material.f64[6]
    damage_min: int = 0    # weapons +0x64
    damage_spread: int = 0  # +0x65 (= max - min)
    to_hit: int = 0        # weapons +0x56
    defence: int = 0       # weapons +0x6e, shields +0x54, armour +0x56
    absorption: int = 0    # shields +0x56, armour +0x58 (truncated, not rounded)
    range: int = 1         # weapons +0x54 (-1 -> 1)


@dataclass(frozen=True)
class Item:
    """A resolved item code (+ optional section 9 effects)."""
    defn: ItemDef
    quality: int
    material: int
    stats: ItemStats
    effects: tuple = ()
    price: int = 0         # base price with the effects (`price_with_effects`)


def spell_name_key(name):
    return name.lower().replace(" ", "_")


class ItemTable:
    """All item definitions plus the factor, stat and spell tables the rules need."""

    def __init__(self, defs, qualities=(), materials=(), stats=(), spells=(), names=None):
        self.defs = tuple(defs)
        self.qualities = tuple(qualities)          # (name, 7 f64) each
        self.materials = tuple(materials)
        self.stats = tuple(stats)                  # StatDef, index = stat id (0 = empty)
        self.spells = tuple(spells)                # (name, scrollCost, bookCost), 1-based id = position + 1
        self.names = dict(names or {})             # item code -> display name (itemname.bin / .txt)
        self._by = {(d.kind, d.index): d for d in self.defs}

    def __len__(self):
        return len(self.defs)

    def __iter__(self):
        return iter(self.defs)

    def of_kind(self, kind):
        return [d for d in self.defs if d.kind == kind]

    def get(self, kind, index):
        return self._by.get((kind, index))

    def lookup(self, code):
        """The `ItemDef` of an item code (`entities.decode_item` semantics), or None (class 0/15,
        index outside the list, or an unused placeholder record)."""
        ic = decode_item(code) if isinstance(code, int) else code
        return self._by.get((ic.kind, ic.index)) if ic else None

    # -- factors ---------------------------------------------------------------------------------

    def factors(self, quality, material):
        return self.qualities[quality][1], self.materials[material][1]

    def class_stats(self, defn, quality, material):
        """`ItemStats` of a class record at (quality, material): FUN_00528c92 (weapons),
        FUN_0052765b (armour), FUN_0052810d (shields)."""
        q, m = self.factors(quality, material)
        f = defn.fields
        s = lambda name, k, half=True: scaled(f[name], q, m, k, half)
        base = dict(price=s("price", F_PRICE), weight=s("weight", F_WEIGHT),
                    magic_cap=ftol(q[F_LEVEL] * m[F_LEVEL]))
        if defn.kind == WEAPON:
            dmin = s("damage_min", F_DAMAGE)
            return ItemStats(damage_min=dmin, damage_spread=ftol(f["damage_max"] * m[F_DAMAGE] * q[F_DAMAGE]
                                                                - dmin + 0.5),
                             to_hit=s("to_hit", F_TOHIT), defence=s("defence", F_DEFENCE),
                             range=1 if f["range"] == -1 else f["range"], **base)
        return ItemStats(defence=s("defence", F_DEFENCE), absorption=s("absorption", F_ABSORPTION, False), **base)

    def resolve(self, code, effects=()):
        """`Item` of an item code; `effects` (section 9 pairs as `Effect`s) change the price."""
        ic = decode_item(code) if isinstance(code, int) else code
        d = self.lookup(ic)
        if d is None:
            return None
        if d.kind == SPECIAL:
            st = ItemStats(price=d.price, weight=d.weight, magic_cap=0)
            return Item(d, 0, 0, st, tuple(effects), self.special_price(d, effects))
        st = self.class_stats(d, ic.quality, ic.material)
        return Item(d, ic.quality, ic.material, st, tuple(effects), self.price_with_effects(st.price, effects))

    # -- price -----------------------------------------------------------------------------------

    def effect_cost(self, e):
        """Price weight of one effect (FUN_0051e318); castSpell is priced by `spell_price`."""
        if e.kind == 0:
            return 0
        cost = self.stats[e.kind].cost
        if e.kind == STAT_CAST:
            return e.count * cost
        if e.kind in ELEMENT_DAMAGE:
            return (e.value + e.spread) * cost
        return e.value * cost

    def spell_price(self, e):
        """Price of a castSpell effect of `count` charges (vtable +0x4c of the effect, 0x51f48d):
        `scrollCost x 10 x 2^(log_1.2(count / 30 + 1))`."""
        if e.kind != STAT_CAST:
            return 0
        return ftol(self.spells[e.value - 1][1] * 10 * 2 ** (math.log(e.count / 30 + 1) / math.log(1.2)))

    def price_with_effects(self, base, effects):
        """Class-item price with its modifiers (FUN_00528e04, FUN_00527862): a price effect (kind 1)
        replaces everything; castSpell adds `spell_price`; the rest is summed to `s` and adds
        `(1.5^(s/70) + 1) x s x 50` (FUN_0051e41a); capped at 19,999,999."""
        price, total = base, 0
        for e in effects:
            if e.kind == STAT_PRICE:
                return e.value
            if e.kind == STAT_CAST:
                price += self.spell_price(e)
            else:
                total += self.effect_cost(e)
        try:
            price += ftol((1.5 ** (total / 70) + 1) * total * 50) if total else 0
        except OverflowError:                       # pow overflows: far above the cap
            return PRICE_CAP
        return min(price, PRICE_CAP)

    def special_price(self, d, effects=()):
        """Special items (FUN_0052340f): the record price; books use the `bookCost` of their
        teachSpell effect (0 without one)."""
        if d.subtype == 5:
            for e in effects:
                if e.kind == STAT_TEACH:
                    return self.spells[e.value - 1][2]
            return 0
        return d.price

    # -- modifiers -------------------------------------------------------------------------------

    def stat_id(self, name):
        """Effect kind of a stat name, case-insensitive (FUN_0051e8fa); 0 if unknown."""
        low = name.strip().lower()
        for s in self.stats:
            if s.id and s.name.lower() == low:
                return s.id
        return 0

    def spell_id(self, name):
        """1-based spell id of `Fire_Arrow` / `Fire Arrow` (FUN_0051f1c3), -1 if unknown."""
        key = spell_name_key(name.strip())
        for i, (n, _, _) in enumerate(self.spells, 1):
            if n and spell_name_key(n) == key:
                return i
        return -1

    def parse_effects(self, text):
        """Effects of modifier text `name=value[:time],...` (FUN_0051e78e / FUN_0051e8fa).  Terms
        with an unknown stat name or spell are skipped, as the exe discards them."""
        out = []
        for term in text.split(","):
            if "=" not in term:
                continue
            name, rest = term.split("=", 1)
            kind = self.stat_id(name)
            if not kind:
                continue
            val, _, tail = rest.partition(":")
            mode, n = time_part(tail)
            if kind in (STAT_CAST, STAT_TEACH):
                sid = self.spell_id(val)
                if sid < 0:
                    continue
                count = int_prefix(tail) if kind == STAT_CAST else 0
                out.append(Effect(kind, sid, 0, count))
            elif kind in (STAT_DAMAGE,) + ELEMENT_DAMAGE and "-" in val[1:]:
                lo, hi = val.split("-", 1)
                lo = int_prefix(lo)
                out.append(Effect(kind, lo, int_prefix(hi) - lo, 0, mode, n << 4 if mode else 0))
            else:
                out.append(Effect(kind, int_prefix(val), 0, 0, mode, n << 4 if mode & 7 else 0))
        return out

    def pair_effects(self, props, spell=0, count=0, book=False):
        """Effects of a section 9 record: `props` = (stat id, value) pairs (id 41 is remapped to 49,
        FUN_00564072), `spell`/`count` the record's `c` field (castSpell, teachSpell for books)."""
        out = []
        if spell:
            out.append(Effect(STAT_TEACH if book else STAT_CAST, spell, 0, count))
        for sid, value in props:
            out.append(Effect(STAT_DAMAGE_BONUS if sid == STAT_CAST else sid, value))
        return out

    def slot_weights(self, slot, mage):
        """Relative chance of each stat as a random enchantment of `slot` (1-12) for the fighter
        (`mage` False) or mage set: differences of the cumulative `in.<slot>` columns
        (FUN_00526ec4).  {stat id: weight}"""
        col = slot - 1 + (12 if mage else 0)
        out, prev = {}, 0
        for s in self.stats[1:]:
            w = s.slot_weights[col] - prev
            prev = s.slot_weights[col]
            if s.name and w > 0:
                out[s.id] = w
        return out

    # -- names, icons ------------------------------------------------------------------------------

    def name_of(self, code):
        """Display name of an item code (itemname.bin / .txt), or None."""
        return self.names.get(code & 0xFFFF)

    def display_name(self, code, effects=(), spell_names=None, of="of", tail=""):
        """Name shown for an item (tooltip builder 0x43901f): the `itemname.txt` name, then for every
        teachSpell effect, and for every castSpell effect of a special item (class 14), the text
        `" %s %s%s" % (of, spell name, tail)`: `Scroll of Fire Arrow`, `Book of Haste`.  `of` / `tail`
        are the interface texts 0x5a / 0x5b (`main.txt`: "of", ""), `spell_names` the lines of `spell.txt`
        (line k = spell k + 1; default: the data.bin spell names).  castSpell of other classes is a
        separate tooltip line ("casts X"), not part of the name.  None for an unknown code."""
        name = self.names.get(code & 0xFFFF)
        if name is None:
            return None
        special = (code >> 8) & 15 == 14
        for e in effects:
            if e.kind == STAT_TEACH or (e.kind == STAT_CAST and special):
                sp = spell_names[e.value - 1] if spell_names else self.spells[e.value - 1][0]
                name += " %s %s%s" % (of, sp, tail)
        return name

    def parse_equipment(self, text, slot=None):
        """Resolve an equipment string `[Quality] [Material] Class{terms}` of a monster / human
        record: returns (ItemCode, effects) or None.  `slot` is the human equipment slot (0 weapon,
        1 shield, 2-9 armour; None: search weapons, shields, armour).  The exe cuts the `{...}` modifier
        text, takes the last quality and material whose name occurs in the text (defaults Common /
        None) and removes them; armour and shields then get the prefix `Soft ` when the material name
        contains `Leather`, else `Wooden ` when it contains `Wood`; shields cut ` Shield`; the rest is
        looked up by name from the end of the class list (FUN_00528808, FUN_005273f0, FUN_00527e23,
        FUN_004fa437, FUN_004fa583, FUN_004fa6c6, FUN_004fa7e1)."""
        body, _, mods = text.partition("{")
        body = " ".join(body.split())
        picked = []
        for table, default in ((self.qualities, DEFAULT_QUALITY), (self.materials, DEFAULT_MATERIAL)):
            idx = default
            for i in range(len(table) - 1, -1, -1):
                pat = r"(?<!\S)%s(?!\S)" % re.escape(table[i][0])
                if re.search(pat, body, re.I):
                    idx = i
                    body = " ".join(re.sub(pat, " ", body, count=1, flags=re.I).split())
                    break
            picked.append(idx)
        quality, material = picked
        kinds = (WEAPON, SHIELD, ARMOUR) if slot is None else ((WEAPON,), (SHIELD,), (ARMOUR,))[min(slot, 2)]
        for kind in kinds:
            name = body
            if kind != WEAPON:
                mname = self.materials[material][0]
                name = ("Soft " if "Leather" in mname else "Wooden " if "Wood" in mname else "") + name
            if kind == SHIELD:
                name = name.replace(" Shield", "", 1)
            for d in reversed(self.of_kind(kind)):
                if d.name.lower() == name.lower():
                    return ItemCode(kind, d.cls, d.index, quality, material), self.parse_effects(mods.rstrip("}"))
        return None

    def to_dict(self):
        return {"items": [d.to_dict() for d in self.defs],
                "qualities": [[n, list(f)] for n, f in self.qualities],
                "materials": [[n, list(f)] for n, f in self.materials],
                "stats": [{**asdict(s), "slot_weights": list(s.slot_weights)} for s in self.stats if s.id],
                "names": {"%04x" % c: n for c, n in sorted(self.names.items())}}


def int_prefix(s):
    """Leading signed integer of `s` (0 if none), like the exe's sscanf of FUN_0051f20a."""
    m = re.match(r"\s*([+-]?\d+)", s)
    return int(m.group(1)) if m else 0


def time_part(tail):
    """(mode, N) of the part after ':' (FUN_0051f29c): permanent 0, singleuse 8, `charges N` 4,
    `duration N` 1, `continuous N` 2; a bare number (castSpell charges) or nothing: (0, 0)."""
    t = tail.strip().lower()
    if t == "singleuse":
        return MODE_SINGLE_USE, 0
    for word, mode in (("charges", MODE_CHARGES), ("duration", MODE_DURATION), ("continuous", MODE_CONTINUOUS)):
        if word in t:
            return mode, int_prefix(t.split(word, 1)[1])
    return MODE_PERMANENT, 0


def icon_path(code):
    """Inventory icon of an item code (FUN_00438ba1): `graphics/inventory/` + `%02d%02d%1d%02d` of
    (material, class, quality, index) + `.16a`; special items `%02d%02d%03d` of (material, 14, code & 0xFF)."""
    code &= 0xFFFF
    if (code >> 8) & 15 == 14:
        return "graphics/inventory/%02d%02d%03d.16a" % (code >> 12, 14, code & 0xFF)
    return "graphics/inventory/%02d%02d%d%02d.16a" % (code >> 12, (code >> 8) & 15, (code >> 5) & 7, code & 31)


def scroll_packet_price(scroll_cost, charges):
    """Price in itemname.pkt of a scroll (INFERRED; fits all 58): `scrollCost x 2^(log_1.2(charges / 30
    + 1)) / 50`, truncated."""
    return ftol(scroll_cost * 10 * 2 ** (math.log(charges / 30 + 1) / math.log(1.2)) / 500)


@dataclass(frozen=True)
class Packet:
    """One itemname.pkt record: the item as the client receives it (INFERRED layout)."""
    code: int
    header: bytes          # 4 bytes after the code (version 1, 0, two unknown)
    price: int             # u32 at payload +1
    pairs: tuple           # (stat id, value) bytes after the price (specials: after the 0x33 0x00 marker)
    payload: bytes


def parse_packets(data):
    """itemname.pkt: 9 header bytes (u32 0, u32 count-ish, u8), then records `u16 code, 4 bytes, u8 n,
    n payload bytes` (stride 7 + n, FUN_00474268) that tile the file."""
    out, pos = [], 9
    while pos < len(data):
        n = data[pos + 6]
        pl = bytes(data[pos + 7:pos + 7 + n])
        if len(pl) != n:
            raise ValueError("itemname.pkt truncated at %d" % pos)
        price = struct.unpack_from("<I", pl, 1)[0] if n >= 5 else 0
        body = pl[7:] if len(pl) > 5 and pl[5] == 0x33 else pl[5:]
        pairs = tuple((body[j], body[j + 1]) for j in range(0, len(body) - 1, 2))
        out.append(Packet(struct.unpack_from("<H", data, pos)[0], bytes(data[pos + 2:pos + 6]), price, pairs, pl))
        pos += 7 + n
    return out


def build(db, names=None):
    """ItemTable of a DataBin.  Records without a name or with the editor placeholder `rem` stay (their
    params are -1); special items have price and weight only."""
    defs = []
    for kind in (WEAPON, SHIELD, ARMOUR):
        for i, rec in enumerate(getattr(db, GROUP[kind]), 1):
            f = dict(zip(CLASS_FIELDS, rec.params))
            cls = CLASS_OF.get(kind) or f["slot"]
            defs.append(ItemDef(kind, cls, i, rec.name, f["price"], f["weight"], f,
                                tuple(rec.extra[0]), 0, "", tuple(rec.params)))
    for i, rec in enumerate(db.items, 1):
        flag, text = rec.extra
        defs.append(ItemDef(SPECIAL, 14, i, rec.name, rec.params[0], rec.params[1],
                            {"price": rec.params[0], "weight": rec.params[1]}, (), flag, text, tuple(rec.params)))
    stats = [StatDef(i, r.name, r.params[0], r.params[1], r.params[2], r.params[3], tuple(r.params[4:28]))
             for i, r in enumerate(db.stats)]
    spells = [(r.name, r.params[20], r.params[21]) if r.params else ("", 0, 0) for r in db.spells]
    return ItemTable(defs, [(r.name, tuple(r.doubles)) for r in db.qualities],
                     [(r.name, tuple(r.doubles)) for r in db.materials], stats, spells, names)


def load_names(fs):
    """{item code: display name} from itemname.bin (u16 codes) and main/text/itemname.txt (one name
    per line, the same order; FUN_00474268 pairs them), {} when a file is missing."""
    try:
        bin_ = bytes(fs.read("world/data/itemname.bin"))
        txt = decode_text(fs.read("main/text/itemname.txt")).split("\r\n")
    except (OSError, KeyError, FileNotFoundError):
        return {}
    codes = struct.unpack("<%dH" % (len(bin_) // 2), bin_)
    return {c: txt[i] for i, c in enumerate(codes) if i < len(txt)}


def load_ui_texts(fs=None):
    """(of, tail, spell_names) for `ItemTable.display_name`: `main/text/main.txt` lines 0x5a and 0x5b
    (text list at 0x622600, FUN_00481186) and `main/text/spell.txt` (list 0x6226e0); ("of", "", []) defaults."""
    fs = as_fs(fs)
    try:
        main = decode_text(fs.read("main/text/main.txt")).split("\r\n")
        spell = decode_text(fs.read("main/text/spell.txt")).split("\r\n")
    except (OSError, KeyError, FileNotFoundError):
        return "of", "", []
    return main[0x5A], main[0x5B], spell


def load(fs=None):
    """The item table of an install (`fs`: game file system), display names included."""
    fs = as_fs(fs)
    return build(databin(fs), load_names(fs))


def load_packets(fs=None):
    return parse_packets(bytes(as_fs(fs).read("world/data/itemname.pkt")))
