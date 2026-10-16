"""docs/formats/map.md part 5: players (5), units (6), item groups (8), item records (9)."""

import struct

import pytest

from allods2 import units as U
from allods2.common import campaign_maps
from allods2.databin import databin
from allods2.formats import Map
from allods2.formats import entities as E

from helpers import GFS

MAPS = campaign_maps(GFS) if GFS else []
needs_maps = pytest.mark.skipif(not MAPS, reason="game files not present")


def player(colour, flags, money, name, rel=()):
    return struct.pack("<III32s16H", colour, flags, money, name, *(list(rel) + [0] * 16)[:16])


def unit(x, y, **k):
    f = dict(type=64, tier=1, flags=0, behaviour=0, sid=626, owner=2, group=0, f32=10,
             hp=0xFFFF, mhp=0xFFFF, uid=5, squad=1)
    f.update(k)
    return struct.pack("<iiHHIIIIIIHHII", (x << 8) + 128, (y << 8) + 128, f["type"], f["tier"],
                       f["flags"], f["behaviour"], f["sid"], f["owner"], f["group"], f["f32"],
                       f["hp"], f["mhp"], 0xABCD0000 | f["uid"], f["squad"])


# --- synthetic: one test per rule ---------------------------------------------

def test_player_record():
    p, q = E.parse_players(player(1, 0, 0, b"self", [18, 1]) + player(2, 1, 5000, b"Enemy"), 2)
    assert (p.index, p.colour, p.name, p.relations[:2]) == (1, 1, "self", (18, 1))
    assert (q.index, q.flags, q.money) == (2, 1, 5000)


def test_unit_record():
    u, = E.parse_units(unit(38, 68, uid=7, hp=40, mhp=40, flags=0x10), 1)
    assert (u.x, u.y, u.cell) == (38 * 256 + 128, 68 * 256 + 128, (38, 68))
    assert u.uid == 7 and u.stamp == 0xABCD and u.is_human and (u.hp, u.max_hp) == (40, 40)


def test_sizes_are_checked():
    with pytest.raises(ValueError):
        E.parse_units(b"\0" * 47, 1)
    with pytest.raises(ValueError):
        E.parse_players(b"\0" * 75, 1)


def test_groups_tile_exactly():
    one = struct.pack("<IIiiI", 2, 0, 0x2000, 0x3000, 100) + struct.pack("<IHI", 0xE03, 0, 0) \
        + struct.pack("<IHI", 0x2A5, 0, 1)
    g, = E.parse_groups(one, 1)
    assert (g.x, g.y, g.extra, [m.code for m in g.members], g.members[1].record) == \
        (0x2000, 0x3000, 100, [0xE03, 0x2A5], 1)
    with pytest.raises(ValueError):
        E.parse_groups(one + b"\0", 1)


def test_item_records_tile_exactly():
    rec = struct.pack("<IIII", 0, 0, 0, 0)[:12] + b"\0" * 6 + struct.pack("<II", 0, 2) \
        + struct.pack("<HI", 1, 9000000) + struct.pack("<HI", 41, 50)
    r, = E.parse_item_records(struct.pack("<I", 1) + rec)
    assert r.props == ((1, 9000000), (41, 50))
    with pytest.raises(ValueError):
        E.parse_item_records(struct.pack("<I", 1) + rec[:-1])


# --- the install -----------------------------------------------------------------

@needs_maps
def test_every_record_parses_and_counts_match():
    tot = [0, 0, 0, 0]
    for path in MAPS:
        m = Map.load(path, GFS)
        h = m.header
        assert len(m.players) == h.player_count and len(m.units) == h.n_sec6
        assert len(m.item_groups) == h.n_sec8
        tot = [a + b for a, b in zip(tot, (len(m.players), len(m.units), len(m.item_groups),
                                           len(m.item_records)))]
    assert tot == [251, 4212, 51, 88]


@needs_maps
def test_owners_reference_players_and_groups_exist():
    for path in MAPS:
        m = Map.load(path, GFS)
        n, g = len(m.players), len(m.item_groups)
        for u in m.units:
            assert 1 <= u.owner <= n, (path, u)
            assert u.group <= g
            assert u.x & 0xFF == 128 and u.y & 0xFF == 128
        links = [u.group for u in m.units if u.group]
        assert len(links) == len(set(links))                  # no group claimed twice
        assert len(m.ground_groups) == g - len(links)


@needs_maps
def test_types_and_templates_resolve():
    db = databin(GFS)
    ids = U.by_id(U.unit_types(GFS))
    seen = set()
    for path in MAPS:
        m = Map.load(path, GFS)
        for u in m.units:
            assert E.template(db, u) is not None, (path, u)
            assert ids[u.type].file, u
            seen.add(u.type)
            if not u.is_human and ids[u.type].Palette:
                face = E.template(db, u).params[db.columns("monsters").index("face")]
                assert 1 <= face <= ids[u.type].Palette, (path, u, face)
    assert len(seen) == 53


@needs_maps
def test_item_codes_decode_to_known_items():
    db = databin(GFS)
    for path in MAPS:
        m = Map.load(path, GFS)
        for g in m.item_groups:
            for mem in g.members:
                kind = (mem.code >> 8) & 15
                assert mem.code < 1 << 16
                if kind == 14:
                    assert 1 <= (mem.code & 0xFF) <= len(db.items)
                else:
                    assert 1 <= kind <= 13 and ((mem.code >> 5) & 7) < len(db.qualities)
                    assert (mem.code >> 12) < len(db.materials)
                assert mem.record <= len(m.item_records)


def test_item_code_decoding():
    assert E.decode_item(0xE03) == E.ItemCode("special", 14, 3)
    assert E.decode_item(0x5146) == E.ItemCode("weapon", 1, 6, 2, 5)       # Two Handed Sword, Mithrill
    assert E.decode_item(0xC263).kind == "shield" and E.decode_item(0x7790).kind == "armour"
    assert E.decode_item(0x0001) is None and E.decode_item(0xF001) is None


@needs_maps
def test_item_classes_select_their_data_bin_lists():
    db = databin(GFS)
    slot = db.columns("classes").index("Slot")
    lists = {"weapon": db.weapons, "shield": db.shields, "armour": db.armour, "special": db.items}
    for path in MAPS:
        for g in Map.load(path, GFS).item_groups:
            for mem in g.members:
                it = E.decode_item(mem.code)
                assert 1 <= it.index <= len(lists[it.kind]), (path, mem)
                if it.kind == "armour":                     # the record's Slot equals the code's class
                    assert lists["armour"][it.index - 1].params[slot] == it.cls, (path, mem)


@needs_maps
def test_scene_draws_units_and_items():
    from allods2.anim.scene import Scene, draw_scene
    from allods2.graphics.canvas import Canvas
    m = Map.load("scenario/10.alm", GFS)
    cv = Canvas(m.width * 32, m.height * 32)
    draw_scene(cv, m, Scene(GFS), relief=False, objects=False, structures=False, units=True, items=True)
    assert cv.pix.any()
