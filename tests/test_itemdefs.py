"""Tests for docs/data/items.md (allods2.formats.itemdefs)."""

import hashlib
import importlib.util
import json
import math
import os
import struct

import pytest

from allods2 import databin as D
from allods2.common import campaign_maps
from allods2.formats import Map
from allods2.formats import itemdefs as I
from allods2.formats.entities import decode_item

from helpers import GFS, needs

needs_databin = needs("world", "data", "data.bin")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- synthetic table --------------------------------------------------------------------------

#                 price weight dmg  toHit def  abs  level
COMMON = D.Factor("Common", bytes(16), (1.0, 1.0, 0.2, 1.0, 0.25, 1.0, 1.0))
RARE = D.Factor("Rare", bytes(16), (4.0, 1.2, 0.288, 1.44, 0.36, 1.21, 3.0))
VRARE = D.Factor("Very Rare", bytes(16), (10.0, 1.3, 0.3456, 1.728, 0.432, 1.331, 4.0))
IRON = D.Factor("Iron", bytes(16), (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0))
BRONZE = D.Factor("Bronze", bytes(16), (0.25, 0.5, 0.694, 1.0, 0.694, 1.0, 3.0))
LEATHER = D.Factor("Leather", bytes(16), (0.0078, 0.2, 0.279, 1.0, 0.279, 1.0, 0.0))
HLEATHER = D.Factor("Hard Leather", bytes(16), (0.125, 0.4, 0.578, 1.0, 0.578, 1.0, 1.0))
WOOD = D.Factor("Wood", bytes(16), (0.1667, 0.5, 0.624, 1.0, 0.624, 1.0, 20.0))
MWOOD = D.Factor("Magic Wood", bytes(16), (6.0, 0.7, 1.6, 2.0, 1.6, 1.28, 150.0))
NONE = D.Factor("None", bytes(16), (1.0, 0.2, 0.48, 1.0, 0.48, 1.0, 150.0))


def cls_params(**kw):
    p = dict(shape=0, material=0, price=0, weight=0, slot=1, attack_type=-1, damage_min=0, damage_max=0,
             to_hit=0, defence=0, absorption=0, range=-1, windup=-1, recovery=-1, two_handed=-1,
             suitable_for=1, other=-1)
    p.update(kw)
    return [p[n] for n in I.CLASS_FIELDS]


def stat(name, cost=1, lo=0, hi=0, usable=3, weights=None):
    return D.Record(name, [cost, lo, hi, usable] + (weights or [0] * 24))


def synthetic_db():
    db = D.DataBin()
    db.qualities = [COMMON, RARE, VRARE]
    db.materials = [IRON, BRONZE, LEATHER, HLEATHER, WOOD, MWOOD] + [NONE] * 10
    db.materials[15] = NONE
    names = ["", "price", "body", "mind", "reaction", "spirit", "health"] + ["s%d" % i for i in range(7, 41)] \
        + ["castSpell", "teachSpell", "damage", "damageFire", "damageWater", "damageAir", "damageEarth",
           "damageAstral", "damageBonus"]
    db.stats = [D.Record(n, [0] * 28) for n in names]
    db.stats[1] = stat("price", 0)
    db.stats[2] = stat("body", 150, 1, 5, 3)
    db.stats[6] = stat("health", 10, 50, 50, 1)
    db.stats[41] = stat("castSpell", 1)
    db.stats[44] = stat("damageFire", 15)
    db.stats[49] = stat("damageBonus", 20)
    # cumulative in.<slot> columns: stats 2 and 6 weigh 10 and 5 in slot 1 (fighter set), only 6 weighs 4 in
    # slot 1 of the mage set
    for i in range(2, 50):
        db.stats[i].params[4] = 10 if i < 6 else 15
        db.stats[i].params[16] = 0 if i < 6 else 4
    db.weapons = [
        D.Record("BareHands", cls_params(price=0), ((0,) * 7, [])),
        D.Record("Long Sword", cls_params(price=600, weight=20, attack_type=1, damage_min=28, damage_max=56,
                                           to_hit=3, windup=7, recovery=4),
                 ((3, 6, 96, 0, 0, 0, 0), [])),
        D.Record("Staff", cls_params(price=1000, weight=10, damage_min=0, damage_max=0, range=6, two_handed=2,
                                     suitable_for=2), ((256, 0, 0, 0, 0, 0, 0), []))]
    db.shields = [D.Record("Soft Small", cls_params(slot=2, price=350, weight=20, defence=49, absorption=1,
                                                    suitable_for=1), ((0,) * 7, [])),
                  D.Record("Small", cls_params(slot=2, price=450, weight=20, defence=49, absorption=1),
                           ((0,) * 7, [])),
                  D.Record("Wooden Large", cls_params(slot=2, price=1050), ((0,) * 7, []))]
    db.armour = [D.Record("Ring", cls_params(slot=4, price=50, weight=3, defence=2, suitable_for=3), ((0,) * 7, [])),
                 D.Record("Soft Boots", cls_params(slot=12, price=100, weight=15, defence=21, absorption=1),
                          ((0,) * 7, [])),
                 D.Record("Plate Cuirass", cls_params(slot=8, price=700, weight=100, defence=46, absorption=2),
                          ((0,) * 7, []))]
    db.items = [D.Record("Book Fire", [1, 10], (1, "")), D.Record("Scroll Fire Arrow", [100, 1], (1, "castSpell=Fire_Arrow:50")),
                D.Record("Potion Medium Healing", [1000, 2], (1, "health=+30")),
                D.Record("Quest Ring", [-1, 1], (1, "1"))]
    db.spells = [D.Record("Fire Arrow", [0] * 20 + [50, 1000], ("",)), D.Record("Wall of Fire", [0] * 20 + [100, 300000], ("",))]
    return db


@pytest.fixture(scope="module")
def table():
    return I.build(synthetic_db())


def test_build_kinds_and_codes(table):
    assert [len(table.of_kind(k)) for k in I.KINDS] == [3, 3, 3, 4]
    d = table.get("armour", 2)
    assert (d.name, d.cls, d.price, d.weight, d.slot) == ("Soft Boots", 12, 100, 15, 12)   # cls = Slot
    assert table.lookup(0x0102).name == "Long Sword"                  # class 1, index 2
    assert table.lookup(0x0F00) is None and table.lookup(0x0000) is None


def test_lookup_uses_decode_item(table):
    code = (1 << 12) | (2 << 5) | 0x0100 | 2                          # material 1, quality 2, class 1, index 2
    assert table.lookup(code).name == "Long Sword"
    assert table.lookup(0x0E01).name == "Book Fire" and table.lookup(0x0E63) is None


def test_scaled_rounding():
    q, m = (0, 0.5, 0, 0, 0, 0, 0), (0, 0.5, 0, 0, 0, 0, 0)
    assert I.scaled(10, q, m, 1) == 3                                 # 2.5 + 0.5 truncates to 3
    assert I.scaled(10, q, m, 1, half=False) == 2                     # absorption: plain truncation


def test_weapon_stats_follow_the_constructor(table):
    s = table.class_stats(table.get("weapon", 2), 0, 0)               # Common Iron Long Sword
    assert (s.price, s.weight, s.magic_cap) == (600, 20, 0)
    assert s.damage_min == 6 and s.damage_spread == 5                 # round(28 x 0.2), round(56 x 0.2) - 6
    assert (s.to_hit, s.range) == (3, 1)                              # range -1 -> 1
    r = table.class_stats(table.get("weapon", 2), 1, 1)               # Rare Bronze
    assert r.price == 600 and r.weight == 12                          # 600 x 4 x 0.25; 20 x 1.2 x 0.5
    assert r.magic_cap == 9                                           # trunc(3 x 3)
    assert r.damage_min == int(28 * 0.288 * 0.694 + 0.5)


def test_armour_and_shield_stats(table):
    s = table.class_stats(table.get("armour", 3), 0, 0)               # Plate Cuirass Common Iron
    assert (s.defence, s.absorption) == (12, 2)                       # round(46 x 0.25), trunc(2 x 1)
    s = table.class_stats(table.get("shield", 2), 1, 0)               # Rare Iron Small
    assert s.absorption == int(1 * 1.21) and s.defence == int(49 * 0.36 + 0.5)


def test_price_effects(table):
    cost = lambda *e: table.price_with_effects(1000, e)
    assert cost() == 1000
    assert cost(I.Effect(1, 777), I.Effect(2, 5)) == 777              # a price effect replaces everything
    s = 5 * 150                                                      # body +5: value x cost.MP
    assert table.effect_cost(I.Effect(2, 5)) == s
    assert cost(I.Effect(2, 5)) == 1000 + int((1.5 ** (s / 70) + 1) * s * 50)
    assert table.effect_cost(I.Effect(44, 3, 4)) == 7 * 15            # element damage: (min + spread) x cost
    assert table.effect_cost(I.Effect(41, 1, 0, 50)) == 50 * 1        # castSpell: charges x cost
    assert cost(I.Effect(2, 100000)) == I.PRICE_CAP


def test_spell_price(table):
    e = I.Effect(41, 1, 0, 50)
    assert table.spell_price(e) == int(500 * 2 ** (math.log(50 / 30 + 1) / math.log(1.2)))
    assert table.price_with_effects(0, [e]) == table.spell_price(e)
    assert I.scroll_packet_price(50, 50) == 41


def test_special_prices_and_subtypes(table):
    book, scroll, potion, quest = table.of_kind("special")
    assert [d.subtype for d in (book, scroll, potion, quest)] == [5, 4, 3, 0]
    assert table.special_price(scroll) == 100 and table.special_price(potion) == 1000
    assert table.special_price(quest) == -1
    assert table.special_price(book) == 0                              # no teachSpell effect yet
    assert table.special_price(book, [I.Effect(42, 2)]) == 300000      # bookCost of spell 2


def test_class_masks_and_users(table):
    sword = table.get("weapon", 2)
    assert sword.allows(0, 0) and sword.allows(0, 1) and not sword.allows(0, 2)
    assert sword.allows(1, 1) and sword.allows(1, 2) and sword.allows(2, 5) and sword.allows(2, 6) and not sword.allows(2, 4)
    assert sword.can_use(False) and not sword.can_use(True)           # fighters need bit 1
    assert table.get("weapon", 3).can_use(True) and not table.get("weapon", 3).can_use(False)
    assert table.get("armour", 1).can_use(True) and table.get("armour", 1).can_use(False)


def test_icon_paths():
    assert I.icon_path((1 << 12) | 0x0102) == "graphics/inventory/0101002.16a"      # material 1, class 1, quality 0, index 2
    assert I.icon_path((6 << 12) | 0x0400 | (1 << 5) | 2) == "graphics/inventory/0604102.16a"
    assert I.icon_path(0x0E2C) == "graphics/inventory/0014044.16a"


def test_parse_effects(table):
    e = table.parse_effects("castSpell=Fire_Arrow:50")
    assert e == [I.Effect(41, 1, 0, 50)]
    assert table.parse_effects("health=+30") == [I.Effect(6, 30)]
    e, = table.parse_effects("body=-2: duration 30")
    assert (e.kind, e.value, e.mode, e.time) == (2, -2, I.MODE_DURATION, 30 << 4)
    e, = table.parse_effects("damageFire=3-7")
    assert (e.kind, e.value, e.spread) == (44, 3, 4)
    assert [x.kind for x in table.parse_effects("body=1,Mind=2,bogus=3")] == [2, 3]   # case-insensitive, unknown skipped
    assert table.parse_effects("castSpell=Nope:5") == []
    assert I.time_part("permanent") == (0, 0) and I.time_part("singleuse") == (8, 0)
    assert I.time_part("charges 3") == (4, 3) and I.time_part("continuous 8") == (2, 8)


def test_section9_pairs(table):
    e = table.pair_effects([(1, 9000000), (41, 5), (2, 3)], spell=2, count=7)
    assert e == [I.Effect(41, 2, 0, 7), I.Effect(1, 9000000), I.Effect(49, 5), I.Effect(2, 3)]   # id 41 -> 49
    assert table.pair_effects([], 2, 0, book=True)[0].kind == 42


def test_slot_weights_are_cumulative_differences(table):
    w = table.slot_weights(1, False)
    assert w == {2: 10, 6: 5}                                           # 10, 15 - 10; the rest adds 0
    assert table.slot_weights(1, True) == {6: 4}


def test_parse_equipment(table):
    code, fx = table.parse_equipment("Rare Bronze Long Sword{body=2}", 0)
    assert (code.kind, code.index, code.quality, code.material) == ("weapon", 2, 1, 1) and fx == [I.Effect(2, 2)]
    code, _ = table.parse_equipment("Leather Boots", 5)                  # Leather -> "Soft Boots"
    assert (code.kind, code.index, code.material) == ("armour", 2, 2)
    code, _ = table.parse_equipment("Hard Leather Boots", 5)             # the longer material name wins
    assert code.material == 3
    code, _ = table.parse_equipment("Magic Wood Large Shield", 1)       # Wood -> "Wooden", " Shield" cut
    assert (code.kind, code.index, code.material) == ("shield", 3, 5)
    code, _ = table.parse_equipment("Very Rare Plate Cuirass", 2)
    assert (code.quality, code.material) == (2, 15)                      # unnamed material: None
    assert table.parse_equipment("Leather Gauntless", 5) is None
    assert table.parse_equipment("Long Sword")[0].kind == "weapon"       # slot None searches all lists


def test_packets_tile():
    def rec(code, price, pairs=b""):
        pl = b"\x01" + struct.pack("<I", price) + pairs
        return struct.pack("<H", code) + b"\x01\x00\x02\x02" + bytes([len(pl)]) + pl
    data = bytes(9) + rec(0x1102, 600, b"\x0d\x04\x0e\x01") + rec(0x0E06, 41, b"\x33\x00\x29\x01\x32\x32")
    a, b = I.parse_packets(data)
    assert (a.code, a.price, a.pairs) == (0x1102, 600, ((13, 4), (14, 1)))
    assert b.price == 41 and b.pairs[0] == (0x29, 1)
    with pytest.raises(ValueError):
        I.parse_packets(data[:-1])


def test_names_from_bin_and_txt():
    class FS:
        files = {"world/data/itemname.bin": struct.pack("<3H", 0x0102, 0x0E01, 0x1102),
                 "main/text/itemname.txt": b"Dagger\r\nBook\r\nBronze Dagger\r\n"}
        def read(self, p):
            return self.files[p]
    names = I.load_names(FS())
    assert names == {0x0102: "Dagger", 0x0E01: "Book", 0x1102: "Bronze Dagger"}
    assert I.ItemTable([], names=names).name_of(0x0E01) == "Book"
    assert I.load_names(type("E", (), {"read": lambda s, p: (_ for _ in ()).throw(FileNotFoundError(p))})()) == {}


def test_resolve_applies_effects(table):
    it = table.resolve((1 << 12) | 0x0102, [I.Effect(2, 5)])
    assert it.defn.name == "Long Sword" and it.stats.price == 150
    assert it.price == 150 + int((1.5 ** (750 / 70) + 1) * 750 * 50)
    assert table.resolve(0x0E02).price == 100 and table.resolve(0x0F00) is None


# --- the install ------------------------------------------------------------------------------

@needs_databin
class TestInstall:
    @classmethod
    def setup_class(cls):
        cls.table = I.load(GFS)
        cls.packets = I.load_packets(GFS)

    def test_counts_and_names(self):
        t = self.table
        assert [len(t.of_kind(k)) for k in I.KINDS] == [27, 9, 30, 96]
        assert len(t.names) == 491 and len(self.packets) == 491
        assert [d.name for d in t.of_kind("weapon")][3] == "Long Sword"
        assert all(len(d.masks) == 7 for d in t if d.kind != "special")

    def test_every_record_parses(self):
        for d in self.table:
            assert d.raw and d.to_dict()["name"] == d.name
            if d.kind == "armour":
                assert d.cls == d.slot and 4 <= d.slot <= 12
        for d in self.table.of_kind("special"):
            assert d.flag == 1 and d.subtype in (0, 3, 4, 5)

    def test_masks_generate_exactly_the_named_class_items(self):
        t = self.table
        named = {(r.defn.kind, r.defn.index, r.quality, r.material)
                 for r in (t.resolve(c) for c in t.names) if r.defn.kind != "special"}
        allowed = {(d.kind, d.index, q, m) for d in t if d.kind != "special" and d.price >= 0 and d.name != "rem"
                   for q in range(7) for m in range(16) if d.allows(q, m)}
        assert allowed == named and len(named) == 395

    def test_packets_match_the_formulas(self):
        t = self.table
        for p in self.packets:
            it = t.resolve(p.code)
            assert it is not None and t.name_of(p.code)
            assert GFS.isfile(I.icon_path(p.code)), hex(p.code)
            if it.defn.kind == "special":
                if it.defn.subtype == 4:
                    e = t.parse_effects(it.defn.effects_text)[0]
                    assert I.scroll_packet_price(t.spells[e.value - 1][1], e.count) == p.price
                elif it.defn.subtype == 3:
                    assert p.price == it.defn.price
                continue
            s = it.stats
            assert s.price == p.price, it.defn.name
            want = {}
            if it.defn.kind == "weapon":
                want = {k: v for k, v in ((13, s.damage_min), (14, s.damage_spread), (12, s.to_hit),
                                          (15, s.defence)) if v > 0}
                if s.damage_min and s.range > 1:
                    want[38] = s.range
            else:
                want = {k: v for k, v in ((15, s.defence), (16, s.absorption)) if v > 0}
            assert dict(p.pairs) == want, it.defn.name

    def test_known_examples(self):
        t = self.table
        sword = t.get("weapon", 4)                                         # databin.md: Long Sword
        assert (sword.name, sword.weight, sword.windup, sword.recovery) == ("Long Sword", 20, 7, 4)
        s = t.class_stats(sword, 0, 0)
        assert (s.damage_min, s.damage_spread, s.to_hit) == (6, 5, 3)

    def test_every_map_item_resolves_with_valid_stats(self):
        t = self.table
        ids = set()
        for p in campaign_maps(GFS):
            m = Map.load(p, GFS)
            recs = m.item_records
            for g in m.item_groups:
                for mem in g.members:
                    ic = decode_item(mem.code)
                    assert ic is not None and t.lookup(ic) is not None, (p, hex(mem.code))
                    r = recs[mem.record - 1] if mem.record else None
                    if r is None or r.a or r.b:
                        continue
                    for sid, _ in r.props:
                        ids.add(sid)
                        assert 0 < sid < len(t.stats) and t.stats[sid].name, (p, sid)
                    t.resolve(ic, t.pair_effects(r.props, r.c & 0xFFFF, r.c >> 16))
        assert ids == {1, 2, 5, 11, 12, 16, 17, 19, 23, 25, 41}

    def test_every_equipment_string_resolves(self):
        from allods2.databin import databin
        db = databin(GFS)
        bad = []
        for group in ("monsters", "humans"):
            for rec in getattr(db, group):
                for k, text in enumerate(rec.extra):
                    if text.strip() and self.table.parse_equipment(text, k if group == "humans" else None) is None:
                        bad.append(text)
        assert bad == ["Leather Gauntless"]                                # typo in data.bin; the exe discards it

    def test_stat_table(self):
        t = self.table
        assert t.stats[2].name == "body" and t.stats[2].cost == 150 and t.stats[2].usable_by == 3
        assert t.stat_id("CastSpell") == 41 and t.spell_id("Fire_Arrow") == 1
        cols = list(zip(*[s.slot_weights for s in t.stats]))
        assert all(list(c) == sorted(c) for c in cols)              # in.<slot> columns are cumulative

    def test_golden_hash(self):
        with open(os.path.join(ROOT, "tests", "golden.json")) as f:
            want = json.load(f)["items"]["sha256"]
        spec = importlib.util.spec_from_file_location("update_golden", os.path.join(ROOT, "tools", "update_golden.py"))
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        assert tool.items_hash(GFS)["sha256"] == want, "items changed; if intended run tools/update_golden.py"
