"""Tests for docs/formats/databin.md."""

import struct

import pytest

from allods2 import databin as D
from allods2.common import DATA

from helpers import needs

needs_databin = needs("world", "data", "data.bin")


def cstr(s):
    b = s.encode("cp1251")
    if len(b) < 0xFF:
        return bytes([len(b)]) + b
    return b"\xff" + struct.pack("<H", len(b)) + b


def base(name, params):
    return cstr(name) + struct.pack("<H", len(params)) + struct.pack("<%di" % len(params), *params)


def group(*lists, one_based=True):
    """Empty string array, then each list as u32 count + records (a 1-based
    list's count includes the unserialized element 0)."""
    out = struct.pack("<H", 0)
    for recs in lists:
        out += struct.pack("<I", len(recs) + (1 if one_based else 0)) + b"".join(recs)
    return out


def sample():
    factor = cstr("Iron") + bytes(16) + struct.pack("<7d", 1, 0.5, 1, 1, 1, 1, 0)
    stats = [base("", [0]), base("price", [1]), base("speed", [2])]
    item_class = base("Dagger", [0, 0, 100, 5]) + struct.pack("<7h", 3, 6, 0, 0, 0, 0, 0) \
        + struct.pack("<H", 1) + cstr("x")
    special = base("Potion", [1, 2]) + b"\x01" + cstr("health=+30")
    monster = base("Goblin", [10, 20]) + cstr("Bronze Pike") + cstr("")
    human = base("Man", [1]) + b"".join(cstr("s%d" % i) for i in range(10))
    spell = base("Haste", [10, 10, 5]) + cstr("speed=+2: duration 30")
    return (group([factor], [factor], one_based=False) + group(stats, one_based=False)
            + group([item_class], [], [item_class]) + group([special]) + group([monster])
            + group([human]) + group([base("Hut", [3])]) + group([spell]))


def test_parse_groups_and_one_based_lists():
    db = D.parse_databin(sample())
    assert [f.name for f in db.qualities + db.materials] == ["Iron", "Iron"]
    assert db.materials[0].doubles[1] == 0.5                    # record +0x38: weight factor
    assert [r.name for r in db.stats] == ["", "price", "speed"]  # 0-based, element 0 present
    assert db.weapons[0].params[D.ITEM_WEIGHT] == 5 and db.shields == []
    assert db.weapons[0].extra == ((3, 6, 0, 0, 0, 0, 0), ["x"])
    assert db.items[0].extra == (1, "health=+30")
    assert db.monsters[0].extra == ("Bronze Pike", "")
    assert len(db.humans[0].extra) == 10
    assert db.structures[0].params == [3] and db.spells[0].name == "Haste"
    assert db.headers == [[]] * 8


def test_count_and_string_escapes():
    r = D._Reader(b"\xff\xff" + struct.pack("<I", 70000) + b"\xff" + struct.pack("<H", 300) + b"a" * 300)
    assert r.count() == 70000
    assert r.string() == "a" * 300


def test_trailing_bytes_rejected():
    with pytest.raises(ValueError):
        D.parse_databin(sample() + b"\0")


def test_modifier_terms():
    db = D.parse_databin(sample())
    m = D.parse_modifier(db, "speed=+2: duration 30")
    assert (m.kind, m.value, m.mode, m.time) == (2, 2, 1, 30)
    m = D.parse_modifier(db, "Speed=-1:continuous 8")            # names compare case-insensitively
    assert (m.value, m.mode, m.time) == (-1, 2, 8)
    assert D.parse_modifier(db, "speed=+1:permanent").mode == 0
    assert D.parse_modifier(db, "speed=+1:singleuse").mode == 8
    assert D.parse_modifier(db, "nothing=+1") is None


def test_monster_search_skips_30_to_62():
    recs = [D.Record("", []) for _ in range(70)]
    recs[29 - 1] = D.Record("Wolf", [])
    recs[31 - 1] = D.Record("Wolf", [])         # skipped range
    recs[64 - 1] = D.Record("Wolf", [])
    recs[20 - 1] = D.Record("Bee", [])          # below 26: never found
    db = D.DataBin(monsters=recs)
    assert db.monster("wolf")[0] == 29
    recs[29 - 1] = D.Record("", [])
    assert db.monster("Wolf")[0] == 64
    assert db.monster("Bee") is None


@needs_databin
def test_install_databin():
    db = D.databin(DATA)                          # raises unless every byte is consumed
    counts = [len(x) for x in (db.qualities, db.materials, db.stats, db.armour, db.shields,
                               db.weapons, db.items, db.monsters, db.humans, db.structures,
                               db.spells)]
    assert counts == [7, 16, 50, 30, 9, 27, 150, 246, 298, 179, 34]
    spells = {r.name: r for r in db.spells}
    assert spells["Fire Arrow"].params[D.SPELL_KIND] == 2
    assert spells["Fire Arrow"].params[D.SPELL_MISSILE_SPEED] == 200
    haste = D.parse_modifier(db, spells["Haste"].extra[0])
    assert (db.stats[haste.kind].name, haste.value, haste.time) == ("speed", 2, 30)
    assert D.parse_modifier(db, spells["Slow"].extra[0]).value == -2
    weapons = {r.name: r for r in db.weapons}
    assert weapons["Long Sword"].params[D.ITEM_WEIGHT] == 20
    assert weapons["Long Sword"].params[D.ITEM_WINDUP:D.ITEM_RECOVERY + 1] == [7, 4]
    tid, goblin = db.monster("Goblin_Pike")
    assert tid == 64 and goblin.params[D.MONSTER["unitType"]] == 64
    assert goblin.params[D.MONSTER["speed"]] == 24
    assert goblin.params[D.MONSTER["attackWindup"]] == 7


@needs_databin
def test_monster_palette_variant():
    db = D.databin(DATA)
    pv = D.MONSTER["paletteVariant"]
    assert pv == 30
    assert db.monster("Goblin_Pike.3")[1].params[pv] == 3
    assert db.monster("F_Zombie.5")[1].params[pv] == 2
    assert {r.params[pv] for r in db.monsters if r.name and len(r.params) > pv} == set(range(1, 8))
